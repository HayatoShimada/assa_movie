"""ASRエンジンの組み立て(プロファイル固定方式)のテスト。

設計(DESIGN.md 2026-08-10): エンジンは実行時に検出しない。確定済みの
ハードウェアプロファイル → 静的対応表(hwprofile.resolve_spec)で決まり、
構成が壊れていたらフォールバックせず直し方を含むエラーで止める。
"""

import pytest

from backend.core import hwprofile
from backend.core.config import Settings
from backend.core.hwprofile import HwProfile
from backend.engines.asr.fasterwhisper import FasterWhisperEngine
from backend.engines.asr.registry import DEFAULT_MODEL, MODELS, build_engine
from backend.engines.asr.whispercpp import WhisperCppEngine


GPU = HwProfile(os="linux", gpu="nvidia", gpu_name="GPU", vram_total_mb=8000,
                whispercpp_ok=True, detected_at="t")
CPU = HwProfile(os="linux", gpu="cpu", detected_at="t")


@pytest.fixture(autouse=True)
def reset_profile():
    """テストごとにプロファイルの現在値を明示設定させる(実機に依存させない)"""
    hwprofile.set_current(CPU)
    yield
    hwprofile.set_current(None)


@pytest.fixture
def whispercpp_ready(monkeypatch, tmp_path):
    """whisper.cppのバイナリとモデルが揃った状態"""
    from backend.engines.asr import whispercpp

    binary = tmp_path / "whisper-cli"
    binary.write_bytes(b"")
    binary.chmod(0o755)
    model = tmp_path / "ggml-large-v3.bin"
    model.write_bytes(b"")
    monkeypatch.setattr(whispercpp, "resolve_binary", lambda: binary)
    monkeypatch.setattr(whispercpp, "resolve_model", lambda: model)
    return tmp_path


def test_default_model_is_large_v3():
    # 精度優先・単語タイムスタンプ必須の要件による決定(BACKEND_DESIGN.md)
    assert DEFAULT_MODEL == "large-v3"
    assert Settings(_env_file=None).asr_model == "large-v3"


def test_all_registered_models_have_word_timestamps():
    # 単語TSが取れないモデルは要件を満たさないため登録しない
    assert all(m.word_timestamps for m in MODELS.values())


# ---- プロファイル → エンジンの写像 ----
def test_GPU機はwhispercpp(whispercpp_ready):
    hwprofile.set_current(GPU)
    engine = build_engine(Settings(_env_file=None))
    assert isinstance(engine, WhisperCppEngine)


def test_CPU機はfaster_whisperのCPU_int8():
    hwprofile.set_current(CPU)
    engine = build_engine(Settings(_env_file=None))
    assert isinstance(engine, FasterWhisperEngine)
    assert engine.device == "cpu"
    assert engine.compute_type == "int8"


def test_検証失敗のGPU機はcpu構成():
    """プロファイル確定時にcpu行へ落ちている(実行時フォールバックではない)"""
    hwprofile.set_current(
        HwProfile(os="windows", gpu="radeon", whispercpp_ok=False, detected_at="t")
    )
    engine = build_engine(Settings(_env_file=None))
    assert isinstance(engine, FasterWhisperEngine)
    assert engine.device == "cpu"


def test_モデルサイズ等の設定は従来どおり効く():
    hwprofile.set_current(CPU)
    s = Settings(_env_file=None)
    s.asr_model = "large-v3-turbo"
    s.asr_beam_size = 3
    engine = build_engine(s)
    assert engine.model_size == "large-v3-turbo"
    assert engine.beam_size == 3


# ---- 破損時はフォールバックせずエラーで案内する(ユーザー決定) ----
def test_whispercppのバイナリが無ければ案内付きエラー(monkeypatch):
    from backend.engines.asr import whispercpp

    hwprofile.set_current(GPU)
    monkeypatch.setattr(whispercpp, "resolve_binary", lambda: None)
    with pytest.raises(RuntimeError, match="再検出"):
        build_engine(Settings(_env_file=None))


def test_whispercppのモデルが無ければ案内付きエラー(monkeypatch, tmp_path):
    from backend.engines.asr import whispercpp

    hwprofile.set_current(GPU)
    binary = tmp_path / "whisper-cli"
    binary.write_bytes(b"")
    monkeypatch.setattr(whispercpp, "resolve_binary", lambda: binary)
    monkeypatch.setattr(whispercpp, "resolve_model", lambda: tmp_path / "no.bin")
    with pytest.raises(RuntimeError, match="セットアップ"):
        build_engine(Settings(_env_file=None))


# ---- KS_ASR_ENGINE(上級者向けの唯一の上書き手段) ----
def test_環境変数でwhispercppを強制できる(whispercpp_ready):
    hwprofile.set_current(CPU)
    s = Settings(_env_file=None)
    s.asr_engine = "whispercpp"
    assert isinstance(build_engine(s), WhisperCppEngine)


def test_環境変数でfaster_whisperを強制するとCPU実行(whispercpp_ready):
    """CUDA経路は廃止した。faster-whisperは常にCPU int8"""
    hwprofile.set_current(GPU)
    s = Settings(_env_file=None)
    s.asr_engine = "faster_whisper"
    engine = build_engine(s)
    assert isinstance(engine, FasterWhisperEngine)
    assert engine.device == "cpu"
    assert engine.compute_type == "int8"


# ---- バリデーション ----
def test_削除済みエンジンは選べない():
    """auto・openai_whisper・transformersはもう存在しない"""
    for engine_id in ("auto", "openai_whisper", "transformers", "whisperx"):
        s = Settings(_env_file=None)
        s.asr_engine = engine_id
        with pytest.raises(ValueError, match="未知のASRエンジン"):
            build_engine(s)


def test_build_engine_rejects_unknown_model():
    s = Settings(_env_file=None)
    s.asr_model = "whisper-tiny-fake"
    with pytest.raises(ValueError, match="未知のASRモデル"):
        build_engine(s)


def test_engine_unload_is_safe_without_load():
    engine = build_engine(Settings(_env_file=None))
    engine.unload()  # ロード前でも例外にならない
    assert engine._model is None


# ---- 設定API(エンジン選択の撤去) ----
def test_settings_api_にasr_enginesはもう無い(client):
    body = client.get("/api/settings").json()
    assert "asr_engines" not in body
    assert "asr_engine" not in body["values"]


def test_settings_api_はasr_engineの変更を受け付けない(client):
    assert client.patch("/api/settings", json={"asr_engine": "whispercpp"}).status_code == 422


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
