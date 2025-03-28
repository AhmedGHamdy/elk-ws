import asyncio
import json
import os
import yfinance as yf
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
import logging

from elasticapm import Client, capture_span
from elasticapm.contrib.starlette import ElasticAPM

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
logging.getLogger("elasticapm").setLevel(logging.DEBUG)

# Initialize FastAPI app
app = FastAPI()

# Allow frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Elastic APM config
PUBLIC_IP = os.environ.get("APM_SERVER_IP", "20.196.29.154")
apm_config = {
    'SERVICE_NAME': 'stock-stream-service',
    'SERVER_URL': f'http://{PUBLIC_IP}:8200',  # Use HTTP to match APM Server config
    'ENVIRONMENT': 'dev',
    'DEBUG': True,
    'SECRET_TOKEN': '',
    'LOG_LEVEL': 'debug',
    'VERIFY_SERVER_CERT': False,  # Not needed for HTTP, but harmless to keep
    'TRANSPORT_TIMEOUT': 30,  # Increased timeout to avoid read timeouts
}

apm_client = Client(apm_config)
app.add_middleware(ElasticAPM, client=apm_client)

# Health and Debug Endpoints
@app.get("/debug")
async def debug():
    return {"routes": [route.path for route in app.routes]}

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

@app.get("/")
async def root():
    return {"status": "ok", "service": "stock-stream-service"}

@app.get("/apm-test")
async def apm_test():
    apm_client.begin_transaction("request")
    with capture_span("test_span", span_type="custom"):
        logger.info("➡️ Elastic APM test span")
    apm_client.end_transaction("apm-test", "success")
    return {"message": "Test span sent to Elastic APM"}

# Stock streaming logic
STOCKS = ["AAPL", "GOOGL", "MSFT", "AMZN", "META"]

async def get_stock_price(symbol: str):
    with capture_span("get_stock_price", span_type="stock"):
        for attempt in range(3):
            try:
                stock = yf.Ticker(symbol)
                price = stock.info.get('regularMarketPrice', 0)
                return {"symbol": symbol, "price": price}
            except Exception as e:
                if "429" in str(e):
                    logger.warning(f"Rate limit hit for {symbol}, retrying in {5 * (attempt + 1)}s")
                    await asyncio.sleep(5 * (attempt + 1))
                else:
                    apm_client.capture_exception()
                    logger.error(f"Error getting price for {symbol}: {str(e)}")
                    return {"symbol": symbol, "price": None, "error": str(e)}
        return {"symbol": symbol, "price": None, "error": "Max retries exceeded"}

async def price_generator():
    while True:
        with capture_span("price_generator", span_type="stream"):
            prices = await asyncio.gather(*[get_stock_price(symbol) for symbol in STOCKS])
            yield json.dumps(prices)
            await asyncio.sleep(60)

@app.websocket("/ws/stocks")
async def websocket_endpoint(websocket: WebSocket):
    apm_client.begin_transaction("websocket")
    await websocket.accept()
    try:
        with capture_span("websocket_connection", span_type="ws"):
            async for prices in price_generator():
                await websocket.send_text(prices)
    except Exception as e:
        apm_client.capture_exception()
        logger.error(f"WebSocket error: {e}")
    finally:
        apm_client.end_transaction("websocket", "success")
        await websocket.close()

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    host = os.environ.get("HOST", "0.0.0.0")
    logger.info(f"Starting server on {host}:{port}")
    uvicorn.run("main:app", host=host, port=port, log_level="info")