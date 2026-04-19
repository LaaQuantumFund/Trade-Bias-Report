import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

TWELVEDATA_API_KEY = os.getenv("TWELVEDATA_API_KEY", "")
OBSIDIAN_DAILY_PATH = Path(
    os.getenv("OBSIDIAN_DAILY_PATH", "~/Brain/Calendar/Daily-Bias")
).expanduser()
OBSIDIAN_WEEKLY_PATH = Path(
    os.getenv("OBSIDIAN_WEEKLY_PATH", "~/Brain/Calendar/Weekly-Bias")
).expanduser()

# スクレイピング対象の銘柄設定
INSTRUMENTS = {
    "DXY": {
        "myfxbook_slug": None,  # DXYはFX銘柄ではないため対象外
        "ig_slug": "usd-index",
        "fxssi": True,
    },
    "XAUUSD": {
        "myfxbook_slug": "XAUUSD",
        "ig_slug": "gold",
        "fxssi": True,
    },
    "USDJPY": {
        "myfxbook_slug": "USDJPY",
        "ig_slug": "usd-jpy",
        "fxssi": True,
    },
    "BTCUSD": {
        "myfxbook_slug": None,  # CoinGlass を代替使用
        "ig_slug": "bitcoin",
        "fxssi": False,
        "coinglass": True,
    },
}

# 2026年 FOMC 日程（開催日）
FOMC_DATES_2026 = [
    "2026-01-27",
    "2026-03-17",
    "2026-04-28",
    "2026-06-16",
    "2026-07-28",
    "2026-09-15",
    "2026-10-27",
    "2026-12-15",
]

# Playwright 設定
BROWSER_TIMEOUT = 30000  # ms
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)
