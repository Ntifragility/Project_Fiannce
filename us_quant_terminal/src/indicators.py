import numpy as np
import pandas as pd


def calc_wma(series: pd.Series, period: int) -> pd.Series:
    """Linearly Weighted Moving Average (WMA) computed via dot product."""
    weights = np.arange(1, period + 1, dtype=float)
    weight_sum = weights.sum()
    return series.rolling(window=period).apply(lambda x: np.dot(x, weights) / weight_sum, raw=True)


def calc_hma(series: pd.Series, period: int) -> pd.Series:
    """
    Hull Moving Average (HMA):
    HMA(n) = WMA( 2 * WMA(n/2) - WMA(n), sqrt(n) )
    Virtually eliminates phase lag while preserving smoothness.
    """
    half_length = max(1, int(period / 2))
    sqrt_length = max(1, int(np.sqrt(period)))
    wma_half = calc_wma(series, half_length)
    wma_full = calc_wma(series, period)
    raw_hma = (2.0 * wma_half) - wma_full
    return calc_wma(raw_hma, sqrt_length)


def calc_vwma(close: pd.Series, volume: pd.Series, period: int) -> pd.Series:
    """
    Volume-Weighted Moving Average (VWMA):
    Sum(Close * Volume, n) / Sum(Volume, n)
    """
    pv = close * volume
    return pv.rolling(window=period).sum() / volume.rolling(window=period).sum()


def calc_kama(series: pd.Series, period: int = 50, fast_ema: int = 2, slow_ema: int = 30) -> pd.Series:
    """
    Kaufman's Adaptive Moving Average (KAMA):
    Dynamically adjusts its smoothing constant based on market Efficiency Ratio (signal vs noise).
    """
    values = series.to_numpy(dtype=float)
    n = len(values)
    kama = np.full(n, np.nan)
    if n <= period:
        return pd.Series(kama, index=series.index)

    fast_sc = 2.0 / (fast_ema + 1.0)
    slow_sc = 2.0 / (slow_ema + 1.0)

    # Seed first valid KAMA value with the simple mean
    kama[period - 1] = np.nanmean(values[:period])

    for i in range(period, n):
        direction = abs(values[i] - values[i - period])
        volatility = np.sum(np.abs(np.diff(values[i - period: i + 1])))
        er = (direction / volatility) if volatility != 0 else 0.0
        sc = (er * (fast_sc - slow_sc) + slow_sc) ** 2
        kama[i] = kama[i - 1] + sc * (values[i] - kama[i - 1])

    return pd.Series(kama, index=series.index)


def enrich_indicators(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "close" not in df.columns:
        return df

    out = df.copy()
    close = out["close"]
    volume = out["volume"]

    # 1. Standard Simple & Exponential Moving Averages (50 & 200)
    out["SMA_50"] = close.rolling(window=50).mean()
    out["SMA_200"] = close.rolling(window=200).mean()
    out["EMA_50"] = close.ewm(span=50, adjust=False).mean()
    out["EMA_200"] = close.ewm(span=200, adjust=False).mean()

    # 2. Volume-Weighted Moving Averages (50 & 200)
    out["VWMA_50"] = calc_vwma(close, volume, 50)
    out["VWMA_200"] = calc_vwma(close, volume, 200)

    # 3. Low-Lag Hull Moving Averages (50 & 200)
    out["HMA_50"] = calc_hma(close, 50)
    out["HMA_200"] = calc_hma(close, 200)

    # 4. Kaufman's Adaptive Moving Average (50)
    out["KAMA_50"] = calc_kama(close, period=50)

    # 5. Spreads, Z-Score & Regime Scoring
    out["Dist_EMA200_Pct"] = ((close - out["EMA_200"]) / out["EMA_200"]) * 100
    out["EMA_Spread_Pct"] = ((out["EMA_50"] - out["EMA_200"]) / out["EMA_200"]) * 100

    spread = close - out["EMA_200"]
    out["Extension_ZScore"] = (spread - spread.rolling(60).mean()) / spread.rolling(60).std()

    # 6. Crossover Detection for any selected MA family
    for family in ["SMA", "EMA", "VWMA", "HMA"]:
        bull = out[f"{family}_50"] > out[f"{family}_200"]
        out[f"{family}_Cross"] = np.where(
            bull & (~bull.shift(1, fill_value=False)), 1,
            np.where((~bull) & bull.shift(1, fill_value=False), -1, 0)
        )

    # 7. Institutional Trend Alignment Score (0 to 4)
    out["Trend_Score"] = (
        (close > out["HMA_50"]).astype(int)
        + (out["EMA_50"] > out["SMA_50"]).astype(int)
        + (out["SMA_50"] > out["EMA_200"]).astype(int)
        + (out["EMA_200"] > out["SMA_200"]).astype(int)
    )

    return out