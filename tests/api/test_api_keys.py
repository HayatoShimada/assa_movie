"""M27: APIキーの登録(設定画面から入れられるようにする)"""

import pytest

from backend.api import keys_api


@pytest.fixture(autouse=True)
def key_dir(monkeypatch, tmp_path):
    """キーの保存先を一時ディレクトリに逃がす"""
    monkeypatch.setattr(keys_api, "key_path", lambda provider: tmp_path / f"{provider}.txt")
    for var in ("ANTHROPIC_API_KEY", "GEMINI_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    return tmp_path


def test_未登録なら未登録と返る(client):
    body = client.get("/api/keys").json()
    assert body["claude"]["configured"] is False
    assert body["gemini"]["configured"] is False


def test_登録すると設定済みになる(client):
    res = client.put("/api/keys/claude", json={"key": "sk-ant-api03-xxxxx"})
    assert res.status_code == 200
    assert res.json()["claude"]["configured"] is True
    assert client.get("/api/keys").json()["claude"]["configured"] is True


def test_キー本体は返さない(client):
    """画面に出す必要が無いものを載せない"""
    client.put("/api/keys/claude", json={"key": "sk-ant-api03-secret"})
    body = client.get("/api/keys").json()
    assert "secret" not in str(body)
    assert "key" not in body["claude"]


def test_末尾だけ見せる(client):
    """どのキーを登録したか分かるように、末尾4文字だけ出す"""
    client.put("/api/keys/claude", json={"key": "sk-ant-api03-abcdefgh"})
    assert client.get("/api/keys").json()["claude"]["hint"] == "…efgh"


def test_形式が違うキーは弾く(client):
    res = client.put("/api/keys/claude", json={"key": "これはキーではない"})
    assert res.status_code == 400
    assert "sk-ant-" in res.json()["detail"]
    assert client.get("/api/keys").json()["claude"]["configured"] is False


def test_空のキーは弾く(client):
    assert client.put("/api/keys/claude", json={"key": "   "}).status_code == 400


def test_前後の空白は落として保存する(client, key_dir):
    """コピペで空白や改行が混ざることを想定する"""
    client.put("/api/keys/claude", json={"key": "  sk-ant-api03-xxxxx \n"})
    assert (key_dir / "claude.txt").read_text(encoding="utf-8").strip() == "sk-ant-api03-xxxxx"


def test_削除できる(client):
    client.put("/api/keys/claude", json={"key": "sk-ant-api03-xxxxx"})
    assert client.delete("/api/keys/claude").status_code == 200
    assert client.get("/api/keys").json()["claude"]["configured"] is False


def test_未登録のキーを消してもエラーにしない(client):
    assert client.delete("/api/keys/gemini").status_code == 200


def test_知らないプロバイダは弾く(client):
    assert client.put("/api/keys/openai", json={"key": "sk-x"}).status_code == 404
    assert client.delete("/api/keys/openai").status_code == 404


def test_環境変数で入っている場合も設定済みとして扱う(client, monkeypatch):
    """キーの出所が違っても、ユーザーに見えるのは「使えるかどうか」だけ"""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-api03-env")
    body = client.get("/api/keys").json()
    assert body["claude"]["configured"] is True
    assert body["claude"]["source"] == "環境変数"


def test_ファイル保存なら出所がファイルになる(client):
    client.put("/api/keys/claude", json={"key": "sk-ant-api03-xxxxx"})
    assert client.get("/api/keys").json()["claude"]["source"] == "この端末に保存"


def test_Geminiのキーも同じ形で扱える(client):
    res = client.put("/api/keys/gemini", json={"key": "AIzaSyXXXXXXXXXXXX"})
    assert res.status_code == 200
    assert res.json()["gemini"]["configured"] is True
