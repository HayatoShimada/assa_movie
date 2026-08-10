"""M27: APIキーの登録(設定画面から入れられるようにする)"""

import pytest
import requests

from backend.api import keys_api


@pytest.fixture(autouse=True)
def key_dir(monkeypatch, tmp_path):
    """キーの保存先を一時ディレクトリに逃がす"""
    monkeypatch.setattr(keys_api, "key_path", lambda provider: tmp_path / f"{provider}.txt")
    for var in ("ANTHROPIC_API_KEY", "GEMINI_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    return tmp_path


@pytest.fixture(autouse=True)
def verify_ok(monkeypatch):
    """疎通確認は既定で成功させる(テストから実ネットワークに出ない)"""
    calls = []

    def _record(provider):
        def _verify(key):
            calls.append((provider, key))
            return None

        return _verify

    for provider in keys_api.PROVIDERS:
        monkeypatch.setitem(keys_api.VERIFIERS, provider, _record(provider))
    return calls


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


def test_Geminiの新形式キーも登録できる(client):
    """キーの形式は仕様変更で変わる(AIza〜 → AQ.〜)。接頭辞では判定しない"""
    res = client.put("/api/keys/gemini", json={"key": "AQ.Ab8RN6JXXXXXXXXXXXX"})
    assert res.status_code == 200
    assert res.json()["gemini"]["configured"] is True


def test_登録時に疎通確認が走る(client, verify_ok):
    """形式の目視チェックではなく、実際にAPIへ接続して確かめる"""
    client.put("/api/keys/gemini", json={"key": "AQ.Ab8RN6Jxxxx"})
    assert verify_ok == [("gemini", "AQ.Ab8RN6Jxxxx")]


def test_疎通確認に失敗したキーは保存しない(client, monkeypatch):
    monkeypatch.setitem(
        keys_api.VERIFIERS, "gemini", lambda key: "Gemini APIがこのキーを受け付けませんでした。"
    )
    res = client.put("/api/keys/gemini", json={"key": "AQ.Ab8RN6Jxxxx"})
    assert res.status_code == 400
    assert "受け付けません" in res.json()["detail"]
    assert client.get("/api/keys").json()["gemini"]["configured"] is False


def test_通信できないときは保存せず既存キーも壊さない(client, monkeypatch):
    """ネットワーク断でキーの良し悪しは判定できない。既存の登録は守る"""
    client.put("/api/keys/gemini", json={"key": "AQ.Ab8RN6Jold"})

    def _unreachable(key):
        raise requests.ConnectionError("network down")

    monkeypatch.setitem(keys_api.VERIFIERS, "gemini", _unreachable)
    res = client.put("/api/keys/gemini", json={"key": "AQ.Ab8RN6Jnew"})
    assert res.status_code == 502
    assert "接続できません" in res.json()["detail"]
    assert client.get("/api/keys").json()["gemini"]["hint"] == "…Jold"


def test_空白や改行を含むキーは疎通確認より前に弾く(client, verify_ok):
    """説明文ごと貼り付けたケース。読み込み側が単一行しか受けないので保存もしない"""
    res = client.put("/api/keys/gemini", json={"key": "ここに貼る AQ.Ab8RN6Jxxxx"})
    assert res.status_code == 400
    assert verify_ok == []  # 無駄な通信をしない
