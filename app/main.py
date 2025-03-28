import asyncio
import json
import yfinance as yf
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from elasticapm.contrib.starlette import ElasticAPM
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.trace import Status, StatusCode

app = FastAPI()

# Allow frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Elastic APM Middleware
app.add_middleware(
    ElasticAPM,
    service_name="stock-stream-service",
    server_url="http://localhost:8200"  # تأكد إنه متاح
)

# OpenTelemetry setup (optional if backend collector is ready)
trace.set_tracer_provider(TracerProvider())
tracer = trace.get_tracer(__name__)
otlp_exporter = OTLPSpanExporter(endpoint="http://localhost:4317", insecure=True)
trace.get_tracer_provider().add_span_processor(BatchSpanProcessor(otlp_exporter))
FastAPIInstrumentor.instrument_app(app)

STOCKS = ["AAPL", "GOOGL", "MSFT", "AMZN", "META"]

async def get_stock_price(symbol: str):
    with tracer.start_as_current_span("get_stock_price") as span:
        span.set_attribute("stock_symbol", symbol)
        try:
            stock = yf.Ticker(symbol)
            price = stock.info.get('regularMarketPrice', 0)
            span.set_attribute("price", price)
            return {"symbol": symbol, "price": price}
        except Exception as e:
            span.record_exception(e)
            span.set_status(Status(StatusCode.ERROR))
            return {"symbol": symbol, "price": None, "error": str(e)}

async def price_generator():
    while True:
        with tracer.start_as_current_span("price_generator"):
            prices = [await get_stock_price(symbol) for symbol in STOCKS]
            yield json.dumps(prices)
            await asyncio.sleep(5)

@app.websocket("/ws/stocks")
async def websocket_endpoint(websocket: WebSocket):
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
    return {"status": "ok", "service": "stock-stream-service"}
