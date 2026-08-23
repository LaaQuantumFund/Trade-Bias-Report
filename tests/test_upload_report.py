"""upload_report.py の契約テスト。

守りたいのは 2 点:
  1. 固定 URL であること（daily / weekly でそれぞれ 1 本、日付を含まない）
  2. 設定欠落・通信失敗でレポート生成本体を止めないこと（WARN + None）
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts import upload_report  # noqa: E402


ENV_KEYS = ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY")


@pytest.fixture
def html(tmp_path: Path) -> Path:
    p = tmp_path / "Weekly_Bias_Report_2026-08-22.html"
    p.write_text("<html>report</html>", encoding="utf-8")
    return p


def _set_env(monkeypatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://proj.supabase.co/")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-key")


def test_object_path_has_no_date(html):
    """日付が入ると URL が毎回変わってしまう。latest 固定であることを保つ。"""
    path = upload_report.object_path("weekly")
    assert path == "weekly/latest.html"
    assert "2026" not in path


def test_storage_url_shape():
    url = upload_report.storage_url("https://proj.supabase.co", "daily/latest.html")
    assert url == (
        "https://proj.supabase.co/storage/v1/object/public/"
        "bias-reports/daily/latest.html"
    )


def test_reader_url_points_at_the_site_not_supabase():
    """Supabase の直リンクは text/plain でソース表示になるため外に出さない。"""
    url = upload_report.reader_url("weekly")
    assert url == "https://www.laa-inc.com/reports/weekly"
    assert "supabase" not in url


def test_missing_env_is_soft(html, monkeypatch, capsys):
    for key in ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    assert upload_report.upload(html, "weekly") is None
    out = capsys.readouterr().out
    assert "WARN" in out
    for key in ENV_KEYS:
        assert key in out, "どの環境変数が足りないかを名指しする"


def test_missing_html_is_soft(tmp_path, monkeypatch, capsys):
    _set_env(monkeypatch)
    assert upload_report.upload(tmp_path / "nope.html", "daily") is None
    assert "WARN" in capsys.readouterr().out


def test_upload_uses_upsert_and_returns_fixed_url(html, monkeypatch, capsys):
    _set_env(monkeypatch)
    captured = {}

    class _Res:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["method"] = req.get_method()
        captured["headers"] = {k.lower(): v for k, v in req.header_items()}
        captured["body"] = req.data
        return _Res()

    monkeypatch.setattr(upload_report.urllib.request, "urlopen", fake_urlopen)

    url = upload_report.upload(html, "weekly")
    # アップロード先は Supabase だが、返す URL は読者向けの HP 側
    assert url == "https://www.laa-inc.com/reports/weekly"
    assert captured["method"] == "POST"
    assert captured["url"].endswith("/storage/v1/object/bias-reports/weekly/latest.html")
    # 上書き前提の運用なので x-upsert が無いと 2 回目以降が 409 で落ちる
    assert captured["headers"].get("X-upsert".lower()) == "true"
    assert "no-cache" in captured["headers"].get("Cache-control".lower(), "")
    assert captured["body"] == b"<html>report</html>"


def test_http_error_is_soft(html, monkeypatch, capsys):
    import urllib.error

    _set_env(monkeypatch)

    def boom(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 403, "Forbidden", {},
                                     __import__("io").BytesIO(b"denied"))

    monkeypatch.setattr(upload_report.urllib.request, "urlopen", boom)
    assert upload_report.upload(html, "daily") is None
    assert "HTTP 403" in capsys.readouterr().out


def test_service_role_key_is_not_printed(html, monkeypatch, capsys):
    """WARN 本文にキーが混ざらないこと（ログ・Telegram に流れるため）。"""
    import urllib.error

    _set_env(monkeypatch)
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "super-secret-value")

    def boom(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 500, "err", {},
                                     __import__("io").BytesIO(b"boom"))

    monkeypatch.setattr(upload_report.urllib.request, "urlopen", boom)
    upload_report.upload(html, "daily")
    assert "super-secret-value" not in capsys.readouterr().out
