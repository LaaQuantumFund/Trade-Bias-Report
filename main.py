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

from config import INSTRUMENTS, OBSIDIAN_VAULT_PATH
from scrapers.myfxbook import scrape_myfxbook
from scrapers.fxssi import scrape_fxssi
from scrapers.ig_sentiment import scrape_ig_sentiment
from scrapers.coinglass import scrape_coinglass
from generate_report import generate_report, load_master_prompt


async def collect_all_data() -> dict:
    """全ソースからデータを並列取得する。"""
    print("[1/4] データ取得を開始...")

    results = {
        "timestamp": datetime.now().isoformat(),
        "myfxbook": {},
        "fxssi": {},
        "ig": {},
        "coinglass": {},
    }

    tasks = []

    # MyFXBook
    for symbol, cfg in INSTRUMENTS.items():
        if cfg.get("myfxbook_slug"):
            tasks.append(("myfxbook", symbol, scrape_myfxbook(cfg["myfxbook_slug"])))

    # IG Client Sentiment
    for symbol in INSTRUMENTS:
        tasks.append(("ig", symbol, scrape_ig_sentiment(symbol)))

    # CoinGlass (BTC のみ)
    tasks.append(("coinglass", "BTCUSD", scrape_coinglass()))

    # FXSSI (一括取得)
    tasks.append(("fxssi", "ALL", scrape_fxssi()))

    # 並列実行
    print(f"  {len(tasks)} 個のスクレイピングタスクを並列実行中...")
    coroutines = [t[2] for t in tasks]
    task_results = await asyncio.gather(*coroutines, return_exceptions=True)

    for i, (source, symbol, _) in enumerate(tasks):
        res = task_results[i]
        if isinstance(res, Exception):
            results[source][symbol] = {"error": str(res)}
            print(f"  [ERROR] {source}/{symbol}: {res}")
        else:
            results[source][symbol] = res
            error = res.get("error")
            if error:
                print(f"  [WARN]  {source}/{symbol}: {error}")
            else:
                print(f"  [OK]    {source}/{symbol}")

    return results


def format_scraped_data(data: dict) -> str:
    """取得データをClaude APIに渡すテキスト形式に整形する。"""
    lines = []
    lines.append(f"データ取得日時: {data['timestamp']}")
    lines.append("")

    # --- MyFXBook ---
    lines.append("### MyFXBook Sentiment")
    for symbol, d in data.get("myfxbook", {}).items():
        if isinstance(d, dict) and not d.get("error"):
            lines.append(f"- {d.get('symbol', symbol)}: "
                         f"Long {d.get('long_pct', '取得不可')}% / "
                         f"Short {d.get('short_pct', '取得不可')}%")
            if d.get("avg_long_entry"):
                lines.append(f"  平均ロングエントリー: {d['avg_long_entry']}")
            if d.get("avg_short_entry"):
                lines.append(f"  平均ショートエントリー: {d['avg_short_entry']}")
        else:
            err = d.get("error", "不明なエラー") if isinstance(d, dict) else str(d)
            lines.append(f"- {symbol}: 取得不可（{err}）")
    lines.append("")

    # --- FXSSI ---
    lines.append("### FXSSI Current Ratio")
    fxssi_all = data.get("fxssi", {}).get("ALL", {})
    fxssi_data = fxssi_all.get("data", {}) if isinstance(fxssi_all, dict) else {}
    if fxssi_data:
        for symbol, d in fxssi_data.items():
            lines.append(f"- {symbol}: Buy {d.get('buy_pct', '?')}% / Sell {d.get('sell_pct', '?')}%")
    else:
        err = fxssi_all.get("error", "取得不可") if isinstance(fxssi_all, dict) else "取得不可"
        lines.append(f"- 全銘柄: 取得不可（{err}）")
    lines.append("")

    # --- IG Client Sentiment ---
    lines.append("### IG Client Sentiment")
    for symbol, d in data.get("ig", {}).items():
        if isinstance(d, dict) and d.get("long_pct") is not None:
            lines.append(f"- {d.get('symbol', symbol)}: "
                         f"Long {d['long_pct']}% / Short {d['short_pct']}%")
        else:
            err = d.get("error", "取得不可") if isinstance(d, dict) else "取得不可"
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

    return "\n".join(lines)


def save_report(report: str, scraped_data: dict, prefix: str = "Daily_Bias_Report"):
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

    # Obsidian Vault に保存
    vault_path = OBSIDIAN_VAULT_PATH
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
        scraped_data = await collect_all_data()
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
    save_report(report, scraped_data, prefix=prefix)

    print(f"\n{'=' * 60}")
    print("完了!")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    asyncio.run(main())
