"""M18: 公式Whisper(openai-whisper)エンジンのテスト(GPU・モデルDL不要)"""

import numpy as np
import pytest

from backend.engines.asr.openai_whisper import OpenAIWhisperEngine, to_segments


# ---- to_segments: whisperの出力 → 共通のSegment/Word ----

RAW = [
    {
        "start": 0.0, "end": 2.0, "text": " こんにちは。", "avg_logprob": -0.21,
        "words": [
            {"word": "こんにち", "start": 0.0, "end": 1.2, "probability": 0.98},
            {"word": "は。", "start": 1.2, "end": 2.0, "probability": 0.42},
        ],
    },
    {"start": 2.5, "end": 3.5, "text": "元気です", "words": []},
]


def test_to_segments_maps_words_and_probability():
    segs = to_segments(RAW)
    assert [s.text for s in segs] == ["こんにちは。", "元気です"]
    assert segs[0].confidence == pytest.approx(-0.21)
    words = segs[0].words
    assert words is not None and len(words) == 2
    # 単語確率はフィラー判定のシグナルなので必ず引き継ぐ(transformers版では取れない)
    assert words[0].probability == pytest.approx(0.98)
    assert words[1].probability == pytest.approx(0.42)
    assert words[0].start == 0.0 and words[0].end == 1.2


def test_to_segments_without_words_is_none():
    assert to_segments(RAW)[1].words is None


def test_to_segments_skips_words_without_timestamps():
    raw = [{"start": 0, "end": 1, "text": "あ", "words": [
        {"word": "あ", "start": None, "end": None, "probability": 0.9},
        {"word": "い", "start": 0.5, "end": 1.0, "probability": 0.9},
    ]}]
    assert [w.text for w in to_segments(raw)[0].words] == ["い"]


def test_to_segments_empty():
    assert to_segments([]) == []


# ---- エンジン統合(Fakeモデル注入) ----

class FakeModel:
    def __init__(self):
        self.calls = []

    def transcribe(self, audio, **kwargs):
        self.calls.append(kwargs)
        return {"language": "ja", "segments": RAW}


def test_transcribe_requests_word_timestamps_and_prompt():
    fake = FakeModel()
    engine = OpenAIWhisperEngine(model_factory=lambda: fake)
    progressed = []
    result = engine.transcribe(
        np.zeros(16000 * 4, dtype=np.float32),
        language="ja",
        progress=progressed.append,
        initial_prompt="えーと、あのー。",
    )
    kwargs = fake.calls[0]
    assert kwargs["word_timestamps"] is True
    # transformers版と違いinitial_promptを渡せる(言い淀みの忠実転写に必要)
    assert kwargs["initial_prompt"] == "えーと、あのー。"
    assert kwargs["language"] == "ja"
    assert result.language == "ja"
    assert len(result.segments) == 2
    assert progressed and progressed[-1] == 1.0


def test_cpu_disables_fp16():
    fake = FakeModel()
    engine = OpenAIWhisperEngine(device="cpu", model_factory=lambda: fake)
    engine.transcribe(np.zeros(16000, dtype=np.float32))
    assert fake.calls[0]["fp16"] is False


def test_unload_is_safe_without_load():
    OpenAIWhisperEngine(model_factory=lambda: FakeModel()).unload()
