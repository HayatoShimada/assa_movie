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


def test_モデルがあれば使える(with_models):
    assert registry.available() is True


def test_モデルが無ければ使えない(no_models):
    """話者分離なしで文字起こしを続ける(必須ではない)"""
    assert registry.available() is False


def test_ONNXへ渡す人数は設定から取る(monkeypatch, with_models):
    calls = {}

    def fake(audio, num_speakers, progress=None):
        calls["n"] = num_speakers
        return [(0.0, 1.0, "SPEAKER_00")]

    monkeypatch.setattr(registry.onnx, "run_diarization", fake)
    turns, engine = registry.run_diarization(np.zeros(16), Settings(num_speakers=3))
    assert engine == "onnx"
    assert turns == [(0.0, 1.0, "SPEAKER_00")]
    assert calls["n"] == 3


def test_使えるものが無ければ空を返す(no_models):
    assert registry.run_diarization(np.zeros(16), Settings()) == ([], None)


def test_進捗コールバックをONNXへ渡す(monkeypatch, with_models):
    """話者分離は長尺で数分かかる。進捗が出ないと止まって見える"""
    def fake(audio, num_speakers, progress=None):
        progress(0.5)
        return []

    monkeypatch.setattr(registry.onnx, "run_diarization", fake)
    seen: list[float] = []
    registry.run_diarization(np.zeros(16), Settings(), progress=seen.append)
    assert seen == [0.5]


def test_sherpaの進捗コールバック変換():
    """sherpa-onnxの (処理済みチャンク, 総数)->int を 0..1 の進捗に直す(純関数)"""
    from backend.engines.diarize import onnx

    seen: list[float] = []
    cb = onnx.sherpa_progress(seen.append)
    assert cb(5, 10) == 0  # 0以外を返すと処理が中断される
    assert cb(10, 10) == 0
    assert seen == [0.5, 1.0]
    assert onnx.sherpa_progress(None)(1, 2) == 0  # コールバック無しでも安全
    assert onnx.sherpa_progress(seen.append)(1, 0) == 0  # 総数0でも割らない


def test_エンジン選択の設定はもう無い():
    """実装はONNXの1つだけ。選べない設定をUIにも設定にも置かない"""
    assert not hasattr(Settings(), "diarization_engine")
    assert not hasattr(registry, "ENGINES")
