"""AIの失敗を利用者向けの文言にする(純関数・テーブル駆動)。

以前はジョブのエラーが「Ollama呼び出しに3回失敗: 404 Client Error…」、
AIに指示が「API 500: Internal Server Error」のまま画面に出ていて、
何をすれば直るのかが分からなかった。判定と文言はここで固定する。
"""

import pytest
import requests

from backend.engines.llm.errors import (
    FailureInfo,
    describe_failure,
    failure_from_exception,
    http_status,
    is_retryable,
)

OLLAMA_404 = '{"error":"model \\"qwen3:32b\\" not found, try pulling it first"}'
OLLAMA_OOM = '{"error":"model requires more system memory (40.0 GiB) than is available (20.1 GiB)"}'

# (provider, model, FailureInfo, 期待するコード, 文言に含まれるべき語)
CASES = [
    pytest.param(
        "ollama", "qwen3:32b", FailureInfo(status=404, body=OLLAMA_404),
        "model_not_installed", ["qwen3:32b", "インストールされていません", "ollama pull qwen3:32b", "設定"],
        id="Ollamaのモデル未インストール(404)",
    ),
    pytest.param(
        "ollama", "qwen3:32b", FailureInfo(status=500, body='{"error":"model \\"qwen3:32b\\" not found"}'),
        "model_not_installed", ["ollama pull qwen3:32b"],
        id="Ollamaのモデル未インストール(本文で判定)",
    ),
    pytest.param(
        "ollama", "qwen2.5:32b", FailureInfo(network="connect"),
        "ollama_unreachable", ["Ollama が起動していません", "ollama.com"],
        id="Ollama未起動",
    ),
    pytest.param(
        "ollama", "qwen2.5:32b", FailureInfo(status=500, body=OLLAMA_OOM),
        "out_of_memory", ["qwen2.5:32b", "メモリが足りません", "小さいモデル"],
        id="Ollamaのメモリ不足",
    ),
    pytest.param(
        "ollama", "qwen2.5:32b", FailureInfo(status=500, body='{"error":"unexpected EOF"}'),
        "server_error", ["Ollama", "再起動"],
        id="Ollamaの内部エラー",
    ),
    pytest.param(
        "ollama", "qwen2.5:32b", FailureInfo(network="timeout"),
        "timeout", ["時間内に", "小さいモデル"],
        id="Ollamaの応答待ち切れ",
    ),
    pytest.param(
        "gemini", "gemini-3.5-flash", FailureInfo(status=401, body="API key not valid"),
        "invalid_key", ["Gemini", "APIキーが正しくありません", "設定タブ"],
        id="GeminiのAPIキー不正(401)",
    ),
    pytest.param(
        "gemini", "gemini-3.5-flash", FailureInfo(status=400, body='{"error":{"message":"API key not valid. Please pass a valid API key."}}'),
        "invalid_key", ["APIキーが正しくありません"],
        id="GeminiのAPIキー不正(400で返る)",
    ),
    pytest.param(
        "claude", "claude-opus-5", FailureInfo(status=403, body="permission"),
        "invalid_key", ["Claude", "APIキーが正しくありません"],
        id="ClaudeのAPIキー不正(403)",
    ),
    pytest.param(
        "gemini", "gemini-9", FailureInfo(status=404, body="models/gemini-9 is not found"),
        "model_not_found", ["gemini-9", "見つかりません", "別のモデル"],
        id="クラウドのモデル名違い",
    ),
    pytest.param(
        "claude", "claude-opus-5", FailureInfo(status=429, body="rate_limit_error"),
        "rate_limited", ["利用上限", "しばらく待って"],
        id="クラウドの利用上限",
    ),
    pytest.param(
        "gemini", "gemini-3.5-flash", FailureInfo(status=503, body="overloaded"),
        "server_error", ["Gemini", "時間をおいて"],
        id="クラウドの一時的な障害",
    ),
    pytest.param(
        "claude", "claude-opus-5", FailureInfo(network="connect"),
        "offline", ["Claude", "インターネット接続"],
        id="クラウドに接続できない",
    ),
    pytest.param(
        "ollama", "qwen2.5:32b", FailureInfo(parse_error=True, body="Expecting value: line 1 column 1"),
        "bad_response", ["読み取れませんでした", "別のモデル"],
        id="応答のJSONが壊れている",
    ),
    pytest.param(
        "claude", "claude-opus-5", FailureInfo(body="something odd"),
        "unknown", ["Claude", "もう一度"],
        id="分類できない失敗",
    ),
]


@pytest.mark.parametrize("provider,model,info,code,words", CASES)
def test_失敗を利用者向けの文言にする(provider, model, info, code, words):
    got_code, message = describe_failure(provider, model, info)
    assert got_code == code
    for word in words:
        assert word in message, f"「{word}」が文言に無い: {message}"


@pytest.mark.parametrize("provider,model,info,code,words", CASES)
def test_生のエラーをそのまま見せない(provider, model, info, code, words):
    """HTTPの英語や「3回失敗」などの内部事情は文言に混ぜない(詳細は別に残す)"""
    _, message = describe_failure(provider, model, info)
    for raw in ("Client Error", "Internal Server Error", "回失敗", "Traceback", "{"):
        assert raw not in message


@pytest.mark.parametrize(
    "code,retry",
    [
        ("model_not_installed", False),  # 何度呼んでも入っていない
        ("model_not_found", False),
        ("invalid_key", False),
        ("ollama_unreachable", True),  # 起動直後で間に合わないことがある
        ("server_error", True),
        ("rate_limited", True),
        ("timeout", True),
        ("bad_response", True),  # 出力の揺れで直ることが多い
        ("offline", True),
    ],
)
def test_再試行しても無駄な失敗は再試行しない(code, retry):
    assert is_retryable(code) is retry


@pytest.mark.parametrize(
    "code,status",
    [
        ("model_not_installed", 503),
        ("ollama_unreachable", 503),
        ("invalid_key", 503),
        ("no_key", 503),
        ("rate_limited", 503),
        ("timeout", 504),
        ("bad_response", 502),
        ("refused", 502),
    ],
)
def test_HTTPのステータスは500にしない(code, status):
    """500は「アプリの不具合」に見える。AI側の問題は502/503/504で返す"""
    assert http_status(code) == status


# ---- 例外から判定材料を取り出す ----
class _Resp:
    def __init__(self, status, text):
        self.status_code = status
        self.text = text


def test_requestsの接続失敗は未起動として扱う():
    info = failure_from_exception(requests.ConnectionError("Connection refused"))
    assert info.network == "connect"


def test_requestsのタイムアウト():
    info = failure_from_exception(requests.ReadTimeout("read timed out"))
    assert info.network == "timeout"


def test_HTTPErrorからステータスと本文を取る():
    err = requests.HTTPError("404 Client Error")
    err.response = _Resp(404, OLLAMA_404)
    info = failure_from_exception(err)
    assert info.status == 404
    assert "not found" in info.body


def test_JSONの解釈失敗は応答が壊れている扱い():
    import json

    try:
        json.loads("これはJSONではない")
    except json.JSONDecodeError as e:
        assert failure_from_exception(e).parse_error is True


def test_SDKの例外のstatus_codeを読む():
    """anthropic SDKの例外は status_code を持つ(SDKを入れずに形だけ真似る)"""

    class AuthenticationError(Exception):
        status_code = 401

    info = failure_from_exception(AuthenticationError("invalid x-api-key"))
    assert info.status == 401


def test_SDKの接続失敗をクラス名で判定する():
    class APIConnectionError(Exception):
        pass

    class APITimeoutError(APIConnectionError):
        pass

    assert failure_from_exception(APIConnectionError("x")).network == "connect"
    assert failure_from_exception(APITimeoutError("x")).network == "timeout"
