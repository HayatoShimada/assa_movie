"""M1: 移植したパイプラインのユニットテスト"""

import numpy as np
import pytest

from backend.engines.asr.base import Segment, Word
from backend.engines.diarize.pyannote import assign_speaker, build_label_map, load_hf_token
from backend.pipeline import audio as audio_io
from backend.pipeline.aizuchi import is_aizuchi
from backend.pipeline.subtitle import format_timestamp, srt_block

GOLDEN_WAV = "tests/golden/smoke.wav"


# ---- 相槌判定(移植前の11ケースをそのまま) ----
@pytest.mark.parametrize(
    "text,duration,expected",
    [
        ("うん", 0.5, True),
        ("うんうん", 0.8, True),
        ("なるほどなるほど", 1.2, True),
        ("はい、はい。", 1.0, True),
        ("そうですね", 1.0, True),
        ("えー", 0.4, True),
        ("、。", 0.5, True),  # 記号だけ
        ("そうですね、AIと話してる方が楽だと思います", 3.5, False),
        ("うん、でもそれは違うと思う", 1.8, False),
        ("確かにそういう見方もありますね", 1.9, False),
        ("なるほど", 3.0, False),  # 長すぎるので残す
        ("人と関わらない", 1.0, False),
    ],
)
def test_is_aizuchi(text, duration, expected):
    assert is_aizuchi(text, duration) is expected


# ---- タイムスタンプ整形 ----
@pytest.mark.parametrize(
    "seconds,expected",
    [
        (0.0, "00:00:00,000"),
        (1.26, "00:00:01,260"),
        (61.5, "00:01:01,500"),
        (3661.001, "01:01:01,001"),
    ],
)
def test_format_timestamp(seconds, expected):
    assert format_timestamp(seconds) == expected


def test_srt_block_format():
    assert srt_block(1, 0.0, 1.26, "はやまる: テスト") == (
        "1\n00:00:00,000 --> 00:00:01,260\nはやまる: テスト\n\n"
    )


# ---- 音声デコード ----
def test_decode_audio_shape():
    audio = audio_io.decode(GOLDEN_WAV)
    assert audio.dtype == np.float32
    assert audio.ndim == 1
    assert 59 * 16000 <= len(audio) <= 61 * 16000  # 60秒クリップ


# ---- 話者割り当て ----
def test_assign_speaker_picks_max_overlap():
    turns = [(0.0, 5.0, "SPEAKER_00"), (5.0, 10.0, "SPEAKER_01")]
    seg = Segment(start=4.0, end=9.0, text="x", words=[Word(4.0, 4.5, "a"), Word(6.0, 9.0, "b")])
    assert assign_speaker(seg, turns) == "SPEAKER_01"  # 重なり 0.5 vs 3.0


def test_assign_speaker_without_words_uses_segment_span():
    turns = [(0.0, 5.0, "SPEAKER_00")]
    seg = Segment(start=1.0, end=2.0, text="x", words=None)
    assert assign_speaker(seg, turns) == "SPEAKER_00"


def test_assign_speaker_returns_none_when_no_overlap():
    turns = [(10.0, 20.0, "SPEAKER_00")]
    seg = Segment(start=1.0, end=2.0, text="x")
    assert assign_speaker(seg, turns) is None


# ---- 話者名の割り当て(ピッチ判定はモックで検証) ----
def _fake_pitch(monkeypatch, mapping):
    import backend.engines.diarize.pyannote as mod

    monkeypatch.setattr(mod, "estimate_pitch", lambda audio, turns, label: mapping[label])


def test_build_label_map_assigns_by_pitch(monkeypatch):
    turns = [(0.0, 1.0, "SPEAKER_00"), (1.0, 2.0, "SPEAKER_01")]
    _fake_pitch(monkeypatch, {"SPEAKER_00": 140.0, "SPEAKER_01": 105.0})
    m = build_label_map(np.zeros(10), turns, male_name="男", female_name="女", log=lambda *_: None)
    assert m == {"SPEAKER_01": "男", "SPEAKER_00": "女"}  # 低い方が男性


def test_build_label_map_warns_when_pitches_close(monkeypatch):
    turns = [(0.0, 1.0, "A"), (1.0, 2.0, "B")]
    _fake_pitch(monkeypatch, {"A": 120.0, "B": 135.0})
    logs = []
    build_label_map(np.zeros(10), turns, male_name="男", female_name="女", log=logs.append)
    assert any("⚠" in line for line in logs)


def test_build_label_map_falls_back_when_pitch_fails(monkeypatch):
    turns = [(0.0, 1.0, "A"), (1.0, 2.0, "B")]
    _fake_pitch(monkeypatch, {"A": None, "B": None})
    m = build_label_map(np.zeros(10), turns, male_name="男", female_name="女", log=lambda *_: None)
    assert m == {"A": "話者1", "B": "話者2"}


def test_build_label_map_explicit_names_win(monkeypatch):
    turns = [(0.0, 1.0, "A"), (1.0, 2.0, "B")]
    m = build_label_map(
        np.zeros(10), turns, male_name="男", female_name="女",
        speaker_names={"A": "しまだ"}, log=lambda *_: None,
    )
    assert m == {"A": "しまだ", "B": "B"}


# ---- HFトークン読み込み ----
def test_load_hf_token_from_env(monkeypatch, tmp_path):
    monkeypatch.setenv("HF_TOKEN", "hf_fromenv")
    assert load_hf_token(tmp_path / "none.txt") == "hf_fromenv"


def test_load_hf_token_from_file(monkeypatch, tmp_path):
    monkeypatch.delenv("HF_TOKEN", raising=False)
    f = tmp_path / "t.txt"
    f.write_text("hf_fromfile\n")
    assert load_hf_token(f) == "hf_fromfile"


def test_load_hf_token_rejects_placeholder(monkeypatch, tmp_path):
    monkeypatch.delenv("HF_TOKEN", raising=False)
    f = tmp_path / "t.txt"
    f.write_text("ここにトークンを貼り付けてください\n複数行の説明\n")
    assert load_hf_token(f) is None
