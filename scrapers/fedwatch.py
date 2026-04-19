"""CME FedWatch 確率スクレイパー

対象URL: https://www.cmegroup.com/markets/interest-rates/cme-fedwatch-tool.html
取得データ: 次回FOMC日、25bp利下げ確率、50bp利下げ確率、据え置き確率
JSレンダリングが必要なためPlaywrightを使用。
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


async def _scrape_investing_fedwatch() -> Optional[dict]:
    """Investing.com のFedWatch情報からフォールバック取得を試みる。"""
    url = "https://www.investing.com/central-banks/fed-rate-monitor"
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(user_agent=USER_AGENT, ignore_https_errors=True)
            page = await context.new_page()

            await page.goto(url, timeout=BROWSER_TIMEOUT, wait_until="domcontentloaded")
            await page.wait_for_timeout(5000)

            body_text = await page.inner_text("body")

            result = {
                "source": "Investing.com Fed Rate Monitor",
                "next_fomc_date": None,
                "cut_25bp_pct": None,
                "cut_50bp_pct": None,
                "hold_pct": None,
                "hike_25bp_pct": None,
                "raw_probabilities": None,
                "error": None,
            }

            # FOMC日の取得
            fomc_match = re.search(r'(\w+\s+\d{1,2},?\s*\d{4})', body_text)
            if fomc_match:
                result["next_fomc_date"] = fomc_match.group(1).strip()

            # 確率データ
            hold_match = re.search(r'(?:No\s*Change|Hold|Unchanged|Pause)\s*[-:=]?\s*(\d+(?:\.\d+)?)\s*%', body_text, re.IGNORECASE)
            if hold_match:
                result["hold_pct"] = float(hold_match.group(1))

            cut25_match = re.search(r'(?:25\s*(?:bp|bps)).*?(\d+(?:\.\d+)?)\s*%', body_text, re.IGNORECASE)
            if cut25_match:
                result["cut_25bp_pct"] = float(cut25_match.group(1))

            await browser.close()

            if result["hold_pct"] is not None or result["cut_25bp_pct"] is not None:
                return result

    except Exception as e:
        print(f"  [WARN] Investing.com FedWatch: {e}")

    return None


async def scrape_fedwatch() -> dict:
    """CME FedWatch からFOMC金利確率データを取得する。

    Returns:
        {
            "source": str,
            "next_fomc_date": str | None,
            "cut_25bp_pct": float | None,
            "cut_50bp_pct": float | None,
            "hold_pct": float | None,
            "hike_25bp_pct": float | None,
            "raw_probabilities": dict | None,
            "error": str | None,
        }
    """
    result = {
        "source": "CME FedWatch",
        "next_fomc_date": None,
        "cut_25bp_pct": None,
        "cut_50bp_pct": None,
        "hold_pct": None,
        "hike_25bp_pct": None,
        "raw_probabilities": None,
        "error": None,
    }

    url = "https://www.cmegroup.com/markets/interest-rates/cme-fedwatch-tool.html"

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=["--disable-http2"],
            )
            context = await browser.new_context(
                user_agent=USER_AGENT,
                extra_http_headers={
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.9",
                },
                ignore_https_errors=True,
            )
            page = await context.new_page()

            await page.goto(url, timeout=60000, wait_until="domcontentloaded")
            # FedWatch はJS重いので長めに待機
            await page.wait_for_timeout(10000)

            body_text = await page.inner_text("body")

            # 次回FOMC日を取得
            fomc_date_match = re.search(
                r'(?:Meeting Date|FOMC Meeting|Next Meeting)[:\s]*(\w+\s+\d{1,2},?\s*\d{4}|\d{1,2}\s+\w+\s+\d{4})',
                body_text, re.IGNORECASE
            )
            if fomc_date_match:
                result["next_fomc_date"] = fomc_date_match.group(1).strip()

            # テーブルからFOMC日と確率データを取得
            # CMEのページ構造は動的だが、通常テーブルに確率が表示される
            # パターン1: "XX.X%" 形式の確率値を探す
            probabilities = {}

            # テーブル行から確率データを探す
            table_rows = await page.query_selector_all('table tr, [class*="meeting"] [class*="row"], [class*="probability"]')
            for row in table_rows:
                try:
                    text = await row.inner_text()
                    pcts = re.findall(r'(\d+(?:\.\d+)?)\s*%', text)
                    if pcts and len(pcts) >= 1:
                        # 日付を探す
                        date_in_row = re.search(r'(\w{3,9}\s+\d{1,2})', text)
                        if date_in_row:
                            if not result["next_fomc_date"]:
                                result["next_fomc_date"] = date_in_row.group(1)
                except Exception:
                    continue

            # テキストベースのパースを試みる
            # パターン: "No Change XX.X%", "25bp Cut XX.X%", etc.
            hold_match = re.search(r'(?:No\s*Change|Hold|Unchanged|据え置き)\s*[-:=]?\s*(\d+(?:\.\d+)?)\s*%', body_text, re.IGNORECASE)
            if hold_match:
                result["hold_pct"] = float(hold_match.group(1))

            cut25_match = re.search(r'(?:25\s*(?:bp|bps)\s*(?:Cut|Decrease|Lower))\s*[-:=]?\s*(\d+(?:\.\d+)?)\s*%', body_text, re.IGNORECASE)
            if not cut25_match:
                cut25_match = re.search(r'(\d+(?:\.\d+)?)\s*%\s*[-–]?\s*25\s*(?:bp|bps)\s*(?:Cut|Decrease|Lower)', body_text, re.IGNORECASE)
            if cut25_match:
                result["cut_25bp_pct"] = float(cut25_match.group(1))

            cut50_match = re.search(r'(?:50\s*(?:bp|bps)\s*(?:Cut|Decrease|Lower))\s*[-:=]?\s*(\d+(?:\.\d+)?)\s*%', body_text, re.IGNORECASE)
            if not cut50_match:
                cut50_match = re.search(r'(\d+(?:\.\d+)?)\s*%\s*[-–]?\s*50\s*(?:bp|bps)\s*(?:Cut|Decrease|Lower)', body_text, re.IGNORECASE)
            if cut50_match:
                result["cut_50bp_pct"] = float(cut50_match.group(1))

            hike_match = re.search(r'(?:25\s*(?:bp|bps)\s*(?:Hike|Increase|Raise))\s*[-:=]?\s*(\d+(?:\.\d+)?)\s*%', body_text, re.IGNORECASE)
            if hike_match:
                result["hike_25bp_pct"] = float(hike_match.group(1))

            # チャートの値を取得する試み（barやsvg等の内部テキスト）
            chart_texts = await page.query_selector_all('[class*="chart"] text, [class*="bar"] span, [class*="prob"] span')
            raw_probs = []
            for el in chart_texts:
                try:
                    t = await el.inner_text()
                    pct_m = re.search(r'(\d+(?:\.\d+)?)\s*%', t)
                    if pct_m:
                        raw_probs.append(float(pct_m.group(1)))
                except Exception:
                    continue

            if raw_probs:
                result["raw_probabilities"] = raw_probs

            # 何も取得できなかった場合
            if all(v is None for v in [result["hold_pct"], result["cut_25bp_pct"], result["cut_50bp_pct"]]):
                # body_textからすべての確率値を抽出
                all_pcts = re.findall(r'(\d+(?:\.\d+)?)\s*%', body_text)
                if all_pcts:
                    result["raw_probabilities"] = [float(p) for p in all_pcts[:20]]

                result["raw_text"] = body_text[:5000]
                result["error"] = "確率データの自動パース失敗。raw_textにページテキストを格納済み。"

            await browser.close()

    except Exception as e:
        result["error"] = f"CME取得失敗: {str(e)}"

    # CME失敗時のフォールバック: Investing.com
    if all(v is None for v in [result["hold_pct"], result["cut_25bp_pct"], result["cut_50bp_pct"]]):
        print("  FedWatch: Investing.com フォールバック試行中...")
        fallback = await _scrape_investing_fedwatch()
        if fallback:
            print(f"  [OK]    FedWatch: Investing.com から取得")
            return fallback

    return result


if __name__ == "__main__":
    data = asyncio.run(scrape_fedwatch())
    print("\n--- FedWatch ---")
    for k, v in data.items():
        if k not in ("raw_text", "raw_probabilities"):
            print(f"  {k}: {v}")
    if data.get("raw_probabilities"):
        print(f"  raw_probabilities: {data['raw_probabilities'][:10]}")
