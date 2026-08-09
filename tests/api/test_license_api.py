"""M26: ライセンスAPI(状態の取得と登録)"""

from datetime import date

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from backend.core import license as lic


@pytest.fixture
def issuer(monkeypatch, tmp_path):
    """テスト用の鍵ペアを埋め込み公開鍵と保存先に差し込む"""
    from backend.api import license_api

    private = Ed25519PrivateKey.generate()
    monkeypatch.setattr(license_api, "PUBLIC_KEY", lic.public_key_to_text(private.public_key()))
    monkeypatch.setattr(license_api, "key_path", lambda: tmp_path / "license.key")
    return private


def issue(private, **overrides) -> str:
    payload = {
        "p": lic.PRODUCT, "e": "pro", "i": "2026-01-01",
        "x": "2099-01-01", "l": "テスト社", "s": 1,
    }
    payload.update(overrides)
    return lic.sign_payload(payload, private)


def test_未登録なら未登録と返る(client, issuer):
    body = client.get("/api/license").json()
    assert body["status"] == "missing"
    assert body["is_usable"] is False
    assert body["licensee"] == ""


def test_登録すると状態が有効になる(client, issuer):
    key = issue(issuer)
    res = client.post("/api/license", json={"key": key})
    assert res.status_code == 200
    assert res.json()["status"] == "valid"
    assert res.json()["licensee"] == "テスト社"
    # 再取得しても保存されている
    assert client.get("/api/license").json()["status"] == "valid"


def test_不正なキーは登録できず既存の登録も壊さない(client, issuer):
    client.post("/api/license", json={"key": issue(issuer)})
    res = client.post("/api/license", json={"key": "KS1.こわれた.きー"})
    assert res.status_code == 400
    assert "ライセンス" in res.json()["detail"]
    # 直前の正規キーがそのまま残っている
    assert client.get("/api/license").json()["status"] == "valid"


def test_期限切れのキーは登録できない(client, issuer):
    expired = issue(issuer, x="2020-01-01")
    res = client.post("/api/license", json={"key": expired})
    assert res.status_code == 400


def test_猶予期間中のキーは登録できる(client, issuer):
    """更新の行き違いで作業中のユーザーを締め出さない"""
    from datetime import timedelta

    soon = (date.today() - timedelta(days=lic.GRACE_DAYS - 1)).isoformat()
    res = client.post("/api/license", json={"key": issue(issuer, x=soon)})
    assert res.status_code == 200
    assert res.json()["status"] == "grace"


def test_期限が近いと残り日数を返す(client, issuer):
    from datetime import timedelta

    soon = (date.today() + timedelta(days=5)).isoformat()
    client.post("/api/license", json={"key": issue(issuer, x=soon)})
    body = client.get("/api/license").json()
    assert body["days_left"] == 5
    assert body["expiring_soon"] is True


def test_キーそのものは返さない(client, issuer):
    """画面に出す必要が無いものを載せない"""
    client.post("/api/license", json={"key": issue(issuer)})
    assert "key" not in client.get("/api/license").json()
