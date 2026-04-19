"""US10Y (米国10年国債利回り) スクレイパー

優先順:
1. Investing.com (https://www.investing.com/rates-bonds/u.s.-10-year-bond-yield)
2. CNBC (https://www.cnbc.com/quotes/US10Y)

取得データ: 現在利回り、前日比
"""

from __future__ import annotations

import asyncio
import re
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from playwright.async_api import async_playwright
from config import BROWSER_TIMEOUT, USER_AGENT


async def _scrape_investing() -> Optional[dict]:
    """Investing.com からUS10Y利回りを取得する。"""
    url = "https://www.investing.com/rates-bonds/u.s.-10-year-bond-yield"
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(user_agent=USER_AGENT, ignore_https_errors=True)
            page = await context.new_page()

            await page.goto(url, timeout=BROWSER_TIMEOUT, wait_until="domcontentloaded")
            await page.wait_for_timeout(5000)

            result = {
                "source": "Investing.com",
                "yield_pct": None,
                "prev_close": None,
                "change": None,
                "change_pct": None,
            }

            # 現在利回り
            price_el = await page.query_selector('[data-test="instrument-price-last"]')
            if price_el:
                price_text = await price_el.inner_text()
                result["yield_pct"] = float(price_text.replace(",", "").replace("%", ""))

            # 前日終値
            body_text = await page.inner_text("body")
            prev_match = re.search(r'(?:Prev\.\s*Close|前日終値)[:\s]*([\d,.]+)', body_text, re.IGNORECASE)
            if prev_match:
                result["prev_close"] = float(prev_match.group(1).replace(",", ""))

            # 前日比
            change_el = await page.query_selector('[data-test="instrument-price-change"]')
            if change_el:
                change_text = await change_el.inner_text()
                result["change"] = float(change_text.replace(",", "").replace("+", ""))

            change_pct_el = await page.query_selector('[data-test="instrument-price-change-percent"]')
            if change_pct_el:
                pct_text = await change_pct_el.inner_text()
                pct_clean = re.sub(r'[()%\s]', '', pct_text)
                if pct_clean:
                    result["change_pct"] = float(pct_clean)

            await browser.close()

            if result["yield_pct"] is not None:
                if result["prev_close"] is None and result["change"] is not None:
                    result["prev_close"] = result["yield_pct"] - result["change"]
                if result["change"] is None and result["prev_close"] is not None:
                    result["change"] = result["yield_pct"] - result["prev_close"]
                return result

    except Exception as e:
        print(f"  [WARN] Investing.com US10Y: {e}")

    return None


async def _scrape_cnbc() -> Optional[dict]:
    """CNBC からUS10Y利回りを取得する。"""
    url = "https://www.cnbc.com/quotes/US10Y"
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(user_agent=USER_AGENT, ignore_https_errors=True)
            page = await context.new_page()

            await page.goto(url, timeout=BROWSER_TIMEOUT, wait_until="domcontentloaded")
            await page.wait_for_timeout(5000)

            result = {
                "source": "CNBC",
                "yield_pct": None,
                "prev_close": None,
                "change": None,
                "change_pct": None,
            }

            body_text = await page.inner_text("body")

            # CNBC の価格表示
            price_el = await page.query_selector('.QuoteStrip-lastPrice, .last-price, [class*="lastPrice"]')
            if price_el:
                price_text = await price_el.inner_text()
                val = re.search(r'([\d,.]+)', price_text)
                if val:
                    result["yield_pct"] = float(val.group(1).replace(",", ""))

            # テキストからフォールバック取得
            if result["yield_pct"] is None:
                yield_match = re.search(r'US\s*10[- ]?(?:Year|Y|yr).*?([\d,.]+)\s*%?', body_text, re.IGNORECASE)
                if yield_match:
                    result["yield_pct"] = float(yield_match.group(1).replace(",", ""))

            # 変動
            change_el = await page.query_selector('.QuoteStrip-changeDown, .QuoteStrip-changeUp, [class*="change"]')
            if change_el:
                change_text = await change_el.inner_text()
                vals = re.findall(r'([-+]?[\d,.]+)', change_text)
                if vals:
                    result["change"] = float(vals[0].replace(",", ""))
                if len(vals) >= 2:
                    result["change_pct"] = float(vals[1].replace(",", ""))

            # 前日終値
            prev_match = re.search(r'(?:Previous Close|Prev\.?\s*Close)[:\s]*([\d,.]+)', body_text, re.IGNORECASE)
            if prev_match:
                result["prev_close"] = float(prev_match.group(1).replace(",", ""))

            await browser.close()

            if result["yield_pct"] is not None:
                if result["prev_close"] is None and result["change"] is not None:
                    result["prev_close"] = result["yield_pct"] - result["change"]
                if result["change"] is None and result["prev_close"] is not None:
                    result["change"] = result["yield_pct"] - result["prev_close"]
                return result

    except Exception as e:
        print(f"  [WARN] CNBC US10Y: {e}")

    return None


async def scrape_us10y() -> dict:
    """US10Y利回りデータを取得する。

    Returns:
        {
            "source": str,
            "yield_pct": float | None,
            "prev_close": float | None,
            "change": float | None,
            "change_pct": float | None,
            "error": str | None,
        }
    """
    # 1. Investing.com
    print("  US10Y: Investing.com を試行中...")
    data = await _scrape_investing()
    if data and data.get("yield_pct") is not None:
        print(f"  [OK]    US10Y: Investing.com ({data['yield_pct']}%)")
        data["error"] = None
        return data

    # 2. CNBC
    print("  US10Y: CNBC を試行中...")
    data = await _scrape_cnbc()
    if data and data.get("yield_pct") is not None:
        print(f"  [OK]    US10Y: CNBC ({data['yield_pct']}%)")
        data["error"] = None
        return data

    return {
        "source": "取得不可",
        "yield_pct": None,
        "prev_close": None,
        "change": None,
        "change_pct": None,
        "error": "全ソースからの取得に失敗",
    }


if __name__ == "__main__":
    data = asyncio.run(scrape_us10y())
    print("\n--- US10Y ---")
    for k, v in data.items():
        print(f"  {k}: {v}")
