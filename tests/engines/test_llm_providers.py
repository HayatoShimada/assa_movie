"""LLMプロバイダ切替(Ollama / Gemini)のテスト"""

import json

import pytest
import requests
from fastapi.testclient import TestClient

from backend.core.config import Settings
from backend.engines.llm.base import LLMError
from backend.engines.llm.claude import verify_api_key as claude_verify_api_key
from backend.engines.llm.gemini import GeminiClient, load_api_key, to_gemini_schema, verify_api_key
from backend.engines.llm.ollama import OllamaClient
from backend.engines.llm.registry import PROVIDERS, build_client
from backend.pipeline.pronoun import EDITS_SCHEMA


# ---- プロバイダ選択 ----
def test_build_client_ollama_by_default():
    c = build_client(Settings(_env_file=None))
    assert isinstance(c, OllamaClient)
    assert c.name == "ollama"


def test_build_client_gemini_with_key(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    s = Settings(_env_file=None)
    s.llm_provider = "gemini"
    c = build_client(s)
    assert isinstance(c, GeminiClient)
    assert c.api_key == "test-key"
    assert c.model == "gemini-3.5-flash"


def test_build_client_gemini_without_key_raises(monkeypatch, tmp_path):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    s = Settings(_env_file=None)
    s.llm_provider = "gemini"
    s.gemini_key_file = tmp_path / "none.txt"
    with pytest.raises(ValueError, match="APIキーが登録されていません"):
        build_client(s)


def test_build_client_unknown_provider_raises():
    s = Settings(_env_file=None)
    s.llm_provider = "openai"
    with pytest.raises(ValueError, match="未対応のLLMプロバイダ"):
        build_client(s)


# ---- APIキーの読み込み ----
def test_load_api_key_from_env(monkeypatch, tmp_path):
    monkeypatch.setenv("GEMINI_API_KEY", "from-env")
    assert load_api_key(tmp_path / "x.txt") == "from-env"


def test_load_api_key_from_file(monkeypatch, tmp_path):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    f = tmp_path / "k.txt"
    f.write_text("AIzaSyFake\n", encoding="utf-8")
    assert load_api_key(f) == "AIzaSyFake"


def test_load_api_key_rejects_placeholder_text(monkeypatch, tmp_path):
    """説明文が残ったままのファイルを鍵として使わない"""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    f = tmp_path / "k.txt"
    f.write_text(
        "ここにAPIキーを貼り付けてください\n取得: https://aistudio.google.com\n",
        encoding="utf-8",
    )
    assert load_api_key(f) is None


# ---- スキーマ変換 ----
def test_to_gemini_schema_strips_unsupported_keys():
    schema = {
        "type": "object",
        "additionalProperties": False,   # Geminiは受け付けない
        "$schema": "http://json-schema.org/draft-07/schema#",
        "properties": {"a": {"type": "string", "additionalProperties": False}},
        "required": ["a"],
    }
    out = to_gemini_schema(schema)
    assert "additionalProperties" not in out
    assert "$schema" not in out
    assert "additionalProperties" not in out["properties"]["a"]
    assert out["required"] == ["a"]


def test_to_gemini_schema_handles_edits_schema():
    out = to_gemini_schema(EDITS_SCHEMA)
    items = out["properties"]["edits"]["items"]
    assert set(items["required"]) >= {"line", "original", "replacement"}
    assert items["properties"]["confidence"]["enum"] == ["auto", "review"]


# ---- Geminiクライアントの通信(requestsをモック) ----
class _FakeResponse:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status
        self.text = json.dumps(payload)

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def test_gemini_complete_json_parses_response(monkeypatch):
    captured = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        captured["url"] = url
        captured["body"] = json
        captured["headers"] = headers
        return _FakeResponse({
            "candidates": [{"content": {"parts": [{"text": '{"edits": [{"line": 1}]}'}]}}]
        })

    c = GeminiClient(api_key="k", model="gemini-3.5-flash")
    monkeypatch.setattr(c._session, "post", fake_post)

    out = c.complete_json("system文", "user文", EDITS_SCHEMA)
    assert out == {"edits": [{"line": 1}]}
    assert "gemini-3.5-flash:generateContent" in captured["url"]
    assert captured["headers"]["x-goog-api-key"] == "k"
    assert captured["body"]["systemInstruction"]["parts"][0]["text"] == "system文"
    assert captured["body"]["generationConfig"]["responseMimeType"] == "application/json"
    assert captured["body"]["generationConfig"]["temperature"] == 0


def test_gemini_retries_then_raises(monkeypatch):
    calls = []

    def fake_post(url, json=None, headers=None, timeout=None):
        calls.append(1)
        return _FakeResponse({"error": "rate limited"}, status=429)

    c = GeminiClient(api_key="k", retries=2)
    monkeypatch.setattr(c._session, "post", fake_post)
    monkeypatch.setattr("time.sleep", lambda _: None)

    with pytest.raises(LLMError, match="利用上限"):
        c.complete_json("s", "u", EDITS_SCHEMA)
    assert len(calls) == 2


# ---- 失敗の伝え方(利用者向けの文言。判定表は test_llm_errors.py) ----
def test_Ollamaのモデル未インストールは直し方付きのエラーにする(monkeypatch):
    calls = []

    def fake_post(url, json=None, timeout=None):
        calls.append(1)
        return _FakeResponse(
            {"error": 'model "qwen3:32b" not found, try pulling it first'}, status=404
        )

    monkeypatch.setattr("backend.engines.llm.ollama.requests.post", fake_post)
    monkeypatch.setattr("time.sleep", lambda _: None)
    with pytest.raises(LLMError) as exc:
        OllamaClient(model="qwen3:32b", retries=3).complete_json("s", "u", EDITS_SCHEMA)
    assert exc.value.code == "model_not_installed"
    assert "ollama pull qwen3:32b" in str(exc.value)
    assert "回失敗" not in str(exc.value)
    assert len(calls) == 1, "入っていないモデルは何度呼んでも同じなので再試行しない"
    assert "404" in exc.value.detail, "原因の調査用に生の応答は残す"


def test_Ollama未起動は起動を促すエラーにする(monkeypatch):
    def fake_post(url, json=None, timeout=None):
        raise requests.ConnectionError("Connection refused")

    monkeypatch.setattr("backend.engines.llm.ollama.requests.post", fake_post)
    monkeypatch.setattr("time.sleep", lambda _: None)
    with pytest.raises(LLMError) as exc:
        OllamaClient(retries=2).complete_json("s", "u", EDITS_SCHEMA)
    assert exc.value.code == "ollama_unreachable"
    assert "Ollama が起動していません" in str(exc.value)


def test_Ollamaの壊れたJSONは再試行して直れば成功する(monkeypatch):
    replies = [
        _FakeResponse({"message": {"content": "これはJSONではない"}}),
        _FakeResponse({"message": {"content": '{"edits": []}'}}),
    ]
    monkeypatch.setattr(
        "backend.engines.llm.ollama.requests.post",
        lambda url, json=None, timeout=None: replies.pop(0),
    )
    monkeypatch.setattr("time.sleep", lambda _: None)
    assert OllamaClient(retries=3).complete_json("s", "u", EDITS_SCHEMA) == {"edits": []}


def test_GeminiのAPIキー不正は登録し直しを促す(monkeypatch):
    calls = []

    def fake_post(url, json=None, headers=None, timeout=None):
        calls.append(1)
        return _FakeResponse({"error": {"message": "API key not valid"}}, status=400)

    c = GeminiClient(api_key="bad", retries=3)
    monkeypatch.setattr(c._session, "post", fake_post)
    monkeypatch.setattr("time.sleep", lambda _: None)
    with pytest.raises(LLMError) as exc:
        c.complete_json("s", "u", EDITS_SCHEMA)
    assert exc.value.code == "invalid_key"
    assert "APIキーが正しくありません" in str(exc.value)
    assert len(calls) == 1


def test_キー未登録は利用者向けのエラーにする(monkeypatch, tmp_path):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    s = Settings(_env_file=None)
    s.llm_provider = "gemini"
    s.gemini_key_file = tmp_path / "none.txt"
    with pytest.raises(LLMError) as exc:
        build_client(s)
    assert exc.value.code == "no_key"
    assert "設定タブ" in str(exc.value)


# ---- APIキーの疎通確認(登録時に1回だけ呼ぶ) ----
def _fake_get(captured, status=200):
    def fake_get(url, headers=None, params=None, timeout=None):
        captured.update(url=url, headers=headers)
        return _FakeResponse({}, status=status)

    return fake_get


def test_gemini_verify_api_key_通れば何も返さない(monkeypatch):
    captured = {}
    monkeypatch.setattr("backend.engines.llm.gemini.requests.get", _fake_get(captured))
    assert verify_api_key("AQ.Ab8RN6Jxxxx") is None
    assert captured["headers"]["x-goog-api-key"] == "AQ.Ab8RN6Jxxxx"


def test_gemini_verify_api_key_認証エラーなら理由を返す(monkeypatch):
    for status in (400, 401, 403):
        monkeypatch.setattr("backend.engines.llm.gemini.requests.get", _fake_get({}, status))
        assert "受け付けません" in verify_api_key("bad-key")


def test_gemini_verify_api_key_レート制限はキー有効とみなす(monkeypatch):
    """429はクォータの問題で、キーそのものは正しい"""
    monkeypatch.setattr("backend.engines.llm.gemini.requests.get", _fake_get({}, 429))
    assert verify_api_key("AQ.Ab8RN6Jxxxx") is None


def test_gemini_verify_api_key_通信エラーは例外のまま上げる(monkeypatch):
    def boom(url, headers=None, params=None, timeout=None):
        raise requests.ConnectionError("down")

    monkeypatch.setattr("backend.engines.llm.gemini.requests.get", boom)
    with pytest.raises(requests.ConnectionError):
        verify_api_key("AQ.Ab8RN6Jxxxx")


def test_claude_verify_api_key_通れば何も返さない(monkeypatch):
    captured = {}
    monkeypatch.setattr("backend.engines.llm.claude.requests.get", _fake_get(captured))
    assert claude_verify_api_key("sk-ant-api03-xxxx") is None
    assert captured["headers"]["x-api-key"] == "sk-ant-api03-xxxx"
    assert "anthropic-version" in captured["headers"]


def test_claude_verify_api_key_認証エラーなら理由を返す(monkeypatch):
    monkeypatch.setattr("backend.engines.llm.claude.requests.get", _fake_get({}, 401))
    assert "受け付けません" in claude_verify_api_key("sk-ant-bad")


# ---- 設定API ----
def test_settings_api_lists_providers(client):
    body = client.get("/api/settings").json()
    ids = {p["id"] for p in body["llm_providers"]}
    assert ids == set(PROVIDERS)

    ollama = next(p for p in body["llm_providers"] if p["id"] == "ollama")
    assert ollama["local"] is True and ollama["ready"] is True

    gemini = next(p for p in body["llm_providers"] if p["id"] == "gemini")
    assert gemini["local"] is False
    assert "Google" in gemini["note"]  # 送信先をUIで明示できる


def test_settings_api_switches_provider(client):
    r = client.patch("/api/settings", json={"llm_provider": "gemini"})
    assert r.status_code == 200
    assert r.json()["values"]["llm_provider"] == "gemini"
    client.patch("/api/settings", json={"llm_provider": "ollama"})


def test_settings_api_rejects_unknown_provider(client):
    assert client.patch("/api/settings", json={"llm_provider": "openai"}).status_code == 400
