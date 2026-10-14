import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from src.config import ALPACA_API_KEY, ALPACA_SECRET_KEY, SECTOR_WATCHLISTS
from src.data_provider import USStockDataProvider
from src.indicators import enrich_indicators
from src.backtester import run_crossover_backtest

st.set_page_config(page_title="US Equities Quant Terminal", page_icon="⚡", layout="wide")

# Custom Dark Terminal Styling
st.markdown("""
<style>
    .block-container { padding-top: 1.5rem; padding-bottom: 1.5rem; }
    div[data-testid="stMetric"] {
        background-color: #161B22;
        border: 1px solid #30363D;
        padding: 12px 16px;
        border-radius: 8px;
    }
</style>
""", unsafe_allow_html=True)

st.title("⚡ US Equities Moving Average Quant Terminal")

# --- SIDEBAR CONTROL PANEL ---
with st.sidebar:
    st.header("🎛️ Terminal Controls")
    sector = st.selectbox("1. Select Sector Preset", list(SECTOR_WATCHLISTS.keys()))
    selected_stocks = st.multiselect(
        "2. Active Watchlist",
        options=sorted(list({sym for syms in SECTOR_WATCHLISTS.values() for sym in syms})),
        default=SECTOR_WATCHLISTS[sector]
    )
    custom_tickers = st.text_input("Add Custom US Tickers (comma-separated)", placeholder="PLTR, UBER, COIN")
    if custom_tickers:
        for t in custom_tickers.split(","):
            clean_t = t.strip().upper()
            if clean_t and clean_t not in selected_stocks:
                selected_stocks.append(clean_t)

    timeframe = st.selectbox("3. Bar Timeframe", ["1Day", "1Hour"], index=0)
    lookback = st.slider("4. Lookback Window (Days)", min_value=400, max_value=1800, value=900, step=100)
    use_cache = st.checkbox("Use Local Parquet Cache", value=True, help="Speeds up repeat queries and shares files with Rust")

    run_btn = st.button("🚀 Sync Market Data & Run Engine", type="primary", use_container_width=True)

# --- DATA EXECUTION ---
if run_btn or "quant_data" not in st.session_state:
    if not selected_stocks:
        st.warning("Select at least one US stock in the sidebar.")
        st.stop()
    try:
        provider = USStockDataProvider(ALPACA_API_KEY, ALPACA_SECRET_KEY)
        with st.spinner("Synchronizing bars with Alpaca IEX & computing regime matrix..."):
            raw_map = provider.fetch_bars(selected_stocks, timeframe, lookback, use_cache)
            enriched_map = {}
            scanner_rows = []

            for sym, df in raw_map.items():
                edf = enrich_indicators(df)
                if len(edf) < 200:
                    continue
                enriched_map[sym] = edf
                last = edf.iloc[-1]

                # Find last crossover date
                crosses = edf[edf["EMA_Cross"] != 0]
                last_cross_str = (
                    f"{'🟢 Golden' if crosses.iloc[-1]['EMA_Cross'] == 1 else '🔴 Death'} "
                    f"({crosses.index[-1].strftime('%Y-%m-%d')})"
                    if not crosses.empty else "None in window"
                )

                scanner_rows.append({
                    "Ticker": sym,
                    "Close ($)": round(last["close"], 2),
                    "50 SMA": round(last["SMA_50"], 2),
                    "50 EMA": round(last["EMA_50"], 2),
                    "200 SMA": round(last["SMA_200"], 2),
                    "200 EMA": round(last["EMA_200"], 2),
                    "50/200 EMA Spread (%)": round(last["EMA_Spread_Pct"], 2),
                    "Dist to 200 EMA (%)": round(last["Dist_EMA200_Pct"], 2),
                    "Extension Z-Score": round(last["Extension_ZScore"], 2),
                    "Trend Score (0-4)": int(last["Trend_Score"]),
                    "Last 50/200 EMA Cross": last_cross_str,
                })

            st.session_state["quant_data"] = enriched_map
            st.session_state["scanner_df"] = pd.DataFrame(scanner_rows)
    except Exception as e:
        st.error(f"Alpaca API / Engine Error: {e}")
        st.stop()

quant_data = st.session_state.get("quant_data", {})
scanner_df = st.session_state.get("scanner_df", pd.DataFrame())

if not quant_data:
    st.info("Click **Sync Market Data & Run Engine** in the sidebar to populate the terminal.")
    st.stop()

# --- MULTI-TAB TERMINAL WORKSPACE ---
tab_scanner, tab_chart, tab_backtest = st.tabs([
    "📡 Multi-Stock Regime Scanner",
    "📈 3-Pane Technical Inspector",
    "🧪 50/200 Crossover Backtester"
])

with tab_scanner:
    st.subheader("Institutional Moving Average Matrix")
    st.caption("Trend Score 4 = Price > 50 EMA > 50 SMA > 200 EMA > 200 SMA | Z-Score > 2.0 indicates statistically overbought vs 200 EMA.")
    
    styled_df = (
        scanner_df.style
        .background_gradient(subset=["50/200 EMA Spread (%)", "Dist to 200 EMA (%)"], cmap="RdYlGn", vmin=-15, vmax=15)
        .background_gradient(subset=["Trend Score (0-4)"], cmap="Blues", vmin=0, vmax=4)
        .format({
            "Close ($)": "${:.2f}", "50 SMA": "${:.2f}", "50 EMA": "${:.2f}",
            "200 SMA": "${:.2f}", "200 EMA": "${:.2f}",
            "50/200 EMA Spread (%)": "{:+.2f}%", "Dist to 200 EMA (%)": "{:+.2f}%",
            "Extension Z-Score": "{:+.2f}σ"
        })
    )
    st.dataframe(styled_df, use_container_width=True, hide_index=True, height=420)

with tab_chart:
    col_sel, col_ma = st.columns([1, 2])
    with col_sel:
        active_sym = st.selectbox("Select Equity to Inspect", list(quant_data.keys()))
    
    df_sym = quant_data[active_sym]
    latest = df_sym.iloc[-1]

    # Top KPI Ribbon
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Latest Close", f"${latest['close']:.2f}", f"{df_sym['close'].pct_change().iloc[-1]*100:+.2f}% today")
    k2.metric("50 SMA / 50 EMA", f"${latest['SMA_50']:.2f}", f"EMA: ${latest['EMA_50']:.2f}")
    k3.metric("200 SMA / 200 EMA", f"${latest['SMA_200']:.2f}", f"EMA: ${latest['EMA_200']:.2f}")
    k4.metric("50 vs 200 EMA Spread", f"{latest['EMA_Spread_Pct']:+.2f}%", "Bullish Regime" if latest["EMA_Spread_Pct"] > 0 else "Bearish Regime")
    k5.metric("200 EMA Z-Score", f"{latest['Extension_ZScore']:+.2f}σ", "Overextended" if abs(latest["Extension_ZScore"]) > 2 else "Normal Range")

    # 3-Pane Synchronized Plotly Chart
    fig = make_subplots(
        rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.03,
        row_heights=[0.60, 0.18, 0.22],
        subplot_titles=(
            f"{active_sym} Price Action, 50/200 MAs & Crossover Signals",
            "Volume",
            "50/200 Spread Oscillator (%)"
        )
    )

    # Pane 1: Candlesticks & 4 Moving Averages
    fig.add_trace(go.Candlestick(
        x=df_sym.index, open=df_sym["open"], high=df_sym["high"],
        low=df_sym["low"], close=df_sym["close"], name="OHLC"
    ), row=1, col=1)

    fig.add_trace(go.Scatter(x=df_sym.index, y=df_sym["SMA_50"], name="50 SMA", line=dict(color="#3B82F6", width=1.6)), row=1, col=1)
    fig.add_trace(go.Scatter(x=df_sym.index, y=df_sym["EMA_50"], name="50 EMA", line=dict(color="#06B6D4", width=1.6, dash="dot")), row=1, col=1)
    fig.add_trace(go.Scatter(x=df_sym.index, y=df_sym["SMA_200"], name="200 SMA", line=dict(color="#F97316", width=2.2)), row=1, col=1)
    fig.add_trace(go.Scatter(x=df_sym.index, y=df_sym["EMA_200"], name="200 EMA", line=dict(color="#EAB308", width=2.2, dash="dot")), row=1, col=1)

    # Plot Golden & Death Cross Markers on Chart
    golden = df_sym[df_sym["EMA_Cross"] == 1]
    death = df_sym[df_sym["EMA_Cross"] == -1]

    fig.add_trace(go.Scatter(
        x=golden.index, y=golden["EMA_50"], mode="markers", name="EMA Golden Cross",
        marker=dict(symbol="triangle-up", size=14, color="#22C55E", line=dict(width=1, color="white"))
    ), row=1, col=1)

    fig.add_trace(go.Scatter(
        x=death.index, y=death["EMA_50"], mode="markers", name="EMA Death Cross",
        marker=dict(symbol="triangle-down", size=14, color="#EF4444", line=dict(width=1, color="white"))
    ), row=1, col=1)

    # Pane 2: Volume Bars
    vol_colors = ["#22C55E" if c >= o else "#EF4444" for c, o in zip(df_sym["close"], df_sym["open"])]
    fig.add_trace(go.Bar(x=df_sym.index, y=df_sym["volume"], name="Volume", marker_color=vol_colors), row=2, col=1)

    # Pane 3: 50/200 Spread Oscillator
    fig.add_trace(go.Scatter(
        x=df_sym.index, y=df_sym["EMA_Spread_Pct"], name="EMA 50/200 Spread %",
        fill="tozeroy", line=dict(color="#A855F7", width=1.5)
    ), row=3, col=1)
    fig.add_hline(y=0, line_dash="dash", line_color="gray", row=3, col=1)
    
    fig.update_layout(
        height=780, template="plotly_dark", xaxis_rangeslider_visible=False,
        hovermode="x unified", margin=dict(l=20, r=20, t=40, b=20)
    )
    st.plotly_chart(fig, use_container_width=True)

with tab_backtest:
    st.subheader(f"Vectorized 50/200 Crossover Backtest — {active_sym}")
    bt_col1, bt_col2 = st.columns([1, 3])
    with bt_col1:
        ma_choice = st.radio("Select Crossover Engine:", ["EMA (50 / 200)", "SMA (50 / 200)"])
        ma_key = "EMA" if "EMA" in ma_choice else "SMA"
        res = run_crossover_backtest(df_sym, ma_type=ma_key)

        if res:
            st.metric("Strategy Return", f"{res['Total Strategy Return (%)']:+.2f}%", f"{res['Outperformance (%)']:+.2f}% vs Buy & Hold")
            st.metric("Buy & Hold Return", f"{res['Buy & Hold Return (%)']:+.2f}%")
            st.metric("Sharpe Ratio", f"{res['Sharpe Ratio']}")
            st.metric("Max Drawdown", f"{res['Max Drawdown (%)']}%")
            st.metric("Total Regime Trades", f"{res['Total Regime Switches']}")

    with bt_col2:
        if res:
            bt_df = res["df"]
            eq_fig = go.Figure()
            eq_fig.add_trace(go.Scatter(x=bt_df.index, y=bt_df["Strategy_Equity"], name=f"50/200 {ma_key} Strategy", line=dict(color="#22C55E", width=2.5)))
            eq_fig.add_trace(go.Scatter(x=bt_df.index, y=bt_df["BuyHold_Equity"], name="Buy & Hold Benchmark", line=dict(color="#94A3B8", width=1.8, dash="dot")))
            eq_fig.update_layout(
                title=f"Growth of $1.00 — {active_sym} ({ma_key} 50/200 Trend Following vs. Buy & Hold)",
                yaxis_title="Portfolio Multiple ($)", template="plotly_dark", height=450, hovermode="x unified"
            )
            st.plotly_chart(eq_fig, use_container_width=True)