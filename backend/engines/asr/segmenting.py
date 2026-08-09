"""Word列をセグメント(字幕1枚ぶん)に区切る。純関数。

エンジンに依存しない。もとは transformers_whisper.py にあったが、
**配布物に入る whisper.cpp エンジンが、配布物に入らない transformers 版の
モジュールを import している**状態だった。中立な場所へ移す。

区切りの基準は3つ。どれも「字幕として読めるか」で決めている。
  - ポーズ(0.8秒以上): 話の切れ目
  - 文末記号: 意味の切れ目
  - 長さ(8秒 / 30文字): どちらも無いまま続くとき、1枚に収まる単位で切る
"""

from backend.engines.asr.base import Segment, Word

# この秒数以上の無音を挟んだらセグメントを分ける(字幕の切れ目として自然な値)
PAUSE_SPLIT_SEC = 0.8
# セグメント末尾として扱う文末記号(全角・半角)
SENTENCE_END = ("。", "?", "!", "?", "!")
# 句読点もポーズも無い発話が続く場合の強制分割(字幕1枚に収まる長さ)
MAX_SEGMENT_SEC = 8.0
MAX_SEGMENT_CHARS = 30


def words_to_segments(words: list[Word]) -> list[Segment]:
    """Word列をポーズ・文末記号でセグメントに区切る(純関数)"""
    segments: list[Segment] = []
    current: list[Word] = []

    def flush():
        if current:
            segments.append(
                Segment(
                    start=current[0].start,
                    end=current[-1].end,
                    text="".join(w.text for w in current),
                    words=list(current),
                )
            )
            current.clear()

    for w in words:
        if current and w.start - current[-1].end >= PAUSE_SPLIT_SEC:
            flush()
        # 句読点もポーズも無いまま長くなったら、字幕1枚に収まる単位で切る
        if current and (
            w.end - current[0].start > MAX_SEGMENT_SEC
            or sum(len(x.text) for x in current) + len(w.text) > MAX_SEGMENT_CHARS
        ):
            flush()
        current.append(w)
        if w.text.endswith(SENTENCE_END):
            flush()
    flush()
    return segments
