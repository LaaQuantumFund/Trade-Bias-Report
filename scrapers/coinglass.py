"""CoinGlass Long/Short Ratio & Funding Rate スクレイパー

対象URL: https://www.coinglass.com/LongShortRatio
取得データ: Long/Short Ratio, Funding Rate
"""

import asyncio
import re
from playwright.async_api import async_playwright
from config import BROWSER_TIMEOUT, USER_AGENT


async def scrape_coinglass() -> dict:
    result = {
        "source": "CoinGlass",
        "symbol": "BTCUSD",
        "long_pct": None,
        "short_pct": None,
        "funding_rate": None,
        "error": None,
    }

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(user_agent=USER_AGENT)

            # --- Long/Short Ratio ---
            page = await context.new_page()
            await page.goto(
                "https://www.coinglass.com/LongShortRatio",
                timeout=BROWSER_TIMEOUT,
                wait_until="domcontentloaded",
            )
            await page.wait_for_timeout(8000)

            body_text = await page.inner_text("body")

            # CoinGlassのテーブル形式:
            # "BTC\t$XXXXX\t+X.XX%\t1.876\n65.23%\n34.77%"
            # ランキングテーブルからBTCの行を探す
            btc_row = re.search(
                r'BTC\s+\$[\d,.]+\s+[+-]?[\d.]+%\s+([\d.]+)\s+([\d.]+)%\s+([\d.]+)%',
                body_text,
            )
            if btc_row:
                result["long_short_ratio"] = float(btc_row.group(1))
                result["long_pct"] = float(btc_row.group(2))
                result["short_pct"] = float(btc_row.group(3))
            else:
                # フォールバック: 4H Long/Short Volume からの取得
                vol_long = re.search(r'(\d+(?:\.\d+)?)\s*%\s*\n\s*4H Long Volume', body_text)
                vol_short = re.search(r'(\d+(?:\.\d+)?)\s*%\s*\n\s*4H Short Volume', body_text)
                if vol_long and vol_short:
                    result["long_pct"] = float(vol_long.group(1))
                    result["short_pct"] = float(vol_short.group(1))

            # --- Funding Rate ---
            page2 = await context.new_page()
            await page2.goto(
                "https://www.coinglass.com/FundingRate",
                timeout=BROWSER_TIMEOUT,
                wait_until="domcontentloaded",
            )
            await page2.wait_for_timeout(8000)

            funding_text = await page2.inner_text("body")

            # OI-Weighted Funding Rate を取得
            oi_weighted = re.search(
                r'BTC OI-Weighted Funding Rate\s*\n?\s*(-?[\d.]+)%',
                funding_text,
            )
            if oi_weighted:
                result["funding_rate"] = float(oi_weighted.group(1))
            else:
                # フォールバック: ヘッダー部分の BTC OI-Weighted Funding Rate
                header_fr = re.search(
                    r'(-?[\d.]+)%\s*\n?\s*BTC OI-Weighted Funding Rate',
                    funding_text,
                )
                if header_fr:
                    result["funding_rate"] = float(header_fr.group(1))

            if result["long_pct"] is None and result["funding_rate"] is None:
                result["raw_text"] = body_text[:2000] + "\n---FUNDING---\n" + funding_text[:2000]
                result["error"] = "セレクタでの取得失敗。raw_textにページテキストを格納済み。"

            await browser.close()

    except Exception as e:
        result["error"] = f"ページ取得失敗: {str(e)}"

    return result


if __name__ == "__main__":
    data = asyncio.run(scrape_coinglass())
    for k, v in data.items():
        if k != "raw_text":
            print(f"  {k}: {v}")
