import asyncio
import json
import yfinance as yf
from fastapi import FastAPI, WebSocket
from elasticapm.contrib.starlette import ElasticAPM
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentation

# Initialize FastAPI
app = FastAPI()

# Configure Elastic APM
app.add_middleware(ElasticAPM, service_name="stock-stream-service", server_url="http://localhost:8200")

# Configure OpenTelemetry
trace.set_tracer_provider(TracerProvider())
tracer = trace.get_tracer(__name__)
otlp_exporter = OTLPSpanExporter(endpoint="http://localhost:4317")
span_processor = BatchSpanProcessor(otlp_exporter)
trace.get_tracer_provider().add_span_processor(span_processor)
FastAPIInstrumentation().instrument_app(app)

# List of stock symbols to track
STOCKS = ["AAPL", "GOOGL", "MSFT", "AMZN", "META"]

async def get_stock_price(symbol: str):
    """Get real-time stock price using yfinance"""
    with tracer.start_as_current_span("get_stock_price") as span:
        span.set_attribute("stock_symbol", symbol)
        try:
            stock = yf.Ticker(symbol)
            price = stock.info.get('regularMarketPrice', 0)
            span.set_attribute("price", price)
            return {"symbol": symbol, "price": price}
        except Exception as e:
            span.record_exception(e)
            span.set_status(trace.Status(trace.StatusCode.ERROR))
            return {"symbol": symbol, "price": None, "error": str(e)}

async def price_generator():
    """Generate stock prices every 5 seconds"""
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
    """WebSocket endpoint for streaming stock prices"""
    with tracer.start_as_current_span("websocket_connection"):
        await websocket.accept()
        try:
            async for prices in price_generator():
                await websocket.send_text(prices)
        except Exception as e:
            print(f"WebSocket error: {e}")
        finally:
            await websocket.close()

@app.get("/")
async def root():
    """Health check endpoint"""
    return {"status": "ok", "service": "stock-stream-service"}