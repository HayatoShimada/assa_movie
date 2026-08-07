"""LLMクライアントの共通インターフェース。

ローカル(Ollama)とクラウド(Anthropic)を差し替え可能にし、
テストでは FakeLLMClient で決定的に動かす。
"""

from dataclasses import dataclass
from typing import Callable, Protocol


class LLMError(RuntimeError):
    pass


class LLMClient(Protocol):
    name: str

    def complete_json(self, system: str, user: str, schema: dict) -> dict:
        """スキーマに従うJSONを返す。失敗時は LLMError を送出する。"""
        ...


@dataclass
class FakeLLMClient:
    """テスト用。あらかじめ用意した応答を順に返す。

    responses: dict のリスト、または (system, user) -> dict の関数
    """

    responses: list[dict] | Callable[[str, str], dict]
    name: str = "fake"

    def __post_init__(self):
        self.calls: list[tuple[str, str]] = []
        self._index = 0

    def complete_json(self, system: str, user: str, schema: dict) -> dict:
        self.calls.append((system, user))
        if callable(self.responses):
            return self.responses(system, user)
        if self._index >= len(self.responses):
            return {"edits": []}  # 応答を使い切ったら空を返す
        out = self.responses[self._index]
        self._index += 1
        if isinstance(out, Exception):
            raise out
        return out
