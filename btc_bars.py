import os
from datetime import datetime
from pathlib import Path

from alpaca.data.historical import CryptoHistoricalDataClient
from alpaca.data.requests import CryptoBarsRequest
from alpaca.data.timeframe import TimeFrame
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / "us_quant_terminal" / ".env")

client = CryptoHistoricalDataClient(
    api_key=os.environ["ALPACA_API_KEY"],
    secret_key=os.environ["ALPACA_SECRET_KEY"],
)

request_params = CryptoBarsRequest(
    symbol_or_symbols=["BTC/USD"],
    timeframe=TimeFrame.Day,
    start=datetime(2022, 9, 1),
    end=datetime(2022, 9, 7),
)

btc_bars = client.get_crypto_bars(request_params)
print(btc_bars.df)
