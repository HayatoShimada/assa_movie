"""Claude(Anthropic API)クライアント。

APIキーは環境変数 ANTHROPIC_API_KEY、または設定ディレクトリの claude_api_key.txt から読む。

構造化出力(output_config.format)でJSON Schemaを直接渡せるので、
Ollama・Geminiと同じ `complete_json` の形に収まる。
"""

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

from backend.engines.llm.base import LLMError

DEFAULT_MODEL = "claude-opus-5"
# Claudeは既定で思考する。max_tokensは「思考+本文」の合計にかかるので、
# 本文だけを見て詰めると途中で切れる
MAX_TOKENS = 16000
# 指示語や相槌の判定は文脈依存の判断なので、極端に浅くしない。
# 逆に文字起こしのチャンクごとに何十回も呼ぶため、既定はhighではなくmediumにする
EFFORT = "medium"


# AnthropicのAPIキーの接頭辞。説明文が残った雛形ファイルを誤って送らないための目印
KEY_PREFIX = "sk-ant-"


def load_api_key(key_file: Path | None = None) -> str | None:
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if key:
        return key
    if key_file and key_file.exists():
        text = key_file.read_text(encoding="utf-8").strip()
        if text.startswith(KEY_PREFIX) and "\n" not in text:
            return text
    return None


def to_strict_schema(schema: dict) -> dict:
    """構造化出力が受け付ける形にする(純関数)。

    すべてのobjectに `additionalProperties: false` が必要で、
    無いとAPIがスキーマを拒否する。元のスキーマは書き換えない。
    """
    if not isinstance(schema, dict):
        return schema
    out = dict(schema)
    if out.get("type") == "object":
        out["additionalProperties"] = False
        if "properties" in out:
            out["properties"] = {k: to_strict_schema(v) for k, v in out["properties"].items()}
    if "items" in out:
        out["items"] = to_strict_schema(out["items"])
    return out


def _build_sdk(api_key: str):
    import anthropic

    return anthropic.Anthropic(api_key=api_key)


@dataclass
class ClaudeClient:
    api_key: str
    model: str = DEFAULT_MODEL
    retries: int = 3
    name: str = "claude"
    # テストでSDKを差し替えるための注入口(実APIを呼ぶテストは書かない)
    sdk: object | None = field(default=None, repr=False)

    def __post_init__(self):
        if self.sdk is None:
            self.sdk = _build_sdk(self.api_key)

    def complete_json(self, system: str, user: str, schema: dict) -> dict:
        request = {
            "model": self.model,
            "max_tokens": MAX_TOKENS,
            "system": system,
            "messages": [{"role": "user", "content": user}],
            "output_config": {
                "effort": EFFORT,
                "format": {"type": "json_schema", "schema": to_strict_schema(schema)},
            },
        }

        last_error = None
        for attempt in range(self.retries):
            try:
                return self._parse(self.sdk.messages.create(**request))
            except _Refused:
                raise  # 同じ内容を投げ直しても結果は変わらない
            except Exception as e:
                last_error = e
                time.sleep(2 * (attempt + 1))
        raise LLMError(f"Claude呼び出しに{self.retries}回失敗: {last_error}")

    def _parse(self, message) -> dict:
        # 安全機構による拒否は「成功応答」で返るため、本文を読む前に確認する
        stop = getattr(message, "stop_reason", None)
        if stop == "refusal":
            detail = getattr(getattr(message, "stop_details", None), "category", "")
            raise _Refused(f"Claudeがこの内容の処理を拒否しました{f'({detail})' if detail else ''}。")
        if stop == "max_tokens":
            raise LLMError(
                "Claudeの応答が長すぎて途中で切れました。"
                "チャンクサイズ(llm_chunk_size)を小さくしてください。"
            )

        text = next(
            (b.text for b in getattr(message, "content", []) if getattr(b, "type", "") == "text"),
            None,
        )
        if not text:
            raise LLMError("Claudeの応答にテキストが含まれていません。")
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            raise LLMError(f"ClaudeのJSONを解釈できません: {e}") from e


class _Refused(LLMError):
    """安全機構による拒否。再試行しても同じなので、その場で伝える"""
