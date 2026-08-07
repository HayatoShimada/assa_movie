"""M10: transformers版Whisperエンジンのテスト(GPU・モデルDL不要)。

実pipelineの代わりにFakeを注入し、chunks→Word/Segment変換と
TranscribeResultの組み立てを検証する。
"""

import numpy as np
import pytest

from backend.engines.asr.base import Word
from backend.engines.asr.transformers_whisper import (
    TransformersWhisperEngine,
    chunks_to_words,
    full_language_name,
    words_to_segments,
)


# ---- chunks_to_words: transformersのword timestamp出力 → Word列 ----

def test_chunks_to_words_basic():
    chunks = [
        {"text": "こんにちは", "timestamp": (0.0, 0.5)},
        {"text": "世界", "timestamp": (0.6, 1.0)},
    ]
    words = chunks_to_words(chunks)
    assert [w.text for w in words] == ["こんにちは", "世界"]
    assert words[0].start == 0.0 and words[0].end == 0.5


def test_chunks_to_words_none_end_is_estimated():
    # 末尾チャンクはend=Noneになることがある(transformersの既知挙動)
    chunks = [{"text": "はい", "timestamp": (3.0, None)}]
    words = chunks_to_words(chunks)
    assert words[0].end > words[0].start


def test_chunks_to_words_skips_empty_text():
    chunks = [
        {"text": " ", "timestamp": (0.0, 0.1)},
        {"text": "話", "timestamp": (0.1, 0.3)},
    ]
    assert [w.text for w in chunks_to_words(chunks)] == ["話"]


# ---- words_to_segments: ポーズ・文末記号でのセグメント分割(テーブル駆動) ----

def _w(start, end, text):
    return Word(start=start, end=end, text=text)


@pytest.mark.parametrize(
    "name, words, expected_texts",
    [
        (
            "ポーズ0.8秒以上で分割",
            [_w(0.0, 0.5, "おはよう"), _w(1.5, 2.0, "ございます")],
            ["おはよう", "ございます"],
        ),
        (
            "ポーズが短ければ連結",
            [_w(0.0, 0.5, "おはよう"), _w(0.6, 1.0, "ございます")],
            ["おはようございます"],
        ),
        (
            "句点で分割",
            [_w(0.0, 0.5, "そうです。"), _w(0.6, 1.0, "次の話")],
            ["そうです。", "次の話"],
        ),
        (
            "疑問符・感嘆符でも分割",
            [_w(0.0, 0.5, "本当?"), _w(0.6, 1.0, "すごい!"), _w(1.1, 1.5, "ね")],
            ["本当?", "すごい!", "ね"],
        ),
        ("空入力", [], []),
    ],
)
def test_words_to_segments_table(name, words, expected_texts):
    segments = words_to_segments(words)
    assert [s.text for s in segments] == expected_texts, name


def test_words_to_segments_force_splits_long_speech():
    # 句読点もポーズも無い60秒の発話でも、字幕1枚に収まる単位に分割される
    words = [_w(i * 0.5, i * 0.5 + 0.4, "あい") for i in range(120)]
    segments = words_to_segments(words)
    assert len(segments) > 5
    assert all(s.end - s.start <= 8.5 for s in segments)
    assert all(len(s.text) <= 32 for s in segments)


def test_words_to_segments_keeps_word_timestamps():
    words = [_w(0.0, 0.5, "あの"), _w(0.6, 1.2, "それで")]
    segments = words_to_segments(words)
    assert len(segments) == 1
    seg = segments[0]
    assert seg.start == 0.0 and seg.end == 1.2
    assert seg.words is not None and len(seg.words) == 2  # 単語TSは必須要件


# ---- エンジン統合(Fake pipeline注入) ----

class FakeTokenizer:
    language = None


class FakePipe:
    def __init__(self, output):
        self.output = output
        self.calls = []
        self.tokenizer = FakeTokenizer()

    def __call__(self, audio, **kwargs):
        self.calls.append(kwargs)
        return self.output


# ---- 言語名の解決(単語分割が壊れた原因) ----

@pytest.mark.parametrize(
    "given, expected",
    [
        ("ja", "japanese"),   # ISOコードのままだと空白分割になり日本語が1単語になる
        ("JA", "japanese"),
        ("en", "english"),
        ("japanese", "japanese"),  # 既に名称ならそのまま
        ("xx", "xx"),         # 未知の値は触らない
        (None, None),
    ],
)
def test_full_language_name(given, expected):
    assert full_language_name(given) == expected


def test_transcribe_sets_tokenizer_language_to_full_name():
    """回帰: tokenizer.languageが"ja"のままだと日本語が分割されない"""
    fake = FakePipe({"text": "はい", "chunks": [{"text": "はい", "timestamp": (0.0, 0.5)}]})
    engine = TransformersWhisperEngine(pipeline_factory=lambda: fake)
    engine.transcribe(np.zeros(16000, dtype=np.float32), language="ja")
    assert fake.tokenizer.language == "japanese"


def test_engine_transcribe_with_fake_pipeline():
    fake = FakePipe(
        {
            "text": "こんにちは。元気です",
            "chunks": [
                {"text": "こんにちは。", "timestamp": (0.0, 1.0)},
                {"text": "元気です", "timestamp": (2.5, 3.5)},
            ],
        }
    )
    engine = TransformersWhisperEngine(pipeline_factory=lambda: fake)
    progressed = []
    result = engine.transcribe(
        np.zeros(16000 * 4, dtype=np.float32),
        language="ja",
        progress=progressed.append,
        initial_prompt="無視される",  # transformersでは未対応(ログのみ)
    )
    assert [s.text for s in result.segments] == ["こんにちは。", "元気です"]
    assert result.language == "ja"
    # 単語タイムスタンプ必須の要件
    assert all(s.words for s in result.segments)
    # 進捗は開始・完了の粗い通知のみ(pipelineにコールバックが無いため)
    assert progressed and progressed[-1] == 1.0
    # word単位のタイムスタンプを要求していること
    assert fake.calls[0]["return_timestamps"] == "word"


def test_engine_unload_is_safe_without_load():
    engine = TransformersWhisperEngine(pipeline_factory=lambda: FakePipe({}))
    engine.unload()  # ロード前でも例外にならない
