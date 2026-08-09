"""M27: Claude(Anthropic API)クライアント。

実APIは呼ばない(CLAUDE.mdの規約)。SDKを差し替えて、
リクエストの組み立てと応答の解釈だけを確かめる。
"""

import pytest

from backend.engines.llm.base import LLMError
from backend.engines.llm.claude import (
    DEFAULT_MODEL,
    ClaudeClient,
    load_api_key,
    to_strict_schema,
)

SCHEMA = {
    "type": "object",
    "properties": {
        "edits": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"line": {"type": "integer"}, "text": {"type": "string"}},
                "required": ["line", "text"],
            },
        }
    },
    "required": ["edits"],
}


class FakeBlock:
    def __init__(self, text):
        self.type = "text"
        self.text = text


class FakeMessage:
    def __init__(self, text="{}", stop_reason="end_turn"):
        self.content = [FakeBlock(text)] if text is not None else []
        self.stop_reason = stop_reason
        self.stop_details = None


class FakeMessages:
    """SDKの messages.create を差し替える"""

    def __init__(self, results):
        self.results = list(results)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        out = self.results.pop(0) if self.results else FakeMessage()
        if isinstance(out, Exception):
            raise out
        return out


class FakeSDK:
    def __init__(self, *results):
        self.messages = FakeMessages(results)


def client_with(*results, **kwargs) -> tuple[ClaudeClient, FakeSDK]:
    sdk = FakeSDK(*results)
    return ClaudeClient(api_key="sk-test", sdk=sdk, retries=1, **kwargs), sdk


# ---- スキーマ変換 ----
def test_構造化出力のスキーマには全オブジェクトにadditionalPropertiesが要る():
    """これが無いとAPIがスキーマを受け付けない"""
    strict = to_strict_schema(SCHEMA)
    assert strict["additionalProperties"] is False
    assert strict["properties"]["edits"]["items"]["additionalProperties"] is False


def test_スキーマ変換は元のスキーマを壊さない():
    original = {"type": "object", "properties": {"a": {"type": "string"}}, "required": ["a"]}
    to_strict_schema(original)
    assert "additionalProperties" not in original


def test_スキーマ変換は中身を保つ():
    strict = to_strict_schema(SCHEMA)
    assert strict["required"] == ["edits"]
    assert strict["properties"]["edits"]["items"]["properties"]["line"]["type"] == "integer"


# ---- リクエストの組み立て ----
def test_構造化出力でJSONを要求する():
    client, sdk = client_with(FakeMessage('{"edits": []}'))
    client.complete_json("あなたは編集者です", "本文", SCHEMA)

    sent = sdk.messages.calls[0]
    assert sent["model"] == DEFAULT_MODEL
    assert sent["system"] == "あなたは編集者です"
    assert sent["messages"] == [{"role": "user", "content": "本文"}]
    fmt = sent["output_config"]["format"]
    assert fmt["type"] == "json_schema"
    assert fmt["schema"]["additionalProperties"] is False


def test_思考の分も含めて出力枠を確保する():
    """Claudeは既定で思考する。max_tokensは思考と本文の合計にかかるため余裕が要る"""
    client, sdk = client_with(FakeMessage('{"edits": []}'))
    client.complete_json("s", "u", SCHEMA)
    assert sdk.messages.calls[0]["max_tokens"] >= 16000


def test_モデルを指定できる():
    client, sdk = client_with(FakeMessage("{}"), model="claude-sonnet-5")
    client.complete_json("s", "u", SCHEMA)
    assert sdk.messages.calls[0]["model"] == "claude-sonnet-5"


# ---- 応答の解釈 ----
def test_JSONを取り出す():
    client, _ = client_with(FakeMessage('{"edits": [{"line": 1, "text": "あれ"}]}'))
    assert client.complete_json("s", "u", SCHEMA) == {"edits": [{"line": 1, "text": "あれ"}]}


def test_拒否されたら理由が分かるエラーにする():
    """安全機構による拒否は成功応答で返るので、本文を読む前に気付く必要がある"""
    client, _ = client_with(FakeMessage(None, stop_reason="refusal"))
    with pytest.raises(LLMError, match="拒否"):
        client.complete_json("s", "u", SCHEMA)


def test_出力が途中で切れたら分かるエラーにする():
    client, _ = client_with(FakeMessage('{"edits": [', stop_reason="max_tokens"))
    with pytest.raises(LLMError, match="長すぎ"):
        client.complete_json("s", "u", SCHEMA)


def test_壊れたJSONはエラーにする():
    client, _ = client_with(FakeMessage("これはJSONではない"))
    with pytest.raises(LLMError):
        client.complete_json("s", "u", SCHEMA)


def test_テキストが無い応答はエラーにする():
    client, _ = client_with(FakeMessage(None))
    with pytest.raises(LLMError):
        client.complete_json("s", "u", SCHEMA)


# ---- 再試行 ----
def test_一時的な失敗は再試行する(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda _: None)
    sdk = FakeSDK(RuntimeError("一時的な失敗"), FakeMessage('{"edits": []}'))
    client = ClaudeClient(api_key="sk-test", sdk=sdk, retries=3)
    assert client.complete_json("s", "u", SCHEMA) == {"edits": []}
    assert len(sdk.messages.calls) == 2


def test_再試行を使い切ったらLLMErrorにする(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda _: None)
    sdk = FakeSDK(RuntimeError("だめ"), RuntimeError("だめ"))
    client = ClaudeClient(api_key="sk-test", sdk=sdk, retries=2)
    with pytest.raises(LLMError, match="2回"):
        client.complete_json("s", "u", SCHEMA)


def test_拒否は再試行しない(monkeypatch):
    """同じ内容を投げ直しても結果は変わらないので、待つだけ無駄になる"""
    monkeypatch.setattr("time.sleep", lambda _: None)
    sdk = FakeSDK(FakeMessage(None, stop_reason="refusal"), FakeMessage('{"edits": []}'))
    client = ClaudeClient(api_key="sk-test", sdk=sdk, retries=3)
    with pytest.raises(LLMError, match="拒否"):
        client.complete_json("s", "u", SCHEMA)
    assert len(sdk.messages.calls) == 1


# ---- APIキー ----
def test_環境変数からキーを読む(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-xxx")
    assert load_api_key(None) == "sk-ant-xxx"


def test_ファイルからキーを読む(monkeypatch, tmp_path):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    path = tmp_path / "claude_api_key.txt"
    path.write_text("sk-ant-api03-file\n", encoding="utf-8")
    assert load_api_key(path) == "sk-ant-api03-file"


@pytest.mark.parametrize(
    "content",
    [
        "ここにAPIキーを書いてください",   # 雛形のまま
        "ANTHROPIC_API_KEY=sk-ant-xxx",  # .env形式で貼ってしまった
        "sk-ant-xxx\nsk-ant-yyy",        # 2つ書いてある
        "",
    ],
)
def test_キーの形をしていないファイルは使わない(monkeypatch, tmp_path, content):
    """雛形や書き間違いをそのままAPIに送らないため"""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    path = tmp_path / "claude_api_key.txt"
    path.write_text(content + "\n", encoding="utf-8")
    assert load_api_key(path) is None


def test_キーが無ければNone(monkeypatch, tmp_path):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert load_api_key(tmp_path / "none.txt") is None
