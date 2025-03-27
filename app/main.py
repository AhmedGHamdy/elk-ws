import asyncio
import json
import logging
import yfinance as yf
from fastapi import FastAPI, WebSocket
from elasticapm.contrib.starlette import ElasticAPM, make_apm_client
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.semconv.resource import ResourceAttributes

# Configure logging
logging.basicConfig(
    filename='/home/LogFiles/application/stock_stream.log',
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI()

# Configure Elastic APM
apm = make_apm_client({
    'SERVICE_NAME': 'stock-stream-service',
    'SERVER_URL': 'http://<vm-public-ip>:8200',  # Replace with VM IP
    'ENVIRONMENT': 'production'
})
app.add_middleware(ElasticAPM, client=apm)

# Configure OpenTelemetry
resource = Resource.create({
    ResourceAttributes.SERVICE_NAME: "stock-stream-service",
    ResourceAttributes.SERVICE_VERSION: "1.0.0",
    ResourceAttributes.DEPLOYMENT_ENVIRONMENT: "production"
})
tracer_provider = TracerProvider(resource=resource)
trace.set_tracer_provider(tracer_provider)

# Use APM Server's OTLP endpoint
otlp_exporter = OTLPSpanExporter(
    endpoint="http://<vm-public-ip>:8200/v1/traces"  # Corrected to APM Server OTLP endpoint
)
span_processor = BatchSpanProcessor(otlp_exporter)
tracer_provider.add_span_processor(span_processor)

tracer = trace.get_tracer(__name__)
FastAPIInstrumentor.instrument_app(app)

STOCKS = ["AAPL", "GOOGL", "MSFT", "AMZN", "META"]

async def get_stock_price(symbol: str):
    with tracer.start_as_current_span("get_stock_price") as span:
        span.set_attribute("stock_symbol", symbol)
        try:
            stock = yf.Ticker(symbol)
            price = stock.info.get('regularMarketPrice', 0)
            span.set_attribute("price", price)
            logger.info(f"Fetched price for {symbol}: {price}")
            return {"symbol": symbol, "price": price}
        except Exception as e:
            span.record_exception(e)
            span.set_status(trace.Status(trace.StatusCode.ERROR))
            logger.error(f"Error fetching {symbol}: {e}")
            return {"symbol": symbol, "price": None, "error": str(e)}

async def price_generator():
    while True:
        with tracer.start_as_current_span("price_generator"):
            prices = []
            for symbol in STOCKS:
                price_data = await get_stock_price(symbol)
                prices.append(price_data)
            yield json.dumps(prices)
            await asyncio.sleep(5)

@app.websocket("/ws/stocks")
async def websocket_endpoint(websocket: WebSocket):
    with tracer.start_as_current_span("websocket_connection") as span:
        await websocket.accept()
        client = websocket.client
        span.set_attribute("client.ip", str(client.host) if client else "unknown")
        logger.info("WebSocket connection established")
        try:
            async for prices in price_generator():
                await websocket.send_text(prices)
        except Exception as e:
            logger.error(f"WebSocket error: {e}")
            span.record_exception(e)
            span.set_status(trace.Status(trace.StatusCode.ERROR))
        finally:
            await websocket.close()
            logger.info("WebSocket connection closed")

@app.get("/")
async def root():
    return {"status": "ok", "service": "stock-stream-service"}