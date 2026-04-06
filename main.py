"""ICT Daily Bias Report — メインオーケストレーター

実行方法:
    python main.py              # 通常実行
    python main.py --scrape-only  # データ取得のみ（レポート生成しない）
    python main.py --skip-scrape  # スクレイピングスキップ（手動データで生成）
"""

import asyncio
import sys
import json
from datetime import datetime
from pathlib import Path

from config import INSTRUMENTS, OBSIDIAN_DAILY_PATH, OBSIDIAN_WEEKLY_PATH
from scrapers.myfxbook import scrape_myfxbook
from scrapers.fxssi import scrape_fxssi
from scrapers.ig_sentiment import scrape_ig_sentiment
from scrapers.coinglass import scrape_coinglass
from scrapers.cot import fetch_cot_data
from scrapers.twelvedata import fetch_price_data
from generate_report import generate_report, load_master_prompt


async def collect_all_data(weekly: bool = False) -> dict:
    """MyFXBook優先でデータを取得し、失敗銘柄はFXSSI→IGの順でフォールバックする。
    weekly=True のときは COT データも取得する。
    """
    print("[1/4] データ取得を開始...")

    results = {
        "timestamp": datetime.now().isoformat(),
        "price_data": None,  # Twelve Data API
        "retail_sentiment": {},  # 銘柄ごとに1ソースのみ格納
        "coinglass": {},
        "cot": None,  # ウィークリー時のみ使用
    }

    # --- Twelve Data: 価格データ取得 ---
    print("  Twelve Data: 価格データ取得中...")
    try:
        price_text = fetch_price_data()
        results["price_data"] = price_text
        print("  [OK]    Twelve Data: 価格データ取得完了")
    except Exception as e:
        results["price_data"] = f"Twelve Data 取得不可（{e}）"
        print(f"  [ERROR] Twelve Data: {e}")

    # --- Phase 1: MyFXBook + CoinGlass を並列取得 ---
    myfxbook_targets = [(sym, cfg["myfxbook_slug"]) for sym, cfg in INSTRUMENTS.items() if cfg.get("myfxbook_slug")]
    phase1_tasks = [("myfxbook", sym, scrape_myfxbook(slug)) for sym, slug in myfxbook_targets]
    phase1_tasks.append(("coinglass", "BTCUSD", scrape_coinglass()))

    print(f"  Phase 1: {len(phase1_tasks)} タスクを並列実行中（MyFXBook + CoinGlass）...")
    phase1_results = await asyncio.gather(*[t[2] for t in phase1_tasks], return_exceptions=True)

    failed_symbols = []
    for i, (source, symbol, _) in enumerate(phase1_tasks):
        res = phase1_results[i]
        if source == "coinglass":
            if isinstance(res, Exception):
                results["coinglass"]["BTCUSD"] = {"error": str(res)}
                print(f"  [ERROR] coinglass/BTCUSD: {res}")
            else:
                results["coinglass"]["BTCUSD"] = res
                print(f"  [WARN]  coinglass/BTCUSD: {res['error']}" if res.get("error") else f"  [OK]    coinglass/BTCUSD")
        else:
            # MyFXBook: long_pct が取得できていれば成功
            ok = not isinstance(res, Exception) and isinstance(res, dict) and res.get("long_pct") is not None
            if ok:
                results["retail_sentiment"][symbol] = {**res, "_fallback": None}
                print(f"  [OK]    myfxbook/{symbol}")
            else:
                err = str(res) if isinstance(res, Exception) else (res.get("error") if isinstance(res, dict) else "不明")
                print(f"  [WARN]  myfxbook/{symbol}: {err} → フォールバック予定")
                failed_symbols.append(symbol)

    # --- Phase 2: 失敗銘柄のフォールバック（FXSSI → IG）---
    if failed_symbols:
        print(f"  Phase 2: フォールバック取得中（{failed_symbols}）...")
        fxssi_result = await scrape_fxssi()
        fxssi_data = fxssi_result.get("data", {}) if not fxssi_result.get("error") else {}

        ig_needed = []
        for symbol in failed_symbols:
            if symbol in fxssi_data:
                d = fxssi_data[symbol]
                results["retail_sentiment"][symbol] = {
                    "source": "FXSSI",
                    "symbol": symbol,
                    "long_pct": d.get("buy_pct"),
                    "short_pct": d.get("sell_pct"),
                    "avg_long_entry": None,
                    "avg_short_entry": None,
                    "_fallback": "FXSSI",
                    "error": None,
                }
                print(f"  [OK]    fxssi/{symbol} (フォールバック)")
            else:
                ig_needed.append(symbol)
                print(f"  [WARN]  fxssi/{symbol}: データなし → IG試行")

        if ig_needed:
            ig_results = await asyncio.gather(*[scrape_ig_sentiment(sym) for sym in ig_needed], return_exceptions=True)
            for i, symbol in enumerate(ig_needed):
                res = ig_results[i]
                ok = not isinstance(res, Exception) and isinstance(res, dict) and res.get("long_pct") is not None
                if ok:
                    results["retail_sentiment"][symbol] = {**res, "_fallback": "IG"}
                    print(f"  [OK]    ig/{symbol} (フォールバック)")
                else:
                    err = str(res) if isinstance(res, Exception) else (res.get("error") if isinstance(res, dict) else "取得不可")
                    results["retail_sentiment"][symbol] = {
                        "source": "IG",
                        "symbol": symbol,
                        "long_pct": None,
                        "short_pct": None,
                        "_fallback": "IG",
                        "error": err,
                    }
                    print(f"  [ERROR] ig/{symbol}: {err}")

    # --- COT データ取得（ウィークリーのみ）---
    if weekly:
        print("  COT: CFTC APIからデータ取得中...")
        try:
            cot = fetch_cot_data()
            results["cot"] = cot
            if cot.get("error"):
                print(f"  [WARN]  COT: 一部エラー: {cot['error']}")
            else:
                print(f"  [OK]    COT: Report Date {cot['report_date']}")
        except Exception as e:
            results["cot"] = {"text": None, "error": str(e)}
            print(f"  [ERROR] COT: {e}")

    return results


def format_scraped_data(data: dict) -> str:
    """取得データをClaude APIに渡すテキスト形式に整形する。
    リテールセンチメントは銘柄ごとに1ソースのみ表示する。
    """
    lines = []
    lines.append(f"データ取得日時: {data['timestamp']}")
    lines.append("")

    # --- 価格データ（Twelve Data API）---
    price_data = data.get("price_data")
    if price_data:
        lines.append(price_data)
        lines.append("")

    # --- リテールセンチメント（銘柄ごとに1ソース）---
    lines.append("### リテールポジション (Retail Sentiment)")
    for symbol, d in data.get("retail_sentiment", {}).items():
        if not isinstance(d, dict):
            lines.append(f"- {symbol}: 取得不可")
            continue

        source = d.get("source", "不明")
        fallback = d.get("_fallback")
        long_pct = d.get("long_pct")
        short_pct = d.get("short_pct")

        if long_pct is not None:
            line = f"- {symbol} ({source}): Long {long_pct}% / Short {short_pct}%"
            if d.get("avg_long_entry"):
                line += f", 平均ロング {d['avg_long_entry']:,.4g}"
            lines.append(line)
            if fallback:
                lines.append(f"  ※ MyFXBook取得不可のため{source}にフォールバック")
        else:
            err = d.get("error", "取得不可")
            lines.append(f"- {symbol}: 取得不可（{err}）")
    lines.append("")

    # --- CoinGlass ---
    lines.append("### CoinGlass (BTCUSD)")
    cg = data.get("coinglass", {}).get("BTCUSD", {})
    if isinstance(cg, dict):
        if cg.get("long_short_ratio") is not None:
            lines.append(f"- Long/Short Ratio: {cg['long_short_ratio']}")
        if cg.get("long_pct") is not None:
            lines.append(f"- Long/Short: {cg['long_pct']}% / {cg['short_pct']}%")
        if cg.get("funding_rate") is not None:
            lines.append(f"- Funding Rate: {cg['funding_rate']}%")
        if cg.get("error"):
            lines.append(f"- エラー: {cg['error']}")
    else:
        lines.append("- BTCUSD: 取得不可")

    # --- COT（ウィークリー時のみ）---
    cot = data.get("cot")
    if cot is not None:
        lines.append("")
        if cot.get("text"):
            lines.append(cot["text"])
        else:
            err = cot.get("error", "取得不可")
            lines.append(f"COTデータ取得不可（{err}）")

    return "\n".join(lines)


def save_report(report: str, scraped_data: dict, prefix: str = "Daily_Bias_Report", weekly: bool = False):
    """レポートをローカルとObsidian Vaultに保存する。"""
    today = datetime.now().strftime("%Y-%m-%d")
    filename = f"{prefix}_{today}.md"

    # ローカル保存
    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)
    local_path = output_dir / filename
    local_path.write_text(report, encoding="utf-8")
    print(f"  ローカル保存: {local_path}")

    # 取得データのJSON保存（デバッグ用）
    json_path = output_dir / f"scraped_data_{today}.json"
    # raw_text を除外してJSON保存
    clean_data = json.loads(json.dumps(scraped_data, default=str))
    for source in clean_data.values():
        if isinstance(source, dict):
            for symbol_data in source.values():
                if isinstance(symbol_data, dict):
                    symbol_data.pop("raw_text", None)
    json_path.write_text(json.dumps(clean_data, ensure_ascii=False, indent=2), encoding="utf-8")

    # Obsidian Vault に保存（Daily/Weekly で出力先を分ける）
    vault_path = OBSIDIAN_WEEKLY_PATH if weekly else OBSIDIAN_DAILY_PATH
    vault_path.mkdir(parents=True, exist_ok=True)
    obsidian_path = vault_path / filename
    obsidian_path.write_text(report, encoding="utf-8")
    print(f"  Obsidian保存: {obsidian_path}")


async def main():
    scrape_only = "--scrape-only" in sys.argv
    skip_scrape = "--skip-scrape" in sys.argv
    weekly = "--weekly" in sys.argv

    print("=" * 60)
    mode = "Weekly" if weekly else "Daily"
    print(f"ICT {mode} Bias Report Generator — {datetime.now().strftime('%Y/%m/%d %H:%M')}")
    print("=" * 60)

    # Step 1: データ取得
    if skip_scrape:
        print("[SKIP] スクレイピングをスキップ")
        scraped_data = {"timestamp": datetime.now().isoformat()}
        formatted_data = "（スクレイピングスキップ。Web検索でデータを取得してください。）"
    else:
        scraped_data = await collect_all_data(weekly=weekly)
        formatted_data = format_scraped_data(scraped_data)

    print(f"\n[2/4] 取得データサマリー:")
    print(formatted_data)

    if scrape_only:
        print("\n[DONE] --scrape-only モード。レポート生成をスキップ。")
        return

    # Step 2: マスタープロンプト読み込み
    prompt_path = "master_prompt_weekly.md" if weekly else "master_prompt.md"
    print(f"\n[3/4] マスタープロンプト読み込み（{prompt_path}）...")
    try:
        master_prompt = load_master_prompt(prompt_path)
        print(f"  読み込み完了（{len(master_prompt)} 文字）")
    except FileNotFoundError as e:
        print(f"  [ERROR] {e}")
        return

    # Step 3: レポート生成
    print(f"\n[4/4] Claude API ({__import__('config').CLAUDE_MODEL}) でレポート生成中...")
    try:
        report = generate_report(formatted_data, master_prompt)
        print(f"  生成完了（{len(report)} 文字）")
    except Exception as e:
        print(f"  [ERROR] レポート生成失敗: {e}")
        return

    # Step 4: 保存
    prefix = "Weekly_Bias_Report" if weekly else "Daily_Bias_Report"
    print(f"\n[SAVE] レポートを保存中...")
    save_report(report, scraped_data, prefix=prefix, weekly=weekly)

    print(f"\n{'=' * 60}")
    print("完了!")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    asyncio.run(main())
