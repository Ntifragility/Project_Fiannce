import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=BASE_DIR / ".env", override=True)

ALPACA_API_KEY = os.getenv("ALPACA_API_KEY") or os.getenv("api_key")
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY") or os.getenv("secret_key")
NTFY_TOPIC = os.getenv("NTFY_TOPIC", "mvilla_quant_alerts_99482")

CACHE_DIR = BASE_DIR / "data_cache"
CACHE_DIR.mkdir(exist_ok=True)

WATCHLIST_FILE = BASE_DIR / "watchlist.md"


def load_watchlists() -> dict[str, list[str]]:
    """Reads watchlist.md dynamically so you can edit stocks without restarting Python."""
    if not WATCHLIST_FILE.exists():
        return {"Default": ["AAPL", "MSFT", "NVDA", "SPY"]}

    watchlists: dict[str, list[str]] = {}
    current_sector = None

    for raw_line in WATCHLIST_FILE.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#"):
            current_sector = line.lstrip("#").strip()
            watchlists[current_sector] = []
        elif current_sector:
            # Supports comma-separated ("AAPL, MSFT") or bulleted ("- AAPL") lines
            cleaned = line.lstrip("-*").strip()
            tickers = [t.strip().upper() for t in cleaned.split(",") if t.strip()]
            for t in tickers:
                if t not in watchlists[current_sector]:
                    watchlists[current_sector].append(t)

    return {k: v for k, v in watchlists.items() if v}