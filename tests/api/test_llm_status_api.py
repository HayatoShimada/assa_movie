"""GET /api/llm/status: 保存済みのAI設定で実際に動くか(ホーム/編集画面の警告用)"""

from backend.core import hwprofile
from backend.core.hwprofile import HwProfile

INSTALLED = {"reachable": True, "models": [
    {"name": "gemma4:26b", "vram_mb": 20402},
    {"name": "qwen2.5:32b", "vram_mb": 21771},
]}
GPU = HwProfile(os="linux", gpu="radeon", gpu_name="RX 7900 XTX",
                vram_total_mb=24560, whispercpp_ok=False, detected_at="t")


def _patch(monkeypatch, ollama=INSTALLED):
    hwprofile.set_current(GPU)
    monkeypatch.setattr("backend.core.environment.scan_ollama", lambda url: ollama)


def test_未インストールのモデルを警告しおすすめを返す(client, monkeypatch):
    _patch(monkeypatch)
    client.patch("/api/settings", json={"llm_provider": "ollama", "ollama_model": "qwen3:32b"})
    body = client.get("/api/llm/status").json()
    assert body["ok"] is False
    assert body["code"] == "model_not_installed"
    assert body["recommended_model"] == "qwen2.5:32b"
    assert body["pull_command"] == "ollama pull qwen3:32b"
    assert body["overridden_by_project"] is False


def test_インストール済みなら問題なし(client, monkeypatch):
    _patch(monkeypatch)
    client.patch("/api/settings", json={"llm_provider": "ollama", "ollama_model": "gemma4:26b"})
    body = client.get("/api/llm/status").json()
    assert body["ok"] is True
    assert body["model"] == "gemma4:26b"


def test_プロジェクトの上書きを反映する(client, monkeypatch):
    """設定は3層。編集画面ではプロジェクトで上書きしたモデルが実際に使われる"""
    _patch(monkeypatch)
    client.patch("/api/settings", json={"llm_provider": "ollama", "ollama_model": "gemma4:26b"})
    pid = client.post(
        "/api/projects", json={"name": "p", "settings": {"ollama_model": "qwen3:32b"}}
    ).json()["id"]
    body = client.get(f"/api/llm/status?project_id={pid}").json()
    assert body["code"] == "model_not_installed"
    assert body["model"] == "qwen3:32b"
    assert body["overridden_by_project"] is True
    # グローバルでは問題ない
    assert client.get("/api/llm/status").json()["ok"] is True


def test_Ollama未起動(client, monkeypatch):
    _patch(monkeypatch, ollama={"reachable": False, "models": []})
    client.patch("/api/settings", json={"llm_provider": "ollama"})
    body = client.get("/api/llm/status").json()
    assert body["code"] == "ollama_unreachable"
