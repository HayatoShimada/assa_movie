"""M10: Word列をセグメント(字幕1枚)に区切る規則。

もとは transformers 版Whisperのテストだった。エンジンは削除したが、区切りの
規則は whisper.cpp と公式Whisperが今も使っている(backend/engines/asr/segmenting.py)。
「どこで切ると字幕として読めるか」の判断なので、ケースは減らさない。
"""

from backend.engines.asr.base import Word
from backend.engines.asr.segmenting import words_to_segments


def W(text, start, end):
    return Word(start=start, end=end, text=text)


def test_ポーズで区切る():
    """0.8秒以上の無音は話の切れ目"""
    words = [W("こんにちは", 0.0, 0.5), W("世界", 2.0, 2.5)]
    segs = words_to_segments(words)
    assert [s.text for s in segs] == ["こんにちは", "世界"]


def test_ポーズが短ければ区切らない():
    words = [W("こんにちは", 0.0, 0.5), W("世界", 0.7, 1.0)]
    assert len(words_to_segments(words)) == 1


def test_文末記号で区切る():
    """意味の切れ目。全角・半角どちらも"""
    for mark in ("。", "?", "!", "?", "!"):
        words = [W(f"はい{mark}", 0.0, 0.5), W("いいえ", 0.6, 1.0)]
        segs = words_to_segments(words)
        assert len(segs) == 2, mark


def test_長くなりすぎたら切る():
    """句読点もポーズも無いまま続くと、字幕1枚に収まらない"""
    words = [W("あ" * 5, i * 0.5, i * 0.5 + 0.4) for i in range(20)]
    segs = words_to_segments(words)
    assert len(segs) > 1
    assert all(len(s.text) <= 35 for s in segs)


def test_秒数でも切る():
    """文字数が少なくても、長すぎる字幕は読みづらい"""
    words = [W("ー", i * 0.5, i * 0.5 + 0.4) for i in range(30)]
    segs = words_to_segments(words)
    assert all(s.end - s.start <= 10 for s in segs)


def test_セグメントは元のWordを保持する():
    """フィラー判定・字幕の折り返しが単語タイムスタンプを使う"""
    words = [W("こんにちは", 0.0, 0.5), W("世界。", 0.6, 1.0)]
    seg = words_to_segments(words)[0]
    assert [w.text for w in seg.words] == ["こんにちは", "世界。"]
    assert seg.start == 0.0 and seg.end == 1.0


def test_空なら空():
    assert words_to_segments([]) == []
