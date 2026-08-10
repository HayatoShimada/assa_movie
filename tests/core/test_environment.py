"""M16: 環境情報(プロファイル・確定構成・エンコーダ・Ollama)とモデル推奨のテスト。

エンジンの選択はプロファイル(tests/core/test_hwprofile.py)が決める。
ここではその表示用整形と、VRAMに応じたモデル推奨だけを見る。
"""

import pytest

from backend.core import hwprofile
from backend.core.environment import profile_warnings, recommend, scan_ollama
from backend.core.hwprofile import HwProfile, resolve_spec

GPU = HwProfile(os="linux", gpu="radeon", gpu_name="RX 7900 XTX",
                vram_total_mb=24560, whispercpp_ok=True, detected_at="t")
CPU = HwProfile(os="linux", gpu="cpu", detected_at="t")


@pytest.fixture(autouse=True)
def reset_profile():
    hwprofile.set_current(CPU)
    yield
    hwprofile.set_current(None)


# ---- recommend: VRAMに収まる最良のASRモデル/LLMを選ぶ(テーブル駆動) ----

INSTALLED = [
    {"name": "qwen3:32b", "vram_mb": 22000},
    {"name": "qwen3:14b", "vram_mb": 10500},
    {"name": "qwen3:8b", "vram_mb": 6300},
]


@pytest.mark.parametrize(
    "name, vram_mb, engine, expected_model, expected_llm",
    [
        # GPU実行(whisper.cpp): 精度優先で収まる最大モデル。
        # ASRとLLMは直列実行(ASRをunloadしてからLLM)なので個別にフィット判定する
        ("24GB/GPU", 24560, "whispercpp", "large-v3", "qwen3:32b"),
        ("12GB/GPU", 12000, "whispercpp", "large-v3", "qwen3:14b"),
        # 6GB: large-v3(5GB)は載るが、qwen3:8b(6.3GB)は収まらない
        ("6GB/GPU", 6000, "whispercpp", "large-v3", "なし"),
        ("7GB/GPU", 7000, "whispercpp", "large-v3", "qwen3:8b"),
        # 4GB: large-v3(5GB)は載らないのでturbo。LLMは何も収まらない
        ("4GB/GPU", 4000, "whispercpp", "large-v3-turbo", "なし"),
        # 何も収まらない極小VRAMでも、最も軽いものを提示する(空にしない)
        ("1GB/GPU", 1000, "whispercpp", "large-v3-turbo", "なし"),
        # CPU実行: VRAM制約なし。実用速度を優先して速い方
        ("CPU実行", 0, "faster_whisper", "large-v3-turbo", "なし"),
    ],
)
def test_recommend_table(name, vram_mb, engine, expected_model, expected_llm):
    rec = recommend(vram_mb, engine, INSTALLED)
    assert rec["asr_model"] == expected_model, name
    if expected_llm == "なし":
        assert rec["ollama_model"] is None, name
    else:
        assert rec["ollama_model"] == expected_llm, name


def test_recommend_エンジンは決めない():
    """エンジンはプロファイルで確定済み。推奨に混ぜると二重管理になる"""
    assert "asr_engine" not in recommend(24560, "whispercpp", INSTALLED)


def test_recommend_without_installed_models():
    rec = recommend(24560, "whispercpp", [])
    assert rec["ollama_model"] is None  # 入っていないモデルは推奨しない


# ---- 警告の組み立て(純関数) ----

def test_警告_正常な機体では何も出ない():
    assert profile_warnings(GPU, resolve_spec(GPU)) == []
    assert profile_warnings(CPU, resolve_spec(CPU)) == []


def test_警告_GPUがあるのにwhispercppを起動できない機体():
    """検出時にcpu構成へ落ちている。その理由と直し方を伝える"""
    broken = HwProfile(os="linux", gpu="nvidia", gpu_name="RTX 4070",
                       whispercpp_ok=False, detected_at="t")
    warnings = profile_warnings(broken, resolve_spec(broken))
    assert len(warnings) == 1
    assert "再検出" in warnings[0]


# ---- scan_ollama(HTTPはfake) ----

def test_scan_ollama_parses_tags(monkeypatch):
    class FakeResp:
        status_code = 200

        def json(self):
            return {"models": [
                {"name": "qwen3:32b", "size": 20 * 1024**3},
                {"name": "qwen3:8b", "size": 5 * 1024**3},
            ]}

    monkeypatch.setattr("requests.get", lambda url, timeout: FakeResp())
    out = scan_ollama("http://localhost:11434/api/chat")
    assert out["reachable"] is True
    names = [m["name"] for m in out["models"]]
    assert names == ["qwen3:32b", "qwen3:8b"]
    # VRAM目安はファイルサイズ+ランタイムのオーバーヘッド分で見積もる
    assert out["models"][0]["vram_mb"] > 20 * 1024


def test_scan_ollama_unreachable(monkeypatch):
    import requests

    def boom(url, timeout):
        raise requests.ConnectionError("接続不可")

    monkeypatch.setattr("requests.get", boom)
    out = scan_ollama("http://localhost:11434/api/chat")
    assert out == {"reachable": False, "models": []}


# ---- API ----

def test_environment_api_shape(client):
    body = client.get("/api/environment").json()
    assert body["profile"]["os"] in ("linux", "windows", "mac")
    assert body["profile"]["gpu"] in ("nvidia", "radeon", "apple", "cpu")
    assert body["resolved"]["engine"] in ("whispercpp", "faster_whisper")
    assert body["resolved"]["label"]
    assert isinstance(body["warnings"], list)
    assert "ffmpeg" in body and "ollama" in body
    assert "recommendations" in body


def test_environment_api_は廃止フィールドを返さない(client):
    body = client.get("/api/environment").json()
    for gone in ("accel", "gpu_compute", "cuda_libs_missing", "vram_budget_mb"):
        assert gone not in body


def test_environment_api_はGPU機の情報を出す(client):
    hwprofile.set_current(GPU)
    body = client.get("/api/environment").json()
    assert body["gpu"]["name"] == "RX 7900 XTX"
    assert body["resolved"]["engine"] == "whispercpp"
    # GPU実行なのでVRAMに収まるモデルが推奨される
    assert body["recommendations"]["asr_model"] == "large-v3"


def test_再検出APIでプロファイルが更新される(client, monkeypatch):
    hwprofile.set_current(CPU)
    monkeypatch.setattr(
        hwprofile, "detect",
        lambda now, runner=None, os_name=None: GPU,
    )
    body = client.post("/api/environment/redetect").json()
    assert body["profile"]["gpu"] == "radeon"
    assert hwprofile.current() == GPU
