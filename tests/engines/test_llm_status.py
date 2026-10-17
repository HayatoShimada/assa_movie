"""AIが使える状態かの事前診断(ホーム/編集画面の警告用)。

評価で、既定の Ollama モデル(qwen3:32b)が入っていない機体だと、AI機能を
押すたびに失敗するまで気付けなかった。押す前に分かるようにする。
"""

import pytest

from backend.engines.llm.status import diagnose

OLLAMA_UP = {"reachable": True, "models": [
    {"name": "gemma4:26b", "vram_mb": 20402},
    {"name": "qwen2.5:32b", "vram_mb": 21771},
]}
OLLAMA_DOWN = {"reachable": False, "models": []}


@pytest.mark.parametrize(
    "name, provider, model, ollama, key_ready, code",
    [
        ("インストール済みのモデル", "ollama", "qwen2.5:32b", OLLAMA_UP, False, None),
        ("未インストールのモデル", "ollama", "qwen3:32b", OLLAMA_UP, False, "model_not_installed"),
        # タグ省略(:latest)はOllamaの表記ゆれ。入っているのに警告しない
        ("latest省略", "ollama", "gemma4", {"reachable": True, "models": [{"name": "gemma4:latest", "vram_mb": 1}]}, False, None),
        ("Ollama未起動", "ollama", "qwen2.5:32b", OLLAMA_DOWN, False, "ollama_unreachable"),
        ("クラウドでキーあり", "gemini", "gemini-3.5-flash", OLLAMA_DOWN, True, None),
        ("クラウドでキーなし", "claude", "claude-opus-5", OLLAMA_UP, False, "no_key"),
    ],
)
def test_診断表(name, provider, model, ollama, key_ready, code):
    out = diagnose(provider, model, ollama, key_ready=key_ready, recommended="qwen2.5:32b")
    assert out["code"] == code, name
    assert out["ok"] is (code is None), name


def test_未インストールなら直し方を3つ示す():
    out = diagnose("ollama", "qwen3:32b", OLLAMA_UP, key_ready=False, recommended="qwen2.5:32b")
    assert "qwen3:32b" in out["message"]
    assert "インストールされていません" in out["message"]
    # おすすめ設定を適用 / 別のモデルを選ぶ / ollama pull
    assert out["recommended_model"] == "qwen2.5:32b"
    assert out["installed_models"] == ["gemma4:26b", "qwen2.5:32b"]
    assert out["pull_command"] == "ollama pull qwen3:32b"


def test_おすすめが無ければ入っているモデルの中から案内する():
    """VRAMに収まるものが無い機体でも、入っているモデルなら動く(遅いだけ)"""
    out = diagnose("ollama", "qwen3:32b", OLLAMA_UP, key_ready=False, recommended=None)
    assert out["recommended_model"] is None
    assert out["installed_models"] == ["gemma4:26b", "qwen2.5:32b"]


def test_Ollama未起動の文言は起動とクラウド切替を案内する():
    out = diagnose("ollama", "qwen2.5:32b", OLLAMA_DOWN, key_ready=False, recommended=None)
    assert "Ollama が起動していません" in out["message"]
    assert "クラウド" in out["message"]
    assert out["pull_command"] is None


def test_使えるときは何も言わない():
    out = diagnose("ollama", "qwen2.5:32b", OLLAMA_UP, key_ready=False, recommended=None)
    assert out["message"] == ""
