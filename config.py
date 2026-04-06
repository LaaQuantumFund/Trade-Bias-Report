import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
OBSIDIAN_VAULT_PATH = Path(os.getenv("OBSIDIAN_VAULT_PATH", "./output")).expanduser()
OBSIDIAN_DAILY_PATH = Path(
    os.getenv(
        "OBSIDIAN_DAILY_PATH",
        "~/Library/Mobile Documents/iCloud~md~obsidian/Documents/Brain/ICT Daily Bias Report",
    )
).expanduser()
OBSIDIAN_WEEKLY_PATH = Path(
    os.getenv(
        "OBSIDIAN_WEEKLY_PATH",
        "~/Library/Mobile Documents/iCloud~md~obsidian/Documents/Brain/ICT Weekly Bias Report",
    )
).expanduser()
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-opus-4-6")

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

# Playwright 設定
BROWSER_TIMEOUT = 30000  # ms
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)
