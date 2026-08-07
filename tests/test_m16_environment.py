"""M16: 環境スキャン(GPU/VRAM/エンコーダ/Ollama)とVRAMベースの推奨のテスト"""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from backend.core.environment import recommend, scan_ollama
from backend.core.device import apply_vram_budget, gpu_info


# ---- gpu_info / apply_vram_budget(fake torchで検証) ----

def _fake_torch(total_mb=24560, free_mb=20000, available=True):
    calls = {}

    def set_fraction(frac, device=0):
        calls["fraction"] = frac

    return SimpleNamespace(
        cuda=SimpleNamespace(
            is_available=lambda: available,
            get_device_name=lambda i=0: "Radeon RX 7900 XTX",
            mem_get_info=lambda: (free_mb * 1024**2, total_mb * 1024**2),
            set_per_process_memory_fraction=set_fraction,
        ),
        version=SimpleNamespace(hip="6.4", cuda=None),
        _calls=calls,
    )


def test_gpu_info_with_gpu():
    info = gpu_info(_fake_torch())
    assert info["name"] == "Radeon RX 7900 XTX"
    assert info["vram_total_mb"] == 24560
    assert info["vram_free_mb"] == 20000


def test_gpu_info_without_gpu():
    assert gpu_info(_fake_torch(available=False)) == {}


def test_apply_vram_budget_sets_fraction():
    fake = _fake_torch(total_mb=24560)
    apply_vram_budget(12280, fake)
    assert fake._calls["fraction"] == pytest.approx(0.5, abs=0.01)


def test_apply_vram_budget_zero_means_unlimited():
    fake = _fake_torch()
    apply_vram_budget(0, fake)
    assert "fraction" not in fake._calls


# ---- recommend: VRAMに収まる最良のASR/LLMを選ぶ(テーブル駆動) ----

INSTALLED = [
    {"name": "qwen3:32b", "vram_mb": 22000},
    {"name": "qwen3:14b", "vram_mb": 10500},
    {"name": "qwen3:8b", "vram_mb": 6300},
]


@pytest.mark.parametrize(
    "name, vram_mb, accel, expected_engine, expected_model, expected_llm",
    [
        # 24GB ROCm機: transformers版large-v3(約10GB)+ qwen3:32b(22GB)…は
        # 同時常駐しないため個別にフィット判定(ASRとLLMは直列実行)
        ("24GB/ROCm", 24560, "rocm", "transformers", "large-v3", "qwen3:32b"),
        ("24GB/CUDA", 24560, "cuda", "faster_whisper", "large-v3", "qwen3:32b"),
        # 12GB: transformers large-v3(10GB)は載る。LLMは14bまで
        ("12GB/ROCm", 12000, "rocm", "transformers", "large-v3", "qwen3:14b"),
        # 8GB: transformersはturbo、LLMは8bまで
        ("8GB/ROCm", 8000, "rocm", "transformers", "large-v3-turbo", "qwen3:8b"),
        # 6GB CUDA: faster-whisperならlarge-v3(5GB)が載る
        ("6GB/CUDA", 6000, "cuda", "faster_whisper", "large-v3", "なし"),
        # GPUなし: CPUのfaster-whisper。速度重視でturbo
        ("CPUのみ", 0, "cpu", "faster_whisper", "large-v3-turbo", "なし"),
    ],
)
def test_recommend_table(name, vram_mb, accel, expected_engine, expected_model, expected_llm):
    rec = recommend(vram_mb, accel, INSTALLED)
    assert rec["asr_engine"] == expected_engine, name
    assert rec["asr_model"] == expected_model, name
    if expected_llm == "なし":
        assert rec["ollama_model"] is None, name
    else:
        assert rec["ollama_model"] == expected_llm, name


def test_recommend_without_installed_models():
    rec = recommend(24560, "rocm", [])
    assert rec["ollama_model"] is None  # 入っていないモデルは推奨しない


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
    assert body["accel"] in ("cuda", "rocm", "cpu")
    assert "gpu" in body and "ffmpeg" in body and "ollama" in body
    assert "recommendations" in body
    assert isinstance(body["asr_options"], list)
    for opt in body["asr_options"]:
        assert {"model", "engine", "vram_mb", "fits"} <= set(opt)


def test_vram_budget_setting_persists(client):
    r = client.patch("/api/settings", json={"vram_budget_mb": 12000})
    assert r.status_code == 200
    assert r.json()["values"]["vram_budget_mb"] == 12000


def test_vram_budget_is_not_project_overridable(client):
    # VRAMはマシン全体の資源なのでプロジェクト単位では上書きできない
    r = client.post("/api/projects", json={
        "name": "x", "settings": {"vram_budget_mb": 8000},
    })
    assert r.status_code == 400
