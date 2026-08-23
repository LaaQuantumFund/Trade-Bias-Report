"""Bias Report の HTML を Supabase Storage へ上げ、固定 URL を返す。

なぜ固定 URL か:
  Telegram に毎回違う URL が流れると過去号が散らかり、HP から「常に最新」を
  指す先も作れない。Daily / Weekly でそれぞれ 1 本の URL に上書きし続ける。
  過去号は Brain の MD が正本なので、必要になったら screen_report.py で
  その場で変換すればよく、URL を増やす必要がない。

URL の形:
  https://<project>.supabase.co/storage/v1/object/public/bias-reports/<prefix>/{daily|weekly}/latest.html

  バケットは公開だが `<prefix>` は推測困難な乱数（1Password 管理）なので、
  URL を知らない第三者は到達できない。将来 HP の「Daily Bias」コーナーから
  この URL にリンクを張れば、そのまま公開コーナーになる。

必要な環境変数（`.env.tpl` 経由で `op run` が注入する）:
  SUPABASE_URL                 プロジェクトの API URL
  SUPABASE_SERVICE_ROLE_KEY    アップロード用（RLS を迂回するため service_role）
  BIAS_REPORT_PATH_PREFIX      推測困難な固定パス断片

設計方針:
  publish_report.py と同じく、失敗してもレポート生成本体を止めない。
  上げられなければ WARN を出して None を返すだけ。

使い方:
    ./scripts/run-with-secrets.sh uv run python scripts/upload_report.py \\
        output/Weekly_Bias_Report_2026-08-22.html --mode weekly
"""

from __future__ import annotations

import argparse
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

BUCKET = "bias-reports"
UPLOAD_TIMEOUT = float(os.environ.get("UPLOAD_REPORT_TIMEOUT", "60"))


class MissingConfig(RuntimeError):
    """必要な環境変数が揃っていない。"""


def _env() -> tuple[str, str, str]:
    base = (os.environ.get("SUPABASE_URL") or "").rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or ""
    prefix = (os.environ.get("BIAS_REPORT_PATH_PREFIX") or "").strip("/")
    missing = [
        name for name, value in (
            ("SUPABASE_URL", base),
            ("SUPABASE_SERVICE_ROLE_KEY", key),
            ("BIAS_REPORT_PATH_PREFIX", prefix),
        ) if not value
    ]
    if missing:
        raise MissingConfig("未設定の環境変数: " + ", ".join(missing))
    return base, key, prefix


def object_path(prefix: str, mode: str) -> str:
    """`<prefix>/{mode}/latest.html`。mode は daily / weekly。"""
    return f"{prefix}/{mode}/latest.html"


def public_url(base: str, path: str) -> str:
    return f"{base}/storage/v1/object/public/{BUCKET}/{path}"


def upload(html_path: Path, mode: str) -> Optional[str]:
    """HTML を上げて公開 URL を返す。失敗時は WARN を出して None。"""
    if not html_path.exists():
        print(f"[upload] WARN: HTML が無いためスキップ: {html_path}")
        return None

    try:
        base, key, prefix = _env()
    except MissingConfig as exc:
        print(f"[upload] WARN: {exc}（アップロードをスキップ）")
        return None

    path = object_path(prefix, mode)
    body = html_path.read_bytes()
    req = urllib.request.Request(
        f"{base}/storage/v1/object/{BUCKET}/{path}",
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {key}",
            "apikey": key,
            "Content-Type": "text/html",
            # 同じパスへ上書きし続けるための必須ヘッダ。
            "x-upsert": "true",
            # 常に最新を出す。CDN に古い版が居座ると固定 URL の意味が消える。
            "Cache-Control": "no-cache, max-age=0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=UPLOAD_TIMEOUT) as res:
            if res.status not in (200, 201):
                print(f"[upload] WARN: 予期しないステータス {res.status}")
                return None
    except urllib.error.HTTPError as exc:
        # 本文にキーは含まれないが、念のため先頭 200 字だけに切る
        detail = exc.read()[:200].decode("utf-8", "replace")
        print(f"[upload] WARN: アップロード失敗 HTTP {exc.code}: {detail}")
        return None
    except Exception as exc:  # noqa: BLE001 — ソフト障害
        print(f"[upload] WARN: アップロード失敗: {type(exc).__name__}: {exc}")
        return None

    url = public_url(base, path)
    print(f"URL: {url}")
    return url


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Bias Report HTML を Supabase Storage の固定 URL へ発行する")
    ap.add_argument("html_path", type=Path)
    ap.add_argument("--mode", choices=["daily", "weekly"], required=True)
    args = ap.parse_args(argv)
    upload(args.html_path.expanduser(), args.mode)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
