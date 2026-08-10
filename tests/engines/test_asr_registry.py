"""M3: ASRエンジン選択機構のテスト"""

import pytest
from fastapi.testclient import TestClient

from backend.core.config import Settings
from backend.engines.asr.fasterwhisper import FasterWhisperEngine
from backend.engines.asr.registry import DEFAULT_MODEL, ENGINES, MODELS, build_engine
from backend.engines.asr.openai_whisper import OpenAIWhisperEngine


@pytest.fixture(autouse=True)
def cuda_runtime_ok(monkeypatch):
    """既定はCUDAランタイムあり(開発機の実環境に左右されない)。
    欠落時の挙動は個別テストで上書きする"""
    from backend.engines.asr import registry

    monkeypatch.setattr(registry, "missing_cuda_libs", lambda: [])


def test_default_model_is_large_v3():
    # 精度優先・単語タイムスタンプ必須の要件による決定(BACKEND_DESIGN.md)
    assert DEFAULT_MODEL == "large-v3"
    assert Settings(_env_file=None).asr_model == "large-v3"


def test_all_registered_models_have_word_timestamps():
    # 単語TSが取れないモデルは要件を満たさないため登録しない
    assert all(m.word_timestamps for m in MODELS.values())


def test_build_engine_uses_configured_model(monkeypatch):
    from backend.engines.asr import registry

    monkeypatch.setattr(registry, "detect_accel", lambda: "cuda")
    s = Settings(_env_file=None)
    s.asr_model = "large-v3-turbo"
    engine = build_engine(s)
    assert engine.model_size == "large-v3-turbo"
    assert engine.compute_type == "float16"  # Blackwellでint8はクラッシュする


@pytest.mark.parametrize(
    "accel, expected_type, expected_device, expected_compute",
    [
        # CUDA: faster-whisper float16(従来どおり)
        ("cuda", FasterWhisperEngine, "cuda", "float16"),
        # ROCm: CTranslate2非対応のため公式Whisper(HIPはcudaを名乗る)
        ("rocm", OpenAIWhisperEngine, "cuda", None),
        # GPUなし: faster-whisperのCPU int8(int8クラッシュはBlackwell GPU限定)
        ("cpu", FasterWhisperEngine, "cpu", "int8"),
    ],
)
def test_build_engine_auto_selects_by_accel(
    monkeypatch, accel, expected_type, expected_device, expected_compute
):
    from backend.engines.asr import registry

    monkeypatch.setattr(registry, "detect_accel", lambda: accel)
    # whisper.cppは外部ビルドなので、無い環境の挙動として固定する
    monkeypatch.setattr(registry, "whispercpp_available", lambda: False)
    # 公式Whisperはtorch依存。開発機に入っているかで結果が変わらないよう固定する
    monkeypatch.setattr(registry, "openai_whisper_available", lambda: True)
    engine = build_engine(Settings(_env_file=None))  # asr_engine="auto"
    assert isinstance(engine, expected_type)
    assert engine.device == expected_device
    if expected_compute is not None:
        assert engine.compute_type == expected_compute


def test_build_engine_prefers_whispercpp_on_rocm_when_built(monkeypatch):
    """whisper.cppが用意されていればROCmではそれを使う(公式版の約2.6倍速)"""
    from backend.engines.asr import registry
    from backend.engines.asr.whispercpp import WhisperCppEngine

    monkeypatch.setattr(registry, "detect_accel", lambda: "rocm")
    monkeypatch.setattr(registry, "whispercpp_available", lambda: True)
    assert isinstance(build_engine(Settings(_env_file=None)), WhisperCppEngine)


def test_build_engine_falls_back_when_whispercpp_missing(monkeypatch):
    """ビルドしていない環境では公式Whisperに落ちる(壊れない)"""
    from backend.engines.asr import registry

    monkeypatch.setattr(registry, "detect_accel", lambda: "rocm")
    monkeypatch.setattr(registry, "whispercpp_available", lambda: False)
    monkeypatch.setattr(registry, "openai_whisper_available", lambda: True)
    assert isinstance(build_engine(Settings(_env_file=None)), OpenAIWhisperEngine)


def test_build_engine_falls_back_to_faster_whisper_without_torch(monkeypatch):
    """配布物にtorchは無い。公式Whisperへ落とすとImportErrorで必ず失敗する。

    faster-whisperのGPU版はCUDA専用なのでROCmではCPUになるが、
    「遅い」と「動かない」なら遅いほうがよい。
    """
    from backend.engines.asr import registry

    monkeypatch.setattr(registry, "detect_accel", lambda: "rocm")
    monkeypatch.setattr(registry, "whispercpp_available", lambda: False)
    monkeypatch.setattr(registry, "openai_whisper_available", lambda: False)
    assert isinstance(build_engine(Settings(_env_file=None)), FasterWhisperEngine)


# ---- CUDAランタイム欠落時のフォールバック ----
# nvidia-smiが通る(ドライバはある)のにCUDAランタイムが無い機体があり、
# faster-whisperのモデル読み込みが「Library libcublas.so.12 is not found」で
# 必ず落ちる(配布版Ubuntuで実例)。クラッシュではなくGPUなしの規則で動かす。


@pytest.fixture
def cuda_without_runtime(monkeypatch):
    from backend.core import device
    from backend.engines.asr import registry

    monkeypatch.setattr(registry, "detect_accel", lambda: "cuda")
    monkeypatch.setattr(registry, "missing_cuda_libs", lambda: ["libcublas.so.12"])
    # GPU自体は積んでいる(nvidia-smiで名前が取れる)機体を想定
    monkeypatch.setattr(
        device, "probe_gpu",
        lambda: {"accel": "cuda", "name": "NVIDIA GeForce RTX 4070",
                 "vram_total_mb": 12282, "vram_free_mb": 11000},
    )


def test_CUDAランタイムが無ければwhispercppに落ちる(monkeypatch, cuda_without_runtime):
    """VulkanビルドのwhisperがあればGPUのまま動かせる"""
    from backend.engines.asr import registry
    from backend.engines.asr.whispercpp import WhisperCppEngine

    monkeypatch.setattr(registry, "whispercpp_available", lambda: True)
    assert isinstance(build_engine(Settings(_env_file=None)), WhisperCppEngine)


def test_CUDAランタイムもwhispercppも無ければCPUで動かす(monkeypatch, cuda_without_runtime):
    """「遅い」と「動かない」なら遅いほうがよい"""
    from backend.engines.asr import registry

    monkeypatch.setattr(registry, "whispercpp_available", lambda: False)
    engine = build_engine(Settings(_env_file=None))
    assert isinstance(engine, FasterWhisperEngine)
    assert engine.device == "cpu"
    assert engine.compute_type == "int8"


def test_CUDAランタイム欠落時は明示指定のfaster_whisperもCPUにする(monkeypatch, cuda_without_runtime):
    """auto以外を選んでいても、無いライブラリでのGPU実行は必ず失敗するので避ける"""
    s = Settings(_env_file=None)
    s.asr_engine = "faster_whisper"
    engine = build_engine(s)
    assert engine.device == "cpu"


def test_transformersエンジンはもう選べない():
    """M41で削除した。単語確率とinitial_promptが取れず、torch依存で
    配布物にも入らないため、選択肢として残す理由が無くなった"""
    from backend.engines.asr.registry import ENGINES

    assert "transformers" not in ENGINES
    s = Settings(_env_file=None)
    s.asr_engine = "transformers"
    with pytest.raises(ValueError, match="未知のASRエンジン"):
        build_engine(s)


def test_build_engine_rejects_unknown_model():
    s = Settings(_env_file=None)
    s.asr_model = "whisper-tiny-fake"
    with pytest.raises(ValueError, match="未知のASRモデル"):
        build_engine(s)


def test_build_engine_rejects_unknown_engine():
    s = Settings(_env_file=None)
    s.asr_engine = "whisperx"
    with pytest.raises(ValueError, match="未知のASRエンジン"):
        build_engine(s)


def test_settings_api_lists_engines(client):
    body = client.get("/api/settings").json()
    assert {e["id"] for e in body["asr_engines"]} == set(ENGINES)
    assert body["values"]["asr_engine"] == "auto"


def test_engine_unload_is_safe_without_load(monkeypatch):
    from backend.engines.asr import registry

    monkeypatch.setattr(registry, "detect_accel", lambda: "cuda")
    engine = build_engine(Settings(_env_file=None))
    engine.unload()  # ロード前でも例外にならない
    assert engine._model is None


def test_settings_api_returns_models_with_notes(client):
    body = client.get("/api/settings").json()
    ids = {m["id"] for m in body["asr_models"]}
    assert ids == set(MODELS)
    turbo = next(m for m in body["asr_models"] if m["id"] == "large-v3-turbo")
    assert "標準語化" in turbo["note"]  # UI表示用の注意書き
    assert body["values"]["asr_model"] == "large-v3"


def test_settings_api_updates_value(client):
    r = client.patch("/api/settings", json={"asr_model": "large-v3-turbo"})
    assert r.status_code == 200
    assert r.json()["values"]["asr_model"] == "large-v3-turbo"


def test_settings_api_rejects_unknown_model(client):
    assert client.patch("/api/settings", json={"asr_model": "nope"}).status_code == 400


def test_settings_api_rejects_unknown_field(client):
    # db_path などUIから変えられては困る項目は拒否される
    assert client.patch("/api/settings", json={"db_path": "/tmp/x.db"}).status_code == 422
