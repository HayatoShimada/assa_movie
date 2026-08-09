"""M28: torchを入れなくてもGPUを検出できること。

配布物からtorchを外すと、torch頼みの検出では ROCm/CUDA機でも "cpu" と判定され、
whisper.cppではなく遅いエンジンが黙って選ばれてしまう。
ベンダーのCLI(rocm-smi / nvidia-smi)から読む。
"""

import pytest

from backend.core import device

ROCM_MEMORY = """{"card0": {"VRAM Total Memory (B)": "25753026560",
 "VRAM Total Used Memory (B)": "1762021376"}}"""
ROCM_NAME = """{"card0": {"Card series": "Navi 31 [Radeon RX 7900 XT/7900 XTX/7900M]",
 "Card model": "0x5302", "Card vendor": "Advanced Micro Devices, Inc. [AMD/ATI]"}}"""


# ---- rocm-smi の解釈 ----
def test_rocm_smiからVRAMと名前を読む():
    info = device.parse_rocm_smi(ROCM_MEMORY, ROCM_NAME)
    assert info["accel"] == "rocm"
    assert info["vram_total_mb"] == 24560
    # 使用中を引いた残りが空き(バイトで引いてからMBに直す)
    assert info["vram_free_mb"] == int((25753026560 - 1762021376) / 1024**2)
    assert "Radeon RX 7900" in info["name"]


def test_名前が取れなくてもVRAMは使える():
    """--showproductname が失敗しても検出そのものは成立させる"""
    info = device.parse_rocm_smi(ROCM_MEMORY, "")
    assert info["accel"] == "rocm"
    assert info["vram_total_mb"] == 24560
    assert info["name"] == "AMD GPU"


@pytest.mark.parametrize("payload", ["", "not json", "{}", '{"card0": {}}'])
def test_読めない出力はGPU無しとして扱う(payload):
    assert device.parse_rocm_smi(payload, "") == {}


# ---- nvidia-smi の解釈 ----
def test_nvidia_smiの1行を読む():
    info = device.parse_nvidia_smi("NVIDIA GeForce RTX 4090, 24564, 23000")
    assert info == {
        "accel": "cuda",
        "name": "NVIDIA GeForce RTX 4090",
        "vram_total_mb": 24564,
        "vram_free_mb": 23000,
    }


def test_GPUが複数でも先頭を使う():
    out = "RTX 4090, 24564, 23000\nRTX 4090, 24564, 24000"
    assert device.parse_nvidia_smi(out)["vram_free_mb"] == 23000


@pytest.mark.parametrize("payload", ["", "  ", "壊れた出力", "name, notanumber, 1"])
def test_読めないnvidia出力はGPU無しとして扱う(payload):
    assert device.parse_nvidia_smi(payload) == {}


# ---- 選択の順番 ----
# macOSはsystem_profiler経由の別経路なので、OSを明示して他OSの判定を確かめる
# (実行中のOSに任せると、macOSのCIでNVIDIA/AMDの分岐に一切入らない)
def test_NVIDIAが見つかればそれを使う(monkeypatch):
    monkeypatch.setattr(device, "_run", lambda cmd: {
        "nvidia-smi": "RTX 4090, 24564, 23000",
    }.get(cmd[0], ""))
    assert device.probe_gpu_cli(os_name="Linux")["accel"] == "cuda"


def test_AMDが見つかればそれを使う(monkeypatch):
    def fake(cmd):
        if cmd[0] != "rocm-smi":
            return ""
        return ROCM_NAME if "--showproductname" in cmd else ROCM_MEMORY

    monkeypatch.setattr(device, "_run", fake)
    assert device.probe_gpu_cli(os_name="Linux")["accel"] == "rocm"


def test_どちらも無ければ空(monkeypatch):
    monkeypatch.setattr(device, "_run", lambda cmd: "")
    assert device.probe_gpu_cli(os_name="Linux") == {}


def test_macOSはsystem_profilerを見る(monkeypatch):
    """ベンダーCLIはmacOSに無い。呼ぶだけ無駄なので経路を分けている"""
    monkeypatch.setattr(device, "_run", lambda cmd: pytest.fail(f"呼ばれた: {cmd}"))
    monkeypatch.setattr(device, "probe_gpu_mac", lambda: {"accel": "metal"})
    assert device.probe_gpu_cli(os_name="Darwin")["accel"] == "metal"


def test_probe_gpuはCLIで足りればtorchを起動しない(monkeypatch):
    """torchの初期化は実測5秒。表示用の情報のためにそれを払わない"""
    device.probe_gpu.cache_clear()
    called = []
    monkeypatch.setattr(device, "probe_gpu_cli", lambda: {"accel": "rocm", "name": "x",
                                                          "vram_total_mb": 100, "vram_free_mb": 50})
    monkeypatch.setattr(device, "_probe_gpu_torch", lambda: called.append(1) or {})
    assert device.probe_gpu()["accel"] == "rocm"
    assert called == []
    device.probe_gpu.cache_clear()


def test_CLIが無い環境ではtorchに聞く(monkeypatch):
    device.probe_gpu.cache_clear()
    monkeypatch.setattr(device, "probe_gpu_cli", lambda: {})
    monkeypatch.setattr(
        device, "_probe_gpu_torch",
        lambda: {"accel": "cuda", "name": "T", "vram_total_mb": 1, "vram_free_mb": 1},
    )
    assert device.probe_gpu()["accel"] == "cuda"
    device.probe_gpu.cache_clear()


def test_どこからも取れなければcpu(monkeypatch):
    device.probe_gpu.cache_clear()
    monkeypatch.setattr(device, "probe_gpu_cli", lambda: {})
    monkeypatch.setattr(device, "_probe_gpu_torch", lambda: {})
    # OSへの問い合わせも塞ぐ(実機のWindowsで動かすとGPUが見つかってしまう)
    monkeypatch.setattr(device, "probe_gpu_windows", lambda: {})
    assert device.probe_gpu() == {
        "accel": "cpu", "name": "", "vram_total_mb": 0, "vram_free_mb": 0
    }
    device.probe_gpu.cache_clear()


# ---- エンジン選択への影響 ----
def test_torch無しでもROCmと判定できる(monkeypatch):
    """ここが"cpu"になると、whisper.cppがあっても選ばれなくなる"""
    monkeypatch.setattr(device, "_torch", lambda m=None: None)
    monkeypatch.setattr(device, "probe_gpu_cli", lambda: {"accel": "rocm", "name": "AMD",
                                                          "vram_total_mb": 24560,
                                                          "vram_free_mb": 20000})
    device.probe_gpu.cache_clear()
    assert device.detect_accel() == "rocm"
    device.probe_gpu.cache_clear()
