"""M3: ASRエンジン選択機構のテスト"""

import pytest
from fastapi.testclient import TestClient

from backend.core.config import Settings
from backend.engines.asr.fasterwhisper import FasterWhisperEngine
from backend.engines.asr.registry import DEFAULT_MODEL, ENGINES, MODELS, build_engine
from backend.engines.asr.openai_whisper import OpenAIWhisperEngine
from backend.engines.asr.transformers_whisper import TransformersWhisperEngine


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
    engine = build_engine(Settings(_env_file=None))  # asr_engine="auto"
    assert isinstance(engine, expected_type)
    assert engine.device == expected_device
    if expected_compute is not None:
        assert engine.compute_type == expected_compute


def test_build_engine_explicit_transformers_on_cpu(monkeypatch):
    from backend.engines.asr import registry

    monkeypatch.setattr(registry, "detect_accel", lambda: "cpu")
    s = Settings(_env_file=None)
    s.asr_engine = "transformers"
    engine = build_engine(s)
    assert isinstance(engine, TransformersWhisperEngine)
    assert engine.device == "cpu"
    assert engine.model_id == "openai/whisper-large-v3"


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
