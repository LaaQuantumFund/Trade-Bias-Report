"""BTC ETF フロー スクレイパー

優先順:
1. Farside Investors (https://farside.co.uk/bitcoin-etf-flow-all-data/)
2. SoSoValue (https://sosovalue.com/assets/etf/us-btc-spot)
3. CoinGlass (https://www.coinglass.com/bitcoin-etf)

取得データ: ETF別（IBIT, FBTC, GBTC, その他）と日次合計、直近5営業日分
"""

from __future__ import annotations

import asyncio
import re
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

import requests
from playwright.async_api import async_playwright
from config import BROWSER_TIMEOUT, USER_AGENT

TARGET_ETFS = ["IBIT", "FBTC", "GBTC"]


def _scrape_farside() -> Optional[dict]:
    """Farside Investors からBTC ETFフローを取得する（requestsのみ）。"""
    url = "https://farside.co.uk/bitcoin-etf-flow-all-data/"
    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
        resp.raise_for_status()
        html = resp.text

        # HTMLテーブルをパース
        # テーブル内の行を取得
        table_match = re.search(r'<table[^>]*>(.*?)</table>', html, re.DOTALL | re.IGNORECASE)
        if not table_match:
            return None

        table_html = table_match.group(1)

        # ヘッダー行からETF名のインデックスを特定
        header_match = re.search(r'<tr[^>]*>(.*?)</tr>', table_html, re.DOTALL | re.IGNORECASE)
        if not header_match:
            return None

        header_cells = re.findall(r'<t[hd][^>]*>(.*?)</t[hd]>', header_match.group(1), re.DOTALL | re.IGNORECASE)
        header_cells = [re.sub(r'<[^>]+>', '', c).strip() for c in header_cells]

        etf_indices = {}
        total_idx = None
        for i, h in enumerate(header_cells):
            for etf in TARGET_ETFS:
                if etf in h.upper():
                    etf_indices[etf] = i
            if "total" in h.lower() or "Total" in h:
                total_idx = i

        # データ行を取得（直近5行）
        data_rows = re.findall(r'<tr[^>]*>(.*?)</tr>', table_html, re.DOTALL | re.IGNORECASE)
        # ヘッダー行をスキップし、最後の数行を取得（日付の新しい順）
        data_rows = data_rows[1:]  # ヘッダー除去

        daily_flows = []
        for row_html in reversed(data_rows[-10:]):
            cells = re.findall(r'<td[^>]*>(.*?)</td>', row_html, re.DOTALL | re.IGNORECASE)
            cells = [re.sub(r'<[^>]+>', '', c).strip() for c in cells]

            if not cells or len(cells) < 3:
                continue

            # 最初のセルが日付
            date_str = cells[0].strip()
            if not re.match(r'\d', date_str):
                continue

            day_data = {"date": date_str, "flows": {}, "total": None}

            for etf, idx in etf_indices.items():
                if idx < len(cells):
                    val = cells[idx].strip()
                    day_data["flows"][etf] = _parse_flow_value(val)

            if total_idx and total_idx < len(cells):
                day_data["total"] = _parse_flow_value(cells[total_idx].strip())

            # 計算で合計を出す
            if day_data["total"] is None:
                known = [v for v in day_data["flows"].values() if v is not None]
                if known:
                    day_data["total"] = sum(known)

            if day_data["flows"] or day_data["total"] is not None:
                daily_flows.append(day_data)

            if len(daily_flows) >= 5:
                break

        if daily_flows:
            return {
                "source": "Farside Investors",
                "daily_flows": daily_flows,
                "error": None,
            }

    except Exception as e:
        print(f"  [WARN] Farside: {e}")

    return None


async def _scrape_sosovalue() -> Optional[dict]:
    """SoSoValue からBTC ETFフローを取得する。"""
    url = "https://sosovalue.com/assets/etf/us-btc-spot"
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(user_agent=USER_AGENT, ignore_https_errors=True)
            page = await context.new_page()

            await page.goto(url, timeout=BROWSER_TIMEOUT, wait_until="domcontentloaded")
            await page.wait_for_timeout(8000)

            body_text = await page.inner_text("body")

            daily_flows = []

            # テーブルからETFフローデータを取得
            rows = await page.query_selector_all('table tr, [class*="table"] [class*="row"]')
            for row in rows:
                try:
                    text = await row.inner_text()
                    # 日付パターンを探す
                    date_match = re.search(r'(\d{4}[-/]\d{2}[-/]\d{2}|\w+\s+\d{1,2},?\s*\d{4})', text)
                    if not date_match:
                        continue

                    day_data = {"date": date_match.group(1), "flows": {}, "total": None}

                    for etf in TARGET_ETFS:
                        pattern = rf'{etf}.*?([-+]?\$?[\d,.]+\s*[MB]?)'
                        match = re.search(pattern, text, re.IGNORECASE)
                        if match:
                            day_data["flows"][etf] = _parse_flow_value(match.group(1))

                    # 合計
                    total_match = re.search(r'(?:Total|Net).*?([-+]?\$?[\d,.]+\s*[MB]?)', text, re.IGNORECASE)
                    if total_match:
                        day_data["total"] = _parse_flow_value(total_match.group(1))

                    if day_data["flows"] or day_data["total"] is not None:
                        daily_flows.append(day_data)

                except Exception:
                    continue

            await browser.close()

            if daily_flows:
                return {
                    "source": "SoSoValue",
                    "daily_flows": daily_flows[:5],
                    "error": None,
                }

    except Exception as e:
        print(f"  [WARN] SoSoValue: {e}")

    return None


async def _scrape_coinglass_etf() -> Optional[dict]:
    """CoinGlass からBTC ETFフローを取得する。"""
    url = "https://www.coinglass.com/bitcoin-etf"
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(user_agent=USER_AGENT, ignore_https_errors=True)
            page = await context.new_page()

            await page.goto(url, timeout=BROWSER_TIMEOUT, wait_until="domcontentloaded")
            await page.wait_for_timeout(8000)

            body_text = await page.inner_text("body")

            daily_flows = []

            # テーブルからデータを取得
            rows = await page.query_selector_all('table tr')
            for row in rows:
                try:
                    text = await row.inner_text()
                    date_match = re.search(r'(\d{4}[-/]\d{2}[-/]\d{2}|\w+\s+\d{1,2})', text)
                    if not date_match:
                        continue

                    day_data = {"date": date_match.group(1), "flows": {}, "total": None}

                    # 数値を抽出
                    values = re.findall(r'([-+]?[\d,.]+)', text)
                    if len(values) >= 2:
                        day_data["total"] = _parse_flow_value(values[-1])

                    if day_data["total"] is not None:
                        daily_flows.append(day_data)

                except Exception:
                    continue

            await browser.close()

            if daily_flows:
                return {
                    "source": "CoinGlass",
                    "daily_flows": daily_flows[:5],
                    "error": None,
                }

    except Exception as e:
        print(f"  [WARN] CoinGlass ETF: {e}")

    return None


def _parse_flow_value(text: str) -> Optional[float]:
    """フロー値のテキストを数値(百万USD)に変換する。"""
    if not text or text in ("-", "N/A", ""):
        return None
    text = text.strip().replace("$", "").replace(",", "").replace(" ", "")

    negative = text.startswith("-") or text.startswith("(")
    text = text.lstrip("-+(").rstrip(")")

    multiplier = 1.0
    if text.upper().endswith("B"):
        multiplier = 1000.0
        text = text[:-1]
    elif text.upper().endswith("M"):
        text = text[:-1]

    try:
        val = float(text) * multiplier
        return -val if negative else val
    except ValueError:
        return None


async def scrape_btc_etf() -> dict:
    """BTC ETFフローデータを取得する。優先順にソースを試行。

    Returns:
        {
            "source": str,
            "daily_flows": [
                {
                    "date": str,
                    "flows": {"IBIT": float, "FBTC": float, "GBTC": float},
                    "total": float | None,
                }
            ],
            "error": str | None,
        }
    """
    # 1. Farside (requests のみ)
    print("  BTC ETF: Farside Investors を試行中...")
    data = _scrape_farside()
    if data and data.get("daily_flows"):
        print(f"  [OK]    BTC ETF: Farside ({len(data['daily_flows'])}日分)")
        return data

    # 2. SoSoValue
    print("  BTC ETF: SoSoValue を試行中...")
    data = await _scrape_sosovalue()
    if data and data.get("daily_flows"):
        print(f"  [OK]    BTC ETF: SoSoValue ({len(data['daily_flows'])}日分)")
        return data

    # 3. CoinGlass
    print("  BTC ETF: CoinGlass を試行中...")
    data = await _scrape_coinglass_etf()
    if data and data.get("daily_flows"):
        print(f"  [OK]    BTC ETF: CoinGlass ({len(data['daily_flows'])}日分)")
        return data

    return {
        "source": "取得不可",
        "daily_flows": [],
        "error": "全ソースからの取得に失敗",
    }


if __name__ == "__main__":
    data = asyncio.run(scrape_btc_etf())
    print(f"\n--- BTC ETF ({data['source']}) ---")
    if data["error"]:
        print(f"  Error: {data['error']}")
    for day in data.get("daily_flows", []):
        flows_str = ", ".join(f"{k}: {v}" for k, v in day.get("flows", {}).items())
        print(f"  {day['date']}: {flows_str} | Total: {day.get('total')}")
