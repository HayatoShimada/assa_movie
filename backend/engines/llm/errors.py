"""AI(LLM)呼び出しの失敗を、利用者向けの平易な日本語と直し方にする。

以前は「Ollama呼び出しに3回失敗: 404 Client Error…」や
「API 500: Internal Server Error」がそのまま画面に出ていて、
初めて使う人には何をすれば直るのかが分からなかった。

- 判定材料(HTTPステータス・本文・通信失敗の種類)を FailureInfo に集め、
- describe_failure() が (コード, 文言) を決める(純関数・テーブル駆動テスト)。
- 例外から判定材料を取り出す部分(failure_from_exception)だけが
  requests や SDK の形を知っている。
"""

import json
from dataclasses import dataclass

PROVIDER_NAMES = {"ollama": "Ollama", "gemini": "Gemini", "claude": "Claude"}

# 何度呼び直しても結果が変わらない失敗。待たせるだけなので再試行しない
NOT_RETRYABLE = {"model_not_installed", "model_not_found", "invalid_key", "no_key", "refused"}

# Ollamaの本文に出る目印(小文字で比較する)
_NOT_FOUND_HINTS = ("not found", "try pulling")
_OOM_HINTS = ("more system memory", "out of memory", "insufficient memory", "cudamalloc failed")
# Geminiは不正なキーを400で返す
_BAD_KEY_HINTS = ("api key not valid", "api_key_invalid", "invalid x-api-key", "invalid api key")


@dataclass(frozen=True)
class FailureInfo:
    """失敗の判定材料"""

    status: int | None = None  # HTTPステータス(応答があった場合)
    network: str | None = None  # "connect"(接続できない)| "timeout"(応答が来ない)
    parse_error: bool = False  # 応答は来たがJSONとして読めなかった
    body: str = ""  # 応答本文や例外メッセージ(調査用。利用者には見せない)


def _model_label(provider: str, model: str) -> str:
    return f"{PROVIDER_NAMES.get(provider, provider)}・{model}" if model else PROVIDER_NAMES.get(provider, provider)


def describe_failure(provider: str, model: str, info: FailureInfo) -> tuple[str, str]:
    """失敗を (コード, 利用者向けの文言) にする(純関数)。

    文言には「何が起きたか」と「どうすれば直るか」を必ず両方入れる。
    HTTPの英語や再試行回数などの内部事情は入れない(詳細は LLMError.detail に残す)。
    """
    name = PROVIDER_NAMES.get(provider, provider)
    body = (info.body or "").lower()
    status = info.status

    if provider == "ollama":
        if info.network == "connect":
            return "ollama_unreachable", (
                "Ollama が起動していません。Ollama を起動してから、もう一度実行してください"
                "(まだ入れていなければ ollama.com から導入できます)。"
                "クラウドのAI(Gemini / Claude)を使う場合は、設定タブの「AI」で切り替えてください。"
            )
        if status == 404 or any(h in body for h in _NOT_FOUND_HINTS):
            return "model_not_installed", (
                f"AIモデル「{model}」がインストールされていません。"
                f"設定タブの「AI」でインストール済みのモデルを選ぶか、"
                f"ターミナルで `ollama pull {model}` を実行してください。"
            )
        if any(h in body for h in _OOM_HINTS):
            return "out_of_memory", (
                f"AIモデル「{model}」を動かすメモリが足りません。"
                "設定タブの「AI」でもっと小さいモデルを選んでください。"
            )
    else:
        if info.network == "connect":
            return "offline", (
                f"{name} に接続できません。インターネット接続を確認してから、もう一度実行してください。"
            )
        if status in (401, 403) or any(h in body for h in _BAD_KEY_HINTS):
            return "invalid_key", (
                f"{name} の APIキーが正しくありません。設定タブの「APIキー」で登録し直してください。"
            )
        if status == 404:
            return "model_not_found", (
                f"{name} でAIモデル「{model}」が見つかりません。設定タブの「AI」で別のモデルを選んでください。"
            )
        if status == 429:
            return "rate_limited", (
                f"{name} の利用上限(回数・料金枠)に達しました。"
                "しばらく待ってから再実行するか、利用枠を確認してください。"
            )

    if info.network == "timeout":
        return "timeout", (
            f"AI({_model_label(provider, model)})の応答が時間内に返りませんでした。"
            "PCの負荷が高いか、モデルが大きすぎる可能性があります。"
            "小さいモデルを選ぶか、時間をおいて再実行してください。"
        )
    if status is not None and status >= 500:
        if provider == "ollama":
            return "server_error", (
                f"Ollama でエラーが起きました(AIモデル「{model}」)。"
                "Ollama を再起動してから、もう一度実行してください。"
                "続く場合は設定タブの「AI」で別のモデルを選んでください。"
            )
        return "server_error", (
            f"{name} のサーバーで一時的なエラーが起きました。時間をおいて再実行してください。"
        )
    if info.parse_error:
        return "bad_response", (
            f"AI({_model_label(provider, model)})の応答を読み取れませんでした。"
            "もう一度実行するか、設定タブの「AI」で別のモデルを選んでください。"
        )
    return "unknown", (
        f"AI({_model_label(provider, model)})の呼び出しに失敗しました。"
        "時間をおいてもう一度実行してください。"
        "続く場合は設定タブの「AI」で別のモデルかAIの種類を選んでください。"
    )


def no_key_message(provider: str) -> str:
    name = PROVIDER_NAMES.get(provider, provider)
    return (
        f"{name} の APIキーが登録されていません。"
        "設定タブの「APIキー」で登録するか、設定タブの「AI」でローカル(Ollama)に切り替えてください。"
    )


def is_retryable(code: str) -> bool:
    """再試行で直る見込みがあるか(純関数)"""
    return code not in NOT_RETRYABLE


def http_status(code: str) -> int:
    """HTTP APIで返すステータス(純関数)。

    500は「アプリの不具合」に見えるので使わない。AIが使えない状態は503、
    待ち切れは504、AIの応答そのものがおかしいときは502。
    """
    if code == "timeout":
        return 504
    if code in ("bad_response", "refused", "too_long", "unknown"):
        return 502
    return 503


def _class_names(exc: BaseException) -> set[str]:
    return {c.__name__ for c in type(exc).__mro__}


def failure_from_exception(exc: BaseException) -> FailureInfo:
    """例外から判定材料を取り出す。

    requests と anthropic SDK の例外の形をここだけが知っている
    (SDKは配布物に入っているが、型でなく名前で見て import に依存しない)。
    """
    names = _class_names(exc)
    if names & {"Timeout", "ReadTimeout", "ConnectTimeout", "APITimeoutError", "TimeoutError"}:
        return FailureInfo(network="timeout", body=str(exc))
    if names & {"ConnectionError", "APIConnectionError"}:
        return FailureInfo(network="connect", body=str(exc))
    if isinstance(exc, json.JSONDecodeError) or names & {"KeyError", "IndexError"}:
        return FailureInfo(parse_error=True, body=str(exc))

    response = getattr(exc, "response", None)
    status = getattr(exc, "status_code", None)
    if status is None and response is not None:
        status = getattr(response, "status_code", None)
    body = str(exc)
    text = getattr(response, "text", None)
    if isinstance(text, str) and text:
        body = f"{body} {text}"
    return FailureInfo(status=status if isinstance(status, int) else None, body=body)
