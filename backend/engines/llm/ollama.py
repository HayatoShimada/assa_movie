"""Ollamaクライアント(ローカルLLM)。"""

import json
import time
from dataclasses import dataclass

import requests

from backend.engines.llm.base import LLMError
from backend.engines.llm.errors import FailureInfo, is_retryable


@dataclass
class OllamaClient:
    url: str = "http://localhost:11434/api/chat"
    model: str = "qwen3:32b"
    retries: int = 3
    timeout: int = 600
    name: str = "ollama"

    def complete_json(self, system: str, user: str, schema: dict) -> dict:
        last_error: LLMError | None = None
        for _ in range(self.retries):
            try:
                resp = requests.post(
                    self.url,
                    json={
                        "model": self.model,
                        "messages": [
                            {"role": "system", "content": system},
                            {"role": "user", "content": user},
                        ],
                        "stream": False,
                        "format": schema,
                        "think": False,
                        "options": {"temperature": 0, "num_ctx": 8192},
                    },
                    timeout=self.timeout,
                )
                if resp.status_code >= 400:
                    # 404=モデル未インストール、500=メモリ不足など。本文に理由がある
                    raise LLMError.from_info(
                        "ollama", self.model,
                        FailureInfo(status=resp.status_code, body=resp.text[:500]),
                    )
                return json.loads(resp.json()["message"]["content"])
            except Exception as e:  # 接続断・JSON不正など。リトライで解消することが多い
                last_error = LLMError.from_exception("ollama", self.model, e)
                if not is_retryable(last_error.code):
                    break  # 入っていないモデルは何度呼んでも入っていない
                time.sleep(2)
        assert last_error is not None
        raise last_error
