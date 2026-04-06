"""MyFXBook Sentiment スクレイパー

対象URL: https://www.myfxbook.com/community/outlook/{symbol}
取得データ: Long%, Short%, 平均ロングエントリー価格, 平均ショートエントリー価格
"""

import asyncio
from playwright.async_api import async_playwright
from config import BROWSER_TIMEOUT, USER_AGENT


async def scrape_myfxbook(symbol: str) -> dict:
    """MyFXBookからセンチメントデータを取得する。

    Args:
        symbol: 銘柄名 (例: "XAUUSD", "USDJPY")

    Returns:
        {
            "source": "MyFXBook",
            "symbol": str,
            "long_pct": float | None,
            "short_pct": float | None,
            "avg_long_entry": float | None,
            "avg_short_entry": float | None,
            "error": str | None,
        }
    """
    result = {
        "source": "MyFXBook",
        "symbol": symbol,
        "long_pct": None,
        "short_pct": None,
        "avg_long_entry": None,
        "avg_short_entry": None,
        "error": None,
    }

    url = f"https://www.myfxbook.com/community/outlook/{symbol}"

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(user_agent=USER_AGENT)
            page = await context.new_page()

            await page.goto(url, timeout=BROWSER_TIMEOUT, wait_until="domcontentloaded")

            # ページが完全にレンダリングされるまで待機
            await page.wait_for_timeout(5000)

            # --- Long/Short パーセンテージ & 平均エントリー価格取得 ---
            try:
                import re
                page_text = await page.inner_text("body")

                # MyFXBookのテキスト形式:
                # "XX of the forex traders are currently going short ... average price of YYYY,
                #  meanwhile XX of the forex traders are going long ... average price of YYYY"
                short_match = re.search(
                    r'(\d+)\s+of the forex traders are currently going short.*?'
                    r'average price of\s+([\d,.]+)',
                    page_text, re.DOTALL | re.IGNORECASE
                )
                long_match = re.search(
                    r'(\d+)\s+of the forex traders are (?:going|currently going) long.*?'
                    r'average price of\s+([\d,.]+)',
                    page_text, re.DOTALL | re.IGNORECASE
                )

                if short_match:
                    result["short_pct"] = float(short_match.group(1))
                    price_str = short_match.group(2).replace(",", "").rstrip(".")
                    result["avg_short_entry"] = float(price_str)
                if long_match:
                    result["long_pct"] = float(long_match.group(1))
                    price_str = long_match.group(2).replace(",", "").rstrip(".")
                    result["avg_long_entry"] = float(price_str)

                # フォールバック: テーブルから "Short XX %" / "Long XX %" を取得
                if result["short_pct"] is None:
                    table_short = re.search(r'Short\s+(\d+)\s*%', page_text)
                    table_long = re.search(r'Long\s+(\d+)\s*%', page_text)
                    if table_short:
                        result["short_pct"] = float(table_short.group(1))
                    if table_long:
                        result["long_pct"] = float(table_long.group(1))

            except Exception as e:
                result["error"] = f"パーセンテージ取得失敗: {str(e)}"

            # --- フォールバック: ページ全体のHTMLをAIに渡すための生テキスト ---
            if result["long_pct"] is None and result["short_pct"] is None:
                try:
                    # ページのメインコンテンツ部分のテキストを取得
                    main_text = await page.inner_text("main, #content, .container, body")
                    # 最初の3000文字だけ保持（トークン節約）
                    result["raw_text"] = main_text[:3000]
                    result["error"] = "セレクタでの取得失敗。raw_textにページテキストを格納済み。"
                except:
                    pass

            await browser.close()

    except Exception as e:
        result["error"] = f"ページ取得失敗: {str(e)}"

    return result


# テスト用
if __name__ == "__main__":
    async def test():
        for sym in ["XAUUSD", "USDJPY"]:
            data = await scrape_myfxbook(sym)
            print(f"\n--- {sym} ---")
            for k, v in data.items():
                if k != "raw_text":
                    print(f"  {k}: {v}")
    asyncio.run(test())
