"""新しい版の確認(backend/core/update_check.py)。

issue #3 の報告者は v2.0.0 が出ていることに気付かず v1.0.1 を使っていた。
アプリに自動更新は無いので、起動時に最新の版を尋ねて画面で知らせる。
通信は差し替えて、判定だけを確かめる(テストから外部へは出ない)。
"""

import pytest
import requests

from backend.core import update_check as uc


@pytest.mark.parametrize(
    "text, expected",
    [
        ("v2.1.0", (2, 1, 0)),
        ("2.1.0", (2, 1, 0)),
        (" v10.0.12 ", (10, 0, 12)),
        ("v2.1.0-rc1", None),  # 試験版は正式版として扱わない
        ("v2.1", None),
        ("latest", None),
        ("", None),
    ],
)
def test_parse_version(text, expected):
    assert uc.parse_version(text) == expected


@pytest.mark.parametrize(
    "latest, current, expected",
    [
        ("v2.1.0", "2.0.0", True),
        ("v2.0.0", "2.0.0", False),
        ("v1.0.1", "2.0.0", False),      # 手元の方が新しい(開発中)
        ("v2.0.10", "2.0.9", True),      # 文字列比較だと逆になる
        ("v10.0.0", "9.9.9", True),
        ("v2.1.0-rc1", "2.0.0", False),  # 試験版は知らせない
        ("v2.1.0", "", False),           # 自分の版が分からなければ知らせない
    ],
)
def test_is_newer(latest, current, expected):
    assert uc.is_newer(latest, current) is expected


@pytest.mark.parametrize(
    "name, payload, has_update, latest",
    [
        ("新しい版がある", {"tag_name": "v2.1.0", "body": "## 直った不具合\n- A"}, True, "2.1.0"),
        ("同じ版", {"tag_name": "v2.0.0", "body": "x"}, False, "2.0.0"),
        ("下書きは知らせない", {"tag_name": "v2.1.0", "draft": True}, False, None),
        ("試験版は知らせない", {"tag_name": "v2.1.0", "prerelease": True}, False, None),
        ("タグが版の形でない", {"tag_name": "nightly"}, False, None),
        ("空の応答", {}, False, None),
    ],
)
def test_evaluate(name, payload, has_update, latest):
    info = uc.evaluate("2.0.0", payload)
    assert (info.has_update, info.latest, info.checked) == (has_update, latest, True), name


def test_変更点は新しい版があるときだけ載せる():
    assert uc.evaluate("2.0.0", {"tag_name": "v2.1.0", "body": "変更点"}).notes == "変更点"
    assert uc.evaluate("2.1.0", {"tag_name": "v2.1.0", "body": "変更点"}).notes == ""


def test_開かせるURLは応答から取らない():
    """外から来たURLをそのままブラウザに渡さない"""
    info = uc.evaluate("2.0.0", {"tag_name": "v2.1.0", "html_url": "https://evil.example/x"})
    assert info.url == uc.RELEASES_URL


def test_trim_notes_は行の途中で切らない():
    body = "\n".join(f"- 変更点その{i}" for i in range(100))
    got = uc.trim_notes(body, limit=50)
    assert got.endswith("\n…")
    assert all(line.startswith("- 変更点その") for line in got.splitlines()[:-1])
    assert len(got) <= 52
    assert uc.trim_notes("短い", limit=50) == "短い"


def test_配布版の版はシェルが教える():
    assert uc.current_version({"KS_APP_VERSION": "2.3.4"}) == "2.3.4"


def test_開発中の版はpyprojectから読む():
    assert uc.parse_version(uc.current_version({})) is not None


def test_確認を切っていれば通信しない():
    def fetch():
        raise AssertionError("通信した")

    info = uc.check(enabled=False, fetch=fetch, current="2.0.0")
    assert (info.checked, info.has_update, info.current) == (False, False, "2.0.0")


def test_今すぐ確認は切っていても通信する():
    info = uc.check(enabled=False, force=True, fetch=lambda: {"tag_name": "v2.1.0"}, current="2.0.0")
    assert info.has_update is True


def test_確認は1回だけで覚える():
    calls = []

    def fetch():
        calls.append(1)
        return {"tag_name": "v2.1.0"}

    uc.check(fetch=fetch, current="2.0.0")
    uc.check(fetch=fetch, current="2.0.0")
    assert len(calls) == 1
    uc.check(force=True, fetch=fetch, current="2.0.0")
    assert len(calls) == 2


def test_通信の失敗は理由を返すだけで例外にしない():
    def fetch():
        raise requests.ConnectionError("no route")

    info = uc.check(fetch=fetch, current="2.0.0")
    assert info.has_update is False
    assert "確認できませんでした" in info.error
    # 失敗は覚えない(次に開いたときもう一度試す)
    assert uc.check(fetch=lambda: {"tag_name": "v2.1.0"}, current="2.0.0").has_update is True


def test_壊れた応答でも落ちない():
    def fetch():
        raise ValueError("not json")

    assert uc.check(fetch=fetch, current="2.0.0").error


# ---- API ----

def test_api_新しい版を知らせる(client, monkeypatch):
    monkeypatch.setattr(uc, "fetch_latest", lambda: {"tag_name": "v99.0.0", "body": "- 新機能"})
    body = client.get("/api/update").json()
    assert body["has_update"] is True
    assert body["latest"] == "99.0.0"
    assert body["notes"] == "- 新機能"
    assert body["url"] == uc.RELEASES_URL


def test_api_設定で切ると通信しない(client):
    """conftest が fetch_latest を「呼んだら失敗」に差し替えている"""
    r = client.patch("/api/settings", json={"update_check_enabled": False})
    assert r.status_code == 200, r.text
    body = client.get("/api/update").json()
    assert body["checked"] is False and body["has_update"] is False
    assert uc.parse_version(body["current"]) is not None


def test_api_ダウンロードページは決まったURLだけを開く(client, monkeypatch):
    from backend.core import reveal

    opened = []
    monkeypatch.setattr(reveal, "open_url", lambda url, os_name=None: opened.append(url))
    r = client.post("/api/update/open")
    assert r.status_code == 200
    assert opened == [uc.RELEASES_URL]


def test_更新の確認はプロジェクトごとの設定にしない():
    from backend.core.project_settings import MUTABLE_FIELDS, PROJECT_OVERRIDABLE

    assert "update_check_enabled" in MUTABLE_FIELDS
    assert "update_check_enabled" not in PROJECT_OVERRIDABLE
