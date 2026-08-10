"""ハードウェアプロファイル(初回検出で固定する実行環境)のテスト。

設計(DESIGN.md 2026-08-10): エンジン選択は実行時の自動判定をやめ、
検出済みプロファイル(OS×GPUクラス)からコード内の静的対応表で決める。
"""

import pytest

from backend.core.hwprofile import (
    EngineSpec,
    HwProfile,
    classify,
    detect,
    resolve_spec,
    verify_whispercpp,
)


# ---- classify: probe結果 → (os, gpu) の分類(純関数・テーブル駆動) ----
@pytest.mark.parametrize(
    "name, probe, os_name, expected",
    [
        # Linux: nvidia-smiが通ればNVIDIA
        ("Linux+NVIDIA", {"accel": "cuda", "name": "NVIDIA GeForce RTX 4070"}, "Linux",
         ("linux", "nvidia")),
        # Linux: rocm-smiが通ればRadeon
        ("Linux+Radeon", {"accel": "rocm", "name": "RX 7900 XTX"}, "Linux",
         ("linux", "radeon")),
        # Linux: GPUなし
        ("Linux+CPU", {"accel": "cpu", "name": ""}, "Linux", ("linux", "cpu")),
        # Windows: NVIDIAはnvidia-smi(ドライバ同梱)で拾える
        ("Windows+NVIDIA", {"accel": "cuda", "name": "NVIDIA GeForce RTX 4080"}, "Windows",
         ("windows", "nvidia")),
        # Windows+AMD: rocm-smiが無いのでレジストリ由来(accel=cpu)。名前で判定する
        ("Windows+Radeon", {"accel": "cpu", "name": "AMD Radeon RX 7900 XTX"}, "Windows",
         ("windows", "radeon")),
        ("Windows+GeForce名判定", {"accel": "cpu", "name": "NVIDIA GeForce GTX 1660"}, "Windows",
         ("windows", "nvidia")),
        ("Windows+CPU", {"accel": "cpu", "name": ""}, "Windows", ("windows", "cpu")),
        # mac: Apple Silicon
        ("mac+Apple", {"accel": "metal", "name": "Apple M3 Max"}, "Darwin", ("mac", "apple")),
        # Intel MacはGPU計算対象外(CPU扱い)
        ("mac+Intel", {"accel": "cpu", "name": ""}, "Darwin", ("mac", "cpu")),
        # 表示アダプタ名が仮想アダプタ等でGPUと判定できない場合
        ("Windows+不明アダプタ", {"accel": "cpu", "name": "Virtual Display"}, "Windows",
         ("windows", "cpu")),
    ],
)
def test_classify_table(name, probe, os_name, expected):
    assert classify(probe, os_name) == expected, name


def test_classify_probeが空でもcpuに落ちる():
    assert classify({}, "Linux") == ("linux", "cpu")


# ---- resolve_spec: プロファイル → エンジン構成(静的対応表) ----
def _profile(os="linux", gpu="nvidia", whispercpp_ok=True):
    return HwProfile(os=os, gpu=gpu, gpu_name="GPU", vram_total_mb=8000,
                     whispercpp_ok=whispercpp_ok, detected_at="2026-08-10T00:00:00")


@pytest.mark.parametrize(
    "os_key, gpu, expected_engine, expected_device",
    [
        # GPU機はOS・ベンダーに関わらずwhisper.cppに統一(ユーザー決定)
        ("linux", "nvidia", "whispercpp", "vulkan"),
        ("linux", "radeon", "whispercpp", "vulkan"),
        ("windows", "nvidia", "whispercpp", "vulkan"),
        ("windows", "radeon", "whispercpp", "vulkan"),
        ("mac", "apple", "whispercpp", "metal"),
        # CPU機はfaster-whisper int8(モデルDL不要で必ず動く)
        ("linux", "cpu", "faster_whisper", "cpu"),
        ("windows", "cpu", "faster_whisper", "cpu"),
        ("mac", "cpu", "faster_whisper", "cpu"),
    ],
)
def test_resolve_spec_table(os_key, gpu, expected_engine, expected_device):
    spec = resolve_spec(_profile(os=os_key, gpu=gpu))
    assert spec.engine == expected_engine
    assert spec.device == expected_device
    if expected_engine == "whispercpp":
        assert spec.needs_whispercpp_model is True
        assert spec.compute_type == ""
    else:
        assert spec.needs_whispercpp_model is False
        assert spec.compute_type == "int8"


def test_resolve_spec_whispercpp検証に失敗した機体はcpu構成に確定する():
    """検証失敗はプロファイル確定時にcpu行へ落とす(実行時フォールバックではない)"""
    spec = resolve_spec(_profile(gpu="nvidia", whispercpp_ok=False))
    assert spec.engine == "faster_whisper"
    assert spec.device == "cpu"


def test_resolve_spec_labelは表示に使える日本語込みの文字列():
    assert "whisper.cpp" in resolve_spec(_profile()).label
    assert "faster-whisper" in resolve_spec(_profile(gpu="cpu")).label


# ---- verify_whispercpp: 同梱バイナリの実行検証 ----
def test_verify_whispercpp_バイナリが無ければFalse(monkeypatch):
    monkeypatch.setattr("backend.engines.asr.whispercpp.resolve_binary", lambda: None)
    assert verify_whispercpp() is False


def test_verify_whispercpp_起動できればTrue(monkeypatch, tmp_path):
    binary = tmp_path / "whisper-cli"
    binary.write_bytes(b"")
    monkeypatch.setattr("backend.engines.asr.whispercpp.resolve_binary", lambda: binary)
    calls = {}

    def runner(cmd, timeout):
        calls["cmd"] = cmd
        return 0

    assert verify_whispercpp(runner=runner) is True
    assert calls["cmd"][0] == str(binary)


def test_verify_whispercpp_起動に失敗すればFalse(monkeypatch, tmp_path):
    """Vulkanローダ欠落等で起動できないバイナリを検出時に見抜く"""
    binary = tmp_path / "whisper-cli"
    binary.write_bytes(b"")
    monkeypatch.setattr("backend.engines.asr.whispercpp.resolve_binary", lambda: binary)
    assert verify_whispercpp(runner=lambda cmd, timeout: 1) is False


def test_verify_whispercpp_実行例外もFalse(monkeypatch, tmp_path):
    binary = tmp_path / "whisper-cli"
    binary.write_bytes(b"")
    monkeypatch.setattr("backend.engines.asr.whispercpp.resolve_binary", lambda: binary)

    def boom(cmd, timeout):
        raise OSError("exec format error")

    assert verify_whispercpp(runner=boom) is False


# ---- detect: probe→分類→検証→プロファイル ----
def test_detect_組み立て(monkeypatch):
    monkeypatch.setattr(
        "backend.core.device.probe_gpu",
        lambda: {"accel": "cuda", "name": "NVIDIA RTX PRO 6000",
                 "vram_total_mb": 97887, "vram_free_mb": 90000},
    )
    profile = detect(now="2026-08-10T12:00:00", runner=lambda cmd, timeout: 0,
                     os_name="Linux")
    assert profile.os == "linux"
    assert profile.gpu == "nvidia"
    assert profile.gpu_name == "NVIDIA RTX PRO 6000"
    assert profile.vram_total_mb == 97887
    assert profile.whispercpp_ok in (True, False)  # バイナリ有無に依存(検証は別テスト)
    assert profile.detected_at == "2026-08-10T12:00:00"


def test_detect_cpu機ではwhispercpp検証を行わない(monkeypatch):
    """CPU行はfaster-whisperなので、whisper-cliの有無は関係ない"""
    monkeypatch.setattr(
        "backend.core.device.probe_gpu",
        lambda: {"accel": "cpu", "name": "", "vram_total_mb": 0, "vram_free_mb": 0},
    )

    def never(cmd, timeout):
        raise AssertionError("cpu機で検証を呼ばない")

    profile = detect(now="t", runner=never, os_name="Linux")
    assert profile.gpu == "cpu"
    assert profile.whispercpp_ok is False


def test_detect_probe例外でもcpuプロファイルに落ちる(monkeypatch):
    """検出失敗で起動を止めない。cpu行は全OSで必ず動く終端"""
    def boom():
        raise RuntimeError("probe失敗")

    monkeypatch.setattr("backend.core.device.probe_gpu", boom)
    profile = detect(now="t", os_name="Windows")
    assert (profile.os, profile.gpu) == ("windows", "cpu")


# ---- JSONシリアライズ(app_settingsへの保存形) ----
def test_profile_roundtrip():
    p = _profile()
    assert HwProfile.from_dict(p.to_dict()) == p


def test_from_dict_未知キーは無視し欠損は既定値():
    """将来フィールドを足した後、旧DBのJSONでも読めること"""
    p = HwProfile.from_dict({"os": "linux", "gpu": "radeon", "unknown_field": 1})
    assert p.os == "linux"
    assert p.gpu == "radeon"
    assert p.whispercpp_ok is False
