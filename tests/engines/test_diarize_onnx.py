"""M23: ONNX話者分離エンジンのテスト(モデル・GPU不要)"""

from pathlib import Path

import numpy as np
import pytest

from backend.engines.diarize.onnx import (
    DEFAULT_EMBEDDING,
    DEFAULT_SEGMENTATION,
    is_available,
    to_turns,
)


class FakeSegment:
    def __init__(self, start, end, speaker):
        self.start, self.end, self.speaker = start, end, speaker


def test_to_turns_maps_speaker_ids_to_labels():
    """pyannoteと同じ (開始, 終了, ラベル) の形にそろえる"""
    turns = to_turns([FakeSegment(0.0, 1.5, 0), FakeSegment(1.5, 3.0, 1)])
    assert turns == [(0.0, 1.5, "SPEAKER_00"), (1.5, 3.0, "SPEAKER_01")]


def test_to_turns_sorts_by_start():
    turns = to_turns([FakeSegment(5.0, 6.0, 1), FakeSegment(0.0, 1.0, 0)])
    assert [t[0] for t in turns] == [0.0, 5.0]


def test_to_turns_pads_speaker_number():
    """話者が10人以上でもラベルの桁がそろう(表示の並びが崩れない)"""
    assert to_turns([FakeSegment(0, 1, 12)])[0][2] == "SPEAKER_12"


def test_to_turns_empty():
    assert to_turns([]) == []


def test_is_available_requires_both_models(tmp_path):
    seg, emb = tmp_path / "seg.onnx", tmp_path / "emb.onnx"
    assert is_available(seg, emb) is False
    seg.write_bytes(b"x")
    assert is_available(seg, emb) is False
    emb.write_bytes(b"x")
    assert is_available(seg, emb) is True


def test_default_paths_are_outside_the_repo():
    """モデルはリポジトリに置かない(配布物を汚さない)"""
    repo = Path(__file__).resolve().parents[2]
    for p in (DEFAULT_SEGMENTATION, DEFAULT_EMBEDDING):
        assert p.is_absolute()
        assert repo not in p.parents


def test_run_diarization_uses_injected_backend(monkeypatch, tmp_path):
    """sherpa-onnxを差し替えて、設定と戻り値の変換だけを確かめる"""
    from backend.engines.diarize import onnx as mod

    seg, emb = tmp_path / "seg.onnx", tmp_path / "emb.onnx"
    seg.write_bytes(b"x")
    emb.write_bytes(b"x")
    captured = {}

    class FakeResult:
        def sort_by_start_time(self):
            return [FakeSegment(0.0, 2.0, 0), FakeSegment(2.0, 4.0, 1)]

    class FakeDiarizer:
        def __init__(self, cfg):
            captured["cfg"] = cfg

        def process(self, audio, callback=None):
            captured["samples"] = len(audio)
            captured["callback"] = callback
            return FakeResult()

    monkeypatch.setattr(mod, "_build_diarizer", lambda **kw: FakeDiarizer(kw))
    turns = mod.run_diarization(
        np.zeros(16000, dtype=np.float32), num_speakers=2, segmentation=seg, embedding=emb
    )
    assert turns == [(0.0, 2.0, "SPEAKER_00"), (2.0, 4.0, "SPEAKER_01")]
    assert captured["cfg"]["num_speakers"] == 2
    assert captured["samples"] == 16000
    assert callable(captured["callback"])  # 進捗コールバックが配線されている


def test_run_diarization_without_models_raises(monkeypatch, tmp_path):
    from backend.engines.diarize import onnx as mod

    monkeypatch.setattr(mod, "DEFAULT_SEGMENTATION", tmp_path / "none.onnx")
    with pytest.raises(RuntimeError, match="話者分離モデル"):
        mod.run_diarization(np.zeros(16000, dtype=np.float32))
