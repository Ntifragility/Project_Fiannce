from datetime import datetime, timedelta
import pandas as pd
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.data.enums import DataFeed, Adjustment
from src.config import CACHE_DIR


class USStockDataProvider:
    def __init__(self, api_key: str, secret_key: str):
        if not api_key or not secret_key:
            raise ValueError("Missing Alpaca API keys in .env file.")
        self.client = StockHistoricalDataClient(api_key=api_key, secret_key=secret_key)

    def fetch_bars(
        self,
        symbols: list[str],
        timeframe_str: str = "1Day",
        lookback_days: int = 750,
        use_cache: bool = True
    ) -> dict[str, pd.DataFrame]:
        tf_map = {
            "1Day": TimeFrame.Day,
            "1Hour": TimeFrame.Hour,
        }
        tf = tf_map.get(timeframe_str, TimeFrame.Day)
        stock_data = {}
        symbols_to_fetch = []

        # 1. Check local Parquet cache ( valid if updated within the last 4 hours )
        if use_cache:
            for sym in symbols:
                cache_file = CACHE_DIR / f"{sym}_{timeframe_str}_{lookback_days}d.parquet"
                if cache_file.exists():
                    mtime = datetime.fromtimestamp(cache_file.stat().st_mtime)
                    if datetime.now() - mtime < timedelta(hours=4):
                        stock_data[sym] = pd.read_parquet(cache_file)
                        continue
                symbols_to_fetch.append(sym)
        else:
            symbols_to_fetch = symbols

        # 2. Fetch remaining symbols from Alpaca US Stock API
        if symbols_to_fetch:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=lookback_days)

            req = StockBarsRequest(
                symbol_or_symbols=symbols_to_fetch,
                timeframe=tf,
                start=start_date,
                end=end_date,
                adjustment=Adjustment.ALL,
                feed=DataFeed.IEX,
            )
            bars = self.client.get_stock_bars(req)
            raw_df = bars.df

            if not raw_df.empty:
                for sym in symbols_to_fetch:
                    if sym in raw_df.index.get_level_values(0):
                        df_sym = raw_df.loc[sym].copy().sort_index()
                        stock_data[sym] = df_sym
                        # Save to Parquet so Python or Rust can read it instantaneously
                        cache_file = CACHE_DIR / f"{sym}_{timeframe_str}_{lookback_days}d.parquet"
                        df_sym.to_parquet(cache_file)

        return stock_data