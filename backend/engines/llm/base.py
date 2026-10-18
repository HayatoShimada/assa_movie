"""LLMクライアントの共通インターフェース。

ローカル(Ollama)とクラウド(Anthropic)を差し替え可能にし、
テストでは FakeLLMClient で決定的に動かす。
"""

from dataclasses import dataclass
from typing import Callable, Protocol

from backend.core.errors import UserFacingError


class LLMError(UserFacingError, RuntimeError):
    """AIの呼び出しに失敗した。

    str(e) は利用者向けの平易な日本語+直し方(backend/engines/llm/errors.py が作る)。
    code は失敗の分類(画面やHTTPステータスの出し分けに使う)、
    detail は調査用の生の情報(HTTP本文など)。
    """

    def __init__(self, message: str, code: str = "unknown", detail: str = ""):
        super().__init__(message)
        self.code = code
        self.detail = detail

    @classmethod
    def from_failure(
        cls, provider: str, model: str, *, status: int | None = None,
        network: str | None = None, parse_error: bool = False, body: str = "",
    ) -> "LLMError":
        from backend.engines.llm.errors import FailureInfo

        return cls.from_info(
            provider, model,
            FailureInfo(status=status, network=network, parse_error=parse_error, body=body),
        )

    @classmethod
    def from_info(cls, provider: str, model: str, info) -> "LLMError":
        from backend.engines.llm.errors import describe_failure

        code, message = describe_failure(provider, model, info)
        status = f"HTTP {info.status} " if info.status is not None else ""
        return cls(message, code=code, detail=f"{provider}/{model}: {status}{info.body}"[:2000])

    @classmethod
    def from_exception(cls, provider: str, model: str, exc: BaseException) -> "LLMError":
        if isinstance(exc, LLMError):
            return exc
        from backend.engines.llm.errors import failure_from_exception

        return cls.from_info(provider, model, failure_from_exception(exc))


class LLMConfigError(LLMError, ValueError):
    """設定の不足(APIキー未登録など)で、呼び出す前に使えないと分かった"""


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
