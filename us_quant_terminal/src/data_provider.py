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
        start_str: str = "",
        end_str: str = "",
        use_cache: bool = True,
    ) -> dict[str, pd.DataFrame]:
        tf_map = {
            "1Day": TimeFrame.Day,
            "1Hour": TimeFrame.Hour,
        }
        tf = tf_map.get(timeframe_str, TimeFrame.Day)

        # Parse user dates or default to last 2.5 years
        end_dt = datetime.strptime(end_str, "%Y-%m-%d") if end_str else datetime.now()
        user_start_dt = (
            datetime.strptime(start_str, "%Y-%m-%d")
            if start_str
            else (end_dt - timedelta(days=900))
        )

        # Fetch 350 extra calendar days BEFORE user_start_dt so the 200 SMA/EMA
        # is already warmed up on the first day of your chosen date window
        fetch_start_dt = user_start_dt - timedelta(days=350)

        tag = f"{timeframe_str}_{fetch_start_dt.strftime('%Y%m%d')}_{end_dt.strftime('%Y%m%d')}"
        stock_data = {}
        symbols_to_fetch = []

        if use_cache:
            for sym in symbols:
                cache_file = CACHE_DIR / f"{sym}_{tag}.parquet"
                if cache_file.exists():
                    stock_data[sym] = pd.read_parquet(cache_file)
                else:
                    symbols_to_fetch.append(sym)
        else:
            symbols_to_fetch = symbols

        if symbols_to_fetch:
            req = StockBarsRequest(
                symbol_or_symbols=symbols_to_fetch,
                timeframe=tf,
                start=fetch_start_dt,
                end=end_dt,
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
                        if use_cache:
                            df_sym.to_parquet(CACHE_DIR / f"{sym}_{tag}.parquet")

        return stock_data