"""Ollamaクライアント(ローカルLLM)。"""

import json
import time
from dataclasses import dataclass

import requests

from backend.engines.llm.base import LLMError


@dataclass
class OllamaClient:
    url: str = "http://localhost:11434/api/chat"
    model: str = "qwen3:32b"
    retries: int = 3
    timeout: int = 600
    name: str = "ollama"

    def complete_json(self, system: str, user: str, schema: dict) -> dict:
        last_error = None
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
                resp.raise_for_status()
                return json.loads(resp.json()["message"]["content"])
            except Exception as e:  # 接続断・JSON不正など。リトライで解消することが多い
                last_error = e
                time.sleep(2)
        raise LLMError(f"Ollama呼び出しに{self.retries}回失敗: {last_error}")


def build_client(settings):
    """設定からLLMクライアントを組み立てる"""
    if settings.llm_provider == "ollama":
        return OllamaClient(
            url=settings.ollama_url,
            model=settings.ollama_model,
            retries=settings.llm_retries,
        )
    raise ValueError(f"未対応のLLMプロバイダ: {settings.llm_provider}")
