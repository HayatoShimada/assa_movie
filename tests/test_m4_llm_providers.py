"""LLMプロバイダ切替(Ollama / Gemini)のテスト"""

import json

import pytest
from fastapi.testclient import TestClient

from backend.core.config import Settings
from backend.engines.llm.base import LLMError
from backend.engines.llm.gemini import GeminiClient, load_api_key, to_gemini_schema
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
    with pytest.raises(ValueError, match="APIキーが設定されていません"):
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
    f.write_text("AIzaSyFake\n")
    assert load_api_key(f) == "AIzaSyFake"


def test_load_api_key_rejects_placeholder_text(monkeypatch, tmp_path):
    """説明文が残ったままのファイルを鍵として使わない"""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    f = tmp_path / "k.txt"
    f.write_text("ここにAPIキーを貼り付けてください\n取得: https://aistudio.google.com\n")
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

    with pytest.raises(LLMError, match="2回失敗"):
        c.complete_json("s", "u", EDITS_SCHEMA)
    assert len(calls) == 2


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
