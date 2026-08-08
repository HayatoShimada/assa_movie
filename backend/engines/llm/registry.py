"""LLMプロバイダの選択。ローカル(Ollama)とクラウド(Gemini / Claude)を切り替える。"""

from dataclasses import dataclass

from backend.engines.llm.base import LLMClient
from backend.engines.llm.claude import DEFAULT_MODEL as CLAUDE_DEFAULT
from backend.engines.llm.claude import ClaudeClient
from backend.engines.llm.claude import load_api_key as load_claude_key
from backend.engines.llm.gemini import DEFAULT_MODEL as GEMINI_DEFAULT
from backend.engines.llm.gemini import GeminiClient, load_api_key
from backend.engines.llm.ollama import OllamaClient


@dataclass(frozen=True)
class ProviderInfo:
    id: str
    label: str
    local: bool
    models: tuple[str, ...]
    note: str = ""


PROVIDERS: dict[str, ProviderInfo] = {
    "ollama": ProviderInfo(
        id="ollama",
        label="ローカル(Ollama)",
        local=True,
        models=("qwen3:32b", "qwen3:14b", "gpt-oss:120b"),
        note="完全ローカルで動作し、文字起こしが外部に送信されません。",
    ),
    "gemini": ProviderInfo(
        id="gemini",
        label="Gemini API(クラウド)",
        local=False,
        models=("gemini-3.5-flash", "gemini-3.5-pro", "gemini-3.6-flash"),
        note="高精度・高速ですが、文字起こしがGoogleに送信されます。APIキーが必要です。",
    ),
    "claude": ProviderInfo(
        id="claude",
        label="Claude API(クラウド)",
        local=False,
        models=("claude-opus-5", "claude-sonnet-5", "claude-haiku-4-5"),
        note="日本語の文脈判断が得意ですが、文字起こしがAnthropicに送信されます。APIキーが必要です。",
    ),
}


def build_client(settings) -> LLMClient:
    """設定からLLMクライアントを組み立てる"""
    provider = settings.llm_provider
    if provider not in PROVIDERS:
        raise ValueError(
            f"未対応のLLMプロバイダ: {provider}(選択肢: {', '.join(PROVIDERS)})"
        )

    if provider == "ollama":
        return OllamaClient(
            url=settings.ollama_url,
            model=settings.ollama_model,
            retries=settings.llm_retries,
        )

    if provider == "claude":
        api_key = load_claude_key(settings.claude_key_file)
        if not api_key:
            raise ValueError(
                "Claude APIキーが設定されていません。設定タブで登録するか、"
                "環境変数 ANTHROPIC_API_KEY を設定してください。"
            )
        return ClaudeClient(
            api_key=api_key,
            model=settings.claude_model or CLAUDE_DEFAULT,
            retries=settings.llm_retries,
        )

    api_key = load_api_key(settings.gemini_key_file)
    if not api_key:
        raise ValueError(
            "Gemini APIキーが設定されていません。"
            "環境変数 GEMINI_API_KEY を設定するか gemini_api_key.txt に記述してください。"
        )
    return GeminiClient(
        api_key=api_key,
        model=settings.gemini_model or GEMINI_DEFAULT,
        retries=settings.llm_retries,
    )
