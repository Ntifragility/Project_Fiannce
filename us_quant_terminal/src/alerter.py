import threading
import time
import urllib.request
from datetime import datetime
from src.config import NTFY_TOPIC, load_watchlists


class QuantAlertEngine:
    def __init__(self, provider):
        self.provider = provider
        self.interval_minutes = 15       # Default: scan every 15 mins (0 = Off)
        self.drop_threshold = -5.0       # Default: -5.0% drop
        self.alerted_today: set[str] = set()
        self.last_reset_day = datetime.now().strftime("%Y-%m-%d")
        self.last_scan_time = "Never"
        self.running = True

        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def send_ntfy(self, title: str, message: str, priority: str = "high"):
        if not NTFY_TOPIC:
            return False
        try:
            req = urllib.request.Request(
                f"https://ntfy.sh/{NTFY_TOPIC.strip()}",
                data=message.encode("utf-8"),
                headers={
                    "Title": title,
                    "Priority": priority,
                    "Tags": "rotating_light,chart_with_downwards_trend",
                },
                method="POST",
            )
            urllib.request.urlopen(req, timeout=6)
            return True
        except Exception as e:
            print(f"[ntfy Error] {e}")
            return False

    def scan_once(self) -> list[str]:
        """Runs 1 batched snapshot call across all unique tickers in watchlist.md."""
        today_str = datetime.now().strftime("%Y-%m-%d")
        if today_str != self.last_reset_day:
            self.alerted_today.clear()
            self.last_reset_day = today_str

        watchlists = load_watchlists()
        all_symbols = sorted(list({sym for syms in watchlists.values() for sym in syms}))
        if not all_symbols:
            return []

        snaps = self.provider.fetch_live_snapshots(all_symbols)
        self.last_scan_time = datetime.now().strftime("%H:%M:%S")
        triggered = []

        for sym, d in snaps.items():
            # Trigger if drop from yesterday's close OR drop from today's high <= threshold
            if d["chg_pct"] <= self.drop_threshold or d["flush_pct"] <= self.drop_threshold:
                if sym not in self.alerted_today:
                    self.alerted_today.add(sym)
                    triggered.append(sym)
                    title = f"ALERT: {sym} dropped {d['chg_pct']:+.2f}%"
                    msg = (
                        f"{sym} is trading at ${d['price']:.2f}\n"
                        f"• Day Change vs Prev Close: {d['chg_pct']:+.2f}% (${d['prev_close']:.2f})\n"
                        f"• Drawdown from Today's High: {d['flush_pct']:+.2f}% (${d['day_high']:.2f})\n"
                        f"• Threshold: {self.drop_threshold:.1f}%"
                    )
                    self.send_ntfy(title, msg, priority="high")

        print(f"[Alert Scanner {self.last_scan_time}] Checked {len(snaps)} stocks in 1 API call | Triggered: {triggered}")
        return triggered

    def _loop(self):
        while self.running:
            if self.interval_minutes > 0:
                try:
                    self.scan_once()
                except Exception as e:
                    print(f"[Scanner Error] {e}")
                # Sleep in 1-second ticks so changing the dropdown updates immediately
                for _ in range(self.interval_minutes * 60):
                    if not self.running or self.interval_minutes == 0:
                        break
                    time.sleep(1)
            else:
                time.sleep(2)