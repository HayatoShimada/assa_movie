"""M23: 話者分離エンジンの選択(モデル・torch・HFトークン不要)"""

import numpy as np
import pytest

from backend.core.config import Settings
from backend.engines.diarize import registry


@pytest.fixture(autouse=True)
def torch_installed(monkeypatch):
    """pyannoteが動く環境(=torchが入っている)を前提にする。

    ここで固定しないと、torchの有無というテスト環境の都合で結果が変わる。
    配布版のようにtorchが無い場合の挙動は test_m35_bundled_models.py で見る。
    """
    monkeypatch.setattr(registry.pyannote, "is_available", lambda: True)


@pytest.fixture
def no_models(monkeypatch):
    """ONNXモデルが未取得の状態にする"""
    monkeypatch.setattr(registry.onnx, "is_available", lambda: False)


@pytest.fixture
def with_models(monkeypatch):
    monkeypatch.setattr(registry.onnx, "is_available", lambda: True)


def test_auto_prefers_onnx(with_models):
    """モデルがあればトークンの有無によらずONNX(速く・軽い)"""
    assert registry.resolve_engine("auto", has_token=False) == "onnx"
    assert registry.resolve_engine("auto", has_token=True) == "onnx"


def test_auto_falls_back_to_pyannote_when_token_exists(no_models):
    assert registry.resolve_engine("auto", has_token=True) == "pyannote"


def test_auto_returns_none_without_models_and_token(no_models):
    """どちらも使えないときはNone(話者分離なしで文字起こしを続ける)"""
    assert registry.resolve_engine("auto", has_token=False) is None


def test_explicit_onnx_does_not_fall_back(no_models):
    """明示指定したエンジンが使えないなら黙って別物にしない"""
    assert registry.resolve_engine("onnx", has_token=True) is None


def test_explicit_pyannote_needs_token(with_models):
    assert registry.resolve_engine("pyannote", has_token=False) is None
    assert registry.resolve_engine("pyannote", has_token=True) == "pyannote"


def test_run_diarization_dispatches_to_onnx(monkeypatch, with_models):
    calls = {}

    def fake(audio, num_speakers):
        calls["n"] = num_speakers
        return [(0.0, 1.0, "SPEAKER_00")]

    monkeypatch.setattr(registry.onnx, "run_diarization", fake)
    turns, engine = registry.run_diarization(np.zeros(16), Settings(num_speakers=3))
    assert engine == "onnx"
    assert turns == [(0.0, 1.0, "SPEAKER_00")]
    assert calls["n"] == 3


def test_run_diarization_returns_empty_when_unavailable(no_models):
    turns, engine = registry.run_diarization(np.zeros(16), Settings(), token=None)
    assert (turns, engine) == ([], None)


def test_run_diarization_rejects_unknown_engine():
    with pytest.raises(ValueError, match="未知の話者分離エンジン"):
        registry.run_diarization(np.zeros(16), Settings(diarization_engine="whisper"))
