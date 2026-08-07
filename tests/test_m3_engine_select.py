"""M3: ASRエンジン選択機構のテスト"""

import pytest
from fastapi.testclient import TestClient

from backend.core.config import Settings
from backend.engines.asr.registry import DEFAULT_MODEL, MODELS, build_engine


@pytest.fixture
def client(tmp_path, monkeypatch):
    from backend.core import config

    monkeypatch.setattr(config.settings, "db_path", tmp_path / "m3.db")
    from backend.app import app

    with TestClient(app) as c:
        yield c


def test_default_model_is_large_v3():
    # 精度優先・単語タイムスタンプ必須の要件による決定(BACKEND_DESIGN.md)
    assert DEFAULT_MODEL == "large-v3"
    assert Settings(_env_file=None).asr_model == "large-v3"


def test_all_registered_models_have_word_timestamps():
    # 単語TSが取れないモデルは要件を満たさないため登録しない
    assert all(m.word_timestamps for m in MODELS.values())


def test_build_engine_uses_configured_model():
    s = Settings(_env_file=None)
    s.asr_model = "large-v3-turbo"
    engine = build_engine(s)
    assert engine.model_size == "large-v3-turbo"
    assert engine.compute_type == "float16"  # Blackwellでint8はクラッシュする


def test_build_engine_rejects_unknown_model():
    s = Settings(_env_file=None)
    s.asr_model = "whisper-tiny-fake"
    with pytest.raises(ValueError, match="未知のASRモデル"):
        build_engine(s)


def test_engine_unload_is_safe_without_load():
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
    client.patch("/api/settings", json={"asr_model": "large-v3"})  # 後片付け


def test_settings_api_rejects_unknown_model(client):
    assert client.patch("/api/settings", json={"asr_model": "nope"}).status_code == 400


def test_settings_api_rejects_unknown_field(client):
    # db_path などUIから変えられては困る項目は拒否される
    assert client.patch("/api/settings", json={"db_path": "/tmp/x.db"}).status_code == 422
