import numpy as np
import pandas as pd


def run_crossover_backtest(df: pd.DataFrame, ma_type: str = "EMA") -> dict:
    """
    Simulates going Long when {ma_type}_50 > {ma_type}_200 and Cash otherwise.
    Supports: 'SMA', 'EMA', 'VWMA', 'HMA'
    """
    fast_col = f"{ma_type}_50"
    slow_col = f"{ma_type}_200"

    if fast_col not in df.columns or slow_col not in df.columns:
        return {}

    valid = df.dropna(subset=[fast_col, slow_col]).copy()
    if len(valid) < 10:
        return {}

    valid["Asset_Return"] = valid["close"].pct_change().fillna(0)
    valid["Position"] = (valid[fast_col] > valid[slow_col]).astype(int).shift(1).fillna(0)
    valid["Strategy_Return"] = valid["Position"] * valid["Asset_Return"]

    valid["BuyHold_Equity"] = (1 + valid["Asset_Return"]).cumprod()
    valid["Strategy_Equity"] = (1 + valid["Strategy_Return"]).cumprod()

    rolling_max = valid["Strategy_Equity"].cummax()
    drawdown = (valid["Strategy_Equity"] - rolling_max) / rolling_max
    max_dd = drawdown.min() * 100

    std_ret = valid["Strategy_Return"].std()
    sharpe = (valid["Strategy_Return"].mean() / std_ret) * np.sqrt(252) if std_ret > 0 else 0.0

    total_strat_ret = (valid["Strategy_Equity"].iloc[-1] - 1) * 100
    total_bh_ret = (valid["BuyHold_Equity"].iloc[-1] - 1) * 100
    trades = int(valid["Position"].diff().abs().sum())

    return {
        "ma_type": ma_type,
        "Total Strategy Return (%)": round(float(total_strat_ret), 2),
        "Buy & Hold Return (%)": round(float(total_bh_ret), 2),
        "Outperformance (%)": round(float(total_strat_ret - total_bh_ret), 2),
        "Sharpe Ratio": round(float(sharpe), 2),
        "Max Drawdown (%)": round(float(max_dd), 2),
        "Trades": trades,
    }


def compare_all_ma_families(df: pd.DataFrame) -> list[dict]:
    """Runs 50/200 crossover backtests across SMA, EMA, VWMA, and HMA."""
    results = []
    for fam in ["SMA", "EMA", "VWMA", "HMA"]:
        res = run_crossover_backtest(df, ma_type=fam)
        if res:
            results.append(res)
    return results