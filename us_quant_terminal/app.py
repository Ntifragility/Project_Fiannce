import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import json
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse
import pandas as pd

from src.config import ALPACA_API_KEY, ALPACA_SECRET_KEY, load_watchlists
from src.data_provider import USStockDataProvider
from src.indicators import enrich_indicators
from src.backtester import compare_all_ma_families

PORT = 8050
UI_DIR = BASE_DIR / "ui"
SERIES_KEYS = [
    "SMA_50", "SMA_200", "EMA_50", "EMA_200",
    "VWMA_50", "VWMA_200", "HMA_50", "HMA_200", "KAMA_50"
]

# Reuse a single client connection across requests
PROVIDER = USStockDataProvider(ALPACA_API_KEY, ALPACA_SECRET_KEY)


def build_tv_series(edf: pd.DataFrame, signal_family: str = "EMA") -> dict:
    df = edf.copy()
    df["time"] = df.index.strftime("%Y-%m-%d")

    candles = df[["time", "open", "high", "low", "close"]].to_dict("records")

    vol_df = pd.DataFrame({
        "time": df["time"],
        "value": df["volume"].astype(float),
        "color": ["rgba(38, 166, 154, 0.32)" if c >= o else "rgba(239, 83, 80, 0.32)" for c, o in zip(df["close"], df["open"])]
    })
    volumes = vol_df.to_dict("records")

    ma_lines = {}
    for k in SERIES_KEYS:
        valid = df[["time", k]].dropna()
        ma_lines[k] = [
            {"time": t, "value": round(float(v), 2)}
            for t, v in zip(valid["time"], valid[k])
        ]

    sp_valid = df[["time", "EMA_Spread_Pct"]].dropna()
    spread_osc = [
        {
            "time": t,
            "value": round(float(v), 2),
            "color": "rgba(38, 166, 154, 0.65)" if v >= 0 else "rgba(239, 83, 80, 0.65)"
        }
        for t, v in zip(sp_valid["time"], sp_valid["EMA_Spread_Pct"])
    ]

    cross_col = f"{signal_family}_Cross" if f"{signal_family}_Cross" in df.columns else "EMA_Cross"
    crosses = df[df[cross_col] != 0]
    markers = [
        {
            "time": row["time"],
            "position": "belowBar" if row[cross_col] == 1 else "aboveBar",
            "color": "#26A69A" if row[cross_col] == 1 else "#EF5350",
            "shape": "arrowUp" if row[cross_col] == 1 else "arrowDown",
            "text": f"{signal_family} {'Golden' if row[cross_col] == 1 else 'Death'} Cross"
        }
        for _, row in crosses.iterrows()
    ]

    return {
        "candles": candles,
        "volumes": volumes,
        "ma_lines": ma_lines,
        "spread": spread_osc,
        "markers": markers
    }

def fetch_terminal_state(
    sector: str, active_sym: str, tf: str, sig_fam: str,
    start_str: str, end_str: str, custom_str: str
):
    watchlists = load_watchlists()
    sectors = list(watchlists.keys())
    if not sector or sector not in watchlists:
        sector = sectors[0]

    symbols = list(watchlists[sector])
    if custom_str:
        for t in custom_str.split(","):
            clean = t.strip().upper()
            if clean and clean not in symbols:
                symbols.append(clean)

    if not active_sym or active_sym not in symbols:
        active_sym = symbols[0]

    print(f"[Sync] Sector={sector} | Active={active_sym} | Window: {start_str or 'ALL'} -> {end_str or 'NOW'}")

    raw_map = PROVIDER.fetch_bars(
        symbols, timeframe_str=tf, start_str=start_str, end_str=end_str, use_cache=True
    )

    scanner_rows = []
    tv_data = {}
    bt_comparison = []

    for sym, df in raw_map.items():
        # 1. Compute 50 & 200 MAs on full history (including the 350-day warmup buffer)
        edf = enrich_indicators(df)
        if edf.empty:
            continue

        # 2. Slice strictly to the user's selected Start and End dates using YYYY-MM-DD strings
        date_strings = edf.index.strftime("%Y-%m-%d")
        mask = pd.Series(True, index=edf.index)
        if start_str:
            mask &= (date_strings >= start_str)
        if end_str:
            mask &= (date_strings <= end_str)

        edf = edf.loc[mask]
        if edf.empty:
            continue

        last = edf.iloc[-1]
        prev = edf.iloc[-2] if len(edf) > 1 else last
        chg_pct = ((last["close"] - prev["close"]) / prev["close"]) * 100

        scanner_rows.append({
            "ticker": sym,
            "close": round(float(last["close"]), 2),
            "chg": round(float(chg_pct), 2),
            "spread": round(float(last["EMA_Spread_Pct"]), 2) if pd.notna(last["EMA_Spread_Pct"]) else 0.0,
            "score": int(last["Trend_Score"]),
        })

        if sym == active_sym:
            tv_data = build_tv_series(edf, signal_family=sig_fam)
            bt_comparison = compare_all_ma_families(edf)

    return {
        "sectors": sectors,
        "active_sector": sector,
        "symbols": symbols,
        "active_sym": active_sym,
        "timeframe": tf,
        "sig_fam": sig_fam,
        "scanner": scanner_rows,
        "tv": tv_data,
        "bt_comparison": bt_comparison,
    }


class QuantServer(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/state":
            qs = parse_qs(parsed.query)
            payload = fetch_terminal_state(
                sector=qs.get("sector", [""])[0],
                active_sym=qs.get("active", [""])[0],
                tf=qs.get("tf", ["1Day"])[0],
                sig_fam=qs.get("sig", ["EMA"])[0],
                start_str=qs.get("start", [""])[0],
                end_str=qs.get("end", [""])[0],
                custom_str=qs.get("custom", [""])[0],
            )
            self._send(200, "application/json", json.dumps(payload).encode("utf-8"))
        elif parsed.path == "/ui/styles.css":
            self._send(200, "text/css", (UI_DIR / "styles.css").read_bytes())
        elif parsed.path == "/ui/terminal.js":
            self._send(200, "application/javascript", (UI_DIR / "terminal.js").read_bytes())
        else:
            self._send(200, "text/html", (UI_DIR / "index.html").read_bytes())

    def _send(self, code: int, mime: str, body: bytes):
        self.send_response(code)
        self.send_header("Content-Type", mime)
        # Prevents Chrome from caching old JS/CSS files
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        return


if __name__ == "__main__":
    url = f"http://127.0.0.1:{PORT}"
    print(f"⚡ Alpaca Quant MA Engine running at {url} — Press Ctrl+C in terminal to stop.")
    webbrowser.open(url)
    HTTPServer(("127.0.0.1", PORT), QuantServer).serve_forever()