"""Gemini APIクライアント(クラウドLLM)。

APIキーは環境変数 GEMINI_API_KEY、または gemini_api_key.txt から読む。
JSON Schemaによる構造化出力に対応しているため、Ollamaと同じ扱いにできる。
"""

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

import requests

from backend.engines.llm.base import LLMError

API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
DEFAULT_MODEL = "gemini-3.5-flash"


def load_api_key(key_file: Path | None = None) -> str | None:
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if key:
        return key
    if key_file and key_file.exists():
        text = key_file.read_text(encoding="utf-8").strip()
        # 説明文が残っているファイルを誤って使わないよう単一行のみ受け付ける
        if text and "\n" not in text and " " not in text:
            return text
    return None


def to_gemini_schema(schema: dict) -> dict:
    """JSON SchemaをGeminiのresponseSchemaに変換する。

    Geminiは additionalProperties や $schema などを受け付けないため、
    サポートされるキーワードだけを残す。
    """
    allowed = {
        "type", "format", "description", "nullable", "enum",
        "properties", "required", "items", "propertyOrdering",
    }
    if not isinstance(schema, dict):
        return schema
    out = {k: v for k, v in schema.items() if k in allowed}
    if "properties" in out:
        out["properties"] = {k: to_gemini_schema(v) for k, v in out["properties"].items()}
    if "items" in out:
        out["items"] = to_gemini_schema(out["items"])
    return out


@dataclass
class GeminiClient:
    api_key: str
    model: str = DEFAULT_MODEL
    retries: int = 3
    timeout: int = 300
    name: str = "gemini"
    _session: requests.Session = field(default_factory=requests.Session, repr=False)

    def complete_json(self, system: str, user: str, schema: dict) -> dict:
        url = f"{API_BASE}/{self.model}:generateContent"
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {
                "temperature": 0,
                "responseMimeType": "application/json",
                "responseSchema": to_gemini_schema(schema),
            },
        }

        last_error = None
        for attempt in range(self.retries):
            try:
                resp = self._session.post(
                    url, json=body,
                    headers={"x-goog-api-key": self.api_key},
                    timeout=self.timeout,
                )
                if resp.status_code in (429, 500, 502, 503):
                    raise LLMError(f"一時的なエラー {resp.status_code}: {resp.text[:200]}")
                resp.raise_for_status()
                data = resp.json()
                text = data["candidates"][0]["content"]["parts"][0]["text"]
                return json.loads(text)
            except Exception as e:
                last_error = e
                time.sleep(2 * (attempt + 1))  # レート制限に配慮して待ち時間を伸ばす
        raise LLMError(f"Gemini呼び出しに{self.retries}回失敗: {last_error}")
