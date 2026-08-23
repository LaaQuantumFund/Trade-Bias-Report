"""Bias Report の human-first HTML を「画面で読む版」に変換する。

`scripts/human_report.build_html` は A4 印刷（Playwright page.pdf）を前提に
組まれているため、そのままブラウザ／スマホで開くと

  - `@page` / `page-break-*` が効かず紙面前提の余白だけが残る
  - 4 カラムの KPI グリッドや 90mm 固定のラダー列がスマホ幅で潰れる
  - 本文 9.5pt が小さく、表が画面外へはみ出す

という状態になる。ここでは **基準 CSS には手を入れず**、画面用の差分レイヤーを
後ろに足す形で上書きする（PDF 側の見た目は一切変えない）。

加えて、紙ではできない画面固有の導線を足す:
  - 節の索引をアンカーリンク化（ページ跨ぎのスクロール往復をなくす）
  - 表を横スクロールコンテナで包む（本文が横に流れないようにする）
  - 追従ナビ（ダッシュボード / 詳細 / 先頭）

出力は Artifact 用に `<!DOCTYPE>` / `<html>` / `<head>` / `<body>` を持たない
フラグメント（`build_fragment`）と、単体で開ける完全な HTML
（`build_page`）の 2 系統。

使い方:
    python scripts/screen_report.py <md_path> [-o out.html] [--fragment]
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPTS_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.human_report import build_html  # noqa: E402

SCREEN_CSS = """
/* ===== 画面表示レイヤー =====
 * A4 印刷基準の CSS に対する差分。screen でのみ効かせ、print には触らない。
 * 色は human-first-docs の検証済みパレット（白背景で validate 済み）をそのまま
 * 使うため、意図的に単一テーマ（ライト）で固定する。
 */
@media screen {
  html { -webkit-text-size-adjust: 100%; }

  html, body {
    background: #ffffff;
    color: #1c1c1e;
    font-size: 10.5pt;
    line-height: 1.75;
  }

  /* --- 追従ナビ（紙にはない導線） --- */
  .screen-nav {
    position: sticky;
    top: 0;
    z-index: 50;
    display: flex;
    align-items: center;
    gap: 16px;
    padding: 10px 20px;
    background: rgba(255, 255, 255, 0.94);
    backdrop-filter: saturate(1.4) blur(8px);
    border-bottom: 1px solid #e4e4e8;
  }

  .screen-nav-label {
    font-size: 8.5pt;
    font-weight: 700;
    color: #2547a8;
    letter-spacing: 0.4pt;
    margin-right: auto;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .screen-nav a {
    font-size: 8.5pt;
    color: #55555c;
    text-decoration: none;
    padding: 3px 10px;
    border: 1px solid #e4e4e8;
    border-radius: 999px;
    white-space: nowrap;
  }

  .screen-nav a:hover { color: #2547a8; border-color: #2547a8; }
  .screen-nav a:focus-visible { outline: 2px solid #2547a8; outline-offset: 2px; }

  /* --- 幅を流動にする --- */
  .dash-page, .dash-panels, .detail, .screen-foot {
    max-width: 1040px;
    margin-left: auto;
    margin-right: auto;
    padding-left: 20px;
    padding-right: 20px;
  }

  .dash-page { padding-top: 24px; }
  .detail { padding-top: 8px; }

  /* 紙の改ページ指定を無効化（画面は連続スクロール） */
  .detail { page-break-before: auto; }

  /* 和文の行長は 40 字前後を維持する（human-first-docs の数値既定） */
  .detail p, .detail ul, .detail ol { max-width: 42em; }
  .labeled { max-width: none; }

  html { scroll-behavior: smooth; }
  .doc-section { scroll-margin-top: 64px; }

  /* 右カラムが空のとき（ラダーのみの週）に余白だけが広がるのを防ぐ */
  .main-grid:has(> :last-child:empty) { grid-template-columns: minmax(0, 380px); }

  /* --- 節の索引をリンクとして機能させる --- */
  .sec-index a {
    color: #16213e;
    text-decoration: none;
    border-bottom: 1px dotted #b9bcc6;
  }

  .sec-index a:hover { color: #2547a8; border-bottom-color: #2547a8; }
  .sec-index a:focus-visible { outline: 2px solid #2547a8; outline-offset: 2px; }

  /* --- 表は本文を押し出さず、自分の中で横スクロールする --- */
  .table-scroll {
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
    margin-bottom: 3mm;
  }

  .screen-foot {
    padding-top: 24px;
    padding-bottom: 40px;
    font-size: 8pt;
    color: #8b8b92;
  }
}

/* ===== スマホ・タブレット縦 ===== */
@media screen and (max-width: 820px) {
  html, body { font-size: 11.5pt; }

  .dash-page, .dash-panels, .detail, .screen-foot {
    padding-left: 14px;
    padding-right: 14px;
  }

  .kpi-row { grid-template-columns: 1fr 1fr; }
  .main-grid { grid-template-columns: 1fr; }
  .plans-row { grid-template-columns: 1fr; }
  .dash-panels { grid-template-columns: 1fr; }
  .retail-grid { grid-template-columns: 1fr; }
  .corr-row { grid-template-columns: 1fr; }

  .dash-title { font-size: 15pt; }
  .detail-divider { flex-direction: column; gap: 2px; }

  /* 列が潰れて見出しが割れるより、横スクロールさせた方が読める */
  .std-table, .mini-table { min-width: 620px; font-size: 9pt; }

  .kpi-sub, .plan-val, .score-reason, .fund-driver, .mini-note, .retail-cell {
    font-size: 9.5pt;
  }

  .detail p, .detail ul, .detail ol { max-width: none; }
}

@media screen and (max-width: 520px) {
  .kpi-row { grid-template-columns: 1fr; }
  .screen-nav { gap: 8px; padding: 8px 14px; }
  .screen-nav-label { font-size: 8pt; }
}

@media (prefers-reduced-motion: reduce) {
  html { scroll-behavior: auto; }
}
"""

_SECTION_OPEN_RE = re.compile(r'<section class="doc-section">')
_TABLE_RE = re.compile(r"<table\b.*?</table>", re.S)
_INDEX_LI_RE = re.compile(r"<li>(.*?)</li>", re.S)
_STYLE_RE = re.compile(r"<style>(.*?)</style>", re.S)
_BODY_RE = re.compile(r"<body>(.*)</body>", re.S)
_TITLE_RE = re.compile(r"<title>(.*?)</title>", re.S)


def _anchor_sections(body: str) -> tuple[str, int]:
    """`.doc-section` に連番 id を振る。付けた個数を返す。"""
    counter = {"n": 0}

    def repl(_m: re.Match[str]) -> str:
        counter["n"] += 1
        return f'<section class="doc-section" id="sec-{counter["n"]}">'

    return _SECTION_OPEN_RE.sub(repl, body), counter["n"]


def _link_index(body: str, section_count: int) -> str:
    """節の索引 `<li>` をアンカーリンクにする。

    索引と節は同じイテレーションで作られるため件数は一致するはずだが、
    ずれた場合はリンク化を諦めて素の索引のまま残す（表示は壊さない）。
    """
    m = re.search(r'<nav class="sec-index">.*?</nav>', body, re.S)
    if not m:
        return body
    nav = m.group(0)
    items = _INDEX_LI_RE.findall(nav)
    if len(items) != section_count:
        return body

    counter = {"n": 0}

    def repl(li: re.Match[str]) -> str:
        counter["n"] += 1
        return f'<li><a href="#sec-{counter["n"]}">{li.group(1)}</a></li>'

    return body.replace(nav, _INDEX_LI_RE.sub(repl, nav))


def _wrap_tables(body: str) -> str:
    """表を横スクロールコンテナで包み、本文を横に流させない。"""
    return _TABLE_RE.sub(
        lambda m: f'<div class="table-scroll">{m.group(0)}</div>', body)


def _nav_html(doc_label: str) -> str:
    return (
        '<nav class="screen-nav" aria-label="レポート内ナビゲーション">'
        f'<span class="screen-nav-label">{doc_label}</span>'
        '<a href="#dash">ダッシュボード</a>'
        '<a href="#detail">詳細</a>'
        '</nav>'
    )


def build_fragment(md_text: str) -> tuple[str, str]:
    """`(title, fragment_html)` を返す。fragment は body の中身のみ。

    Artifact は `<!doctype html><head>...</head><body>` を公開時に被せるため、
    こちらは `<title>` + `<style>` + 本文だけを返す。
    """
    full = build_html(md_text)

    style_m = _STYLE_RE.search(full)
    body_m = _BODY_RE.search(full)
    title_m = _TITLE_RE.search(full)
    if not (style_m and body_m):
        raise ValueError("build_html の出力から style/body を取り出せなかった")

    title = title_m.group(1).strip() if title_m else "Bias Report"
    body = body_m.group(1)

    body, section_count = _anchor_sections(body)
    body = _link_index(body, section_count)
    body = _wrap_tables(body)
    body = body.replace('<div class="dash-page">',
                        '<div class="dash-page" id="dash">', 1)
    body = body.replace('<div class="detail">',
                        '<div class="detail" id="detail">', 1)

    style = style_m.group(1) + SCREEN_CSS
    fragment = (
        f"<title>{title}</title>\n"
        f"<style>{style}</style>\n"
        f"{_nav_html(title)}\n"
        f"{body}"
    )
    return title, fragment


def build_page(md_text: str) -> str:
    """単体でブラウザに開ける完全な HTML を返す。"""
    title, fragment = build_fragment(md_text)
    return (
        '<!DOCTYPE html>\n<html lang="ja">\n<head>\n'
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"{fragment.split('</style>')[0]}</style>\n</head>\n<body>\n"
        f"{fragment.split('</style>', 1)[1]}\n</body>\n</html>\n"
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Bias Report MD → 画面表示用 HTML")
    ap.add_argument("md_path", type=Path)
    ap.add_argument("-o", "--out", type=Path, default=None)
    ap.add_argument("--fragment", action="store_true",
                    help="Artifact 用に body 中身のみを出力する")
    args = ap.parse_args()

    md_text = args.md_path.read_text(encoding="utf-8")
    if args.fragment:
        _, out_html = build_fragment(md_text)
    else:
        out_html = build_page(md_text)

    out_path = args.out or args.md_path.with_name(
        args.md_path.stem + "_screen.html")
    out_path.write_text(out_html, encoding="utf-8")
    print(f"HTML: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
