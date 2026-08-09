"""M23: 話者分離エンジンの選択。

エンジンはONNXだけになった(M41でpyannoteを削除)。配布物にtorchを入れて
いないため、pyannoteはインストール版では一度も動かず「選べるのに選ぶと落ちる」
選択肢だった。実測でもONNXの方が4倍速く、一致率94.8%でトークンも要らない。
"""

import numpy as np
import pytest

from backend.core.config import Settings
from backend.engines.diarize import registry


@pytest.fixture
def no_models(monkeypatch):
    """ONNXモデルが未取得の状態にする"""
    monkeypatch.setattr(registry.onnx, "is_available", lambda: False)


@pytest.fixture
def with_models(monkeypatch):
    monkeypatch.setattr(registry.onnx, "is_available", lambda: True)


def test_autoはONNXを選ぶ(with_models):
    assert registry.resolve_engine("auto") == "onnx"


def test_モデルが無ければNone(no_models):
    """話者分離なしで文字起こしを続ける(必須ではない)"""
    assert registry.resolve_engine("auto") is None
    assert registry.resolve_engine("onnx") is None


def test_pyannoteはもう選べない():
    """設定に残っていても弾く。動かないものを受け付けない"""
    assert "pyannote" not in registry.ENGINES
    with pytest.raises(ValueError, match="未知の話者分離エンジン"):
        registry.run_diarization(np.zeros(16), Settings(diarization_engine="pyannote"))


def test_ONNXへ渡す人数は設定から取る(monkeypatch, with_models):
    calls = {}

    def fake(audio, num_speakers):
        calls["n"] = num_speakers
        return [(0.0, 1.0, "SPEAKER_00")]

    monkeypatch.setattr(registry.onnx, "run_diarization", fake)
    turns, engine = registry.run_diarization(np.zeros(16), Settings(num_speakers=3))
    assert engine == "onnx"
    assert turns == [(0.0, 1.0, "SPEAKER_00")]
    assert calls["n"] == 3


def test_使えるものが無ければ空を返す(no_models):
    assert registry.run_diarization(np.zeros(16), Settings()) == ([], None)


def test_未知のエンジンは弾く():
    with pytest.raises(ValueError, match="未知の話者分離エンジン"):
        registry.run_diarization(np.zeros(16), Settings(diarization_engine="whisper"))
