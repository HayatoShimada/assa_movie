"""M7-1/7-2: 折返し・禁則処理・ASS生成のテスト(テーブル駆動)"""

import pytest

from backend.pipeline.subtitle import (
    AssEvent,
    SubtitleStyle,
    build_ass,
    format_ass_time,
    min_display_duration,
    segments_to_events,
    wrap_subtitle,
)


# ---- 折返し・禁則(25ケース以上) ----
@pytest.mark.parametrize(
    "text,max_chars,expected",
    [
        # 基本の折返し
        ("あいうえおかきくけこ", 5, ["あいうえお", "かきくけこ"]),
        ("あいうえお", 5, ["あいうえお"]),
        ("あいうえお", 10, ["あいうえお"]),
        ("", 5, [""]),
        ("あ", 5, ["あ"]),
        # ちょうど割り切れる
        ("あいうえおかきくけこさしすせそ", 5, ["あいうえお", "かきくけこ", "さしすせそ"]),
        # 行頭禁則: 句読点は前の行にぶら下げる
        ("あいうえお、かきくけ", 5, ["あいうえお、", "かきくけ"]),
        ("あいうえお。かきくけ", 5, ["あいうえお。", "かきくけ"]),
        ("あいうえお!?かきく", 5, ["あいうえお!?", "かきく"]),
        # 行頭禁則: 小書き仮名
        ("ハッカソンってすごい", 4, ["ハッカソ", "ンってす", "ごい"]),
        ("あいうえょかきくけ", 5, ["あいうえょ", "かきくけ"]),
        # 行頭禁則: 長音
        ("コンピューターがすごい", 5, ["コンピュー", "ターがすご", "い"]),
        # 行頭禁則: 閉じ括弧
        ("それ(去年の話)です", 7, ["それ(去年の話)", "です"]),
        # 行末禁則: 開き括弧は次の行へ
        ("あいうえ「かきくけこ", 5, ["あいうえ", "「かきくけ", "こ"]),
        ("あいうえ(かきくけこ", 5, ["あいうえ", "(かきくけ", "こ"]),
        # ぶら下げ上限(2文字)を超える禁則の連続は、安全な切れ目まで追い出す
        ("あいうえお、。ーかきく", 5, ["あいうえ", "お、。ーか", "きく"]),
        # 複合: 括弧注釈付きの実例
        ("この人(高田さん)とは多分", 8, ["この人(高田さん)", "とは多分"]),
        ("それ(問い続けること)私あの", 10, ["それ(問い続けること)", "私あの"]),
        # 記号・数字混在
        ("50円で作れる洋服の話", 6, ["50円で作れ", "る洋服の話"]),
        ("AIと話す方が楽だ", 5, ["AIと話す", "方が楽だ"]),
        # 長文
        ("なんかそういうのがあってもいいのかなって思ったりするんですけど", 15,
         ["なんかそういうのがあってもいい", "のかなって思ったりするんですけ", "ど"]),
        # 読点が行末に来るケース
        ("あいうえ、おかきくけ", 5, ["あいうえ、", "おかきくけ"]),
        # max_charsが極端に小さい場合も壊れない
        ("あい、う", 2, ["あい、", "う"]),
        # 禁則文字だけの文字列
        ("、、、", 5, ["、、、"]),
        # スペース混じり
        ("はい そうです ね", 5, ["はい そう", "です ね"]),
    ],
)
def test_wrap_subtitle(text, max_chars, expected):
    assert wrap_subtitle(text, max_chars) == expected


def test_wrap_lines_respect_kinsoku_invariants():
    """どんな入力でも折返し結果が禁則を破っていないことを検査する"""
    import random

    random.seed(42)
    chars = "あいうえお、。ーっゃ「」()カタカナ漢字ABC123!?"
    for _ in range(50):
        text = "".join(random.choices(chars, k=random.randint(1, 60)))
        for line in wrap_subtitle(text, 8)[1:]:  # 2行目以降の行頭をチェック
            assert line == "" or line[0] not in "、。ーっゃ」)!?", f"行頭禁則違反: {line!r} ({text!r})"
        for line in wrap_subtitle(text, 8)[:-1]:  # 最終行以外の行末をチェック
            assert line == "" or line[-1] not in "「(", f"行末禁則違反: {line!r} ({text!r})"


# ---- 表示時間 ----
@pytest.mark.parametrize(
    "text,expected",
    [("あ", 1.0), ("あいうえおかき", 1.05), ("あ" * 20, 3.0)],
)
def test_min_display_duration(text, expected):
    assert min_display_duration(text) == pytest.approx(expected)


# ---- ASS ----
def test_format_ass_time():
    assert format_ass_time(0.0) == "0:00:00.00"
    assert format_ass_time(61.5) == "0:01:01.50"
    assert format_ass_time(3661.999) == "1:01:02.00"  # 繰り上がり


def test_build_ass_has_speaker_styles_and_events():
    events = [
        AssEvent(0.0, 2.0, "こんにちは", speaker="はやまる"),
        AssEvent(2.0, 4.0, "よろしくお願いします", speaker="高田さん"),
        AssEvent(4.0, 5.0, "ナレーション", speaker=None),
    ]
    ass = build_ass(events, SubtitleStyle(font_name="Noto Sans JP", max_chars_per_line=15))
    assert "PlayResX: 1920" in ass
    assert "Style: Default,Noto Sans JP" in ass
    assert ass.count("Style: S") == 2  # 話者2人分のスタイル
    assert "Dialogue: 0,0:00:00.00,0:00:02.00,S0,はやまる" in ass
    assert "Dialogue: 0,0:00:04.00,0:00:05.00,Default" in ass


def test_build_ass_wraps_long_text_with_ass_newline():
    events = [AssEvent(0.0, 3.0, "あいうえおかきくけこさしすせそたちつてと", speaker=None)]
    ass = build_ass(events, SubtitleStyle(max_chars_per_line=10))
    assert "あいうえおかきくけこ\\Nさしすせそたちつてと" in ass


# ---- セグメント→イベント変換 ----
def _seg(idx, start, end, text, **over):
    return {
        "id": idx + 1, "idx": idx, "start": start, "end": end, "text": text,
        "speaker": "はやまる", "is_aizuchi": 0, "subtitle_show": "auto_show", **over,
    }


def test_segments_to_events_strips_speaker_prefix_and_offsets():
    segs = [_seg(0, 10.0, 12.0, "はやまる: こんにちは")]
    events = segments_to_events(segs, clip_start=10.0)
    assert events[0].text == "こんにちは"
    assert events[0].start == 0.0


def test_segments_to_events_excludes_aizuchi_and_hidden():
    segs = [
        _seg(0, 0.0, 1.0, "本編"),
        _seg(1, 1.0, 2.0, "うん", is_aizuchi=1),
        _seg(2, 2.0, 3.0, "非採用", subtitle_show="auto_hide"),
        _seg(3, 3.0, 4.0, "手動非採用", subtitle_show="user_hide"),
        _seg(4, 4.0, 5.0, "手動採用", subtitle_show="user_show"),
    ]
    events = segments_to_events(segs)
    assert [e.text for e in events] == ["本編", "手動採用"]


def test_segments_to_events_clip_range_filter():
    segs = [_seg(0, 0.0, 5.0, "前"), _seg(1, 10.0, 12.0, "中"), _seg(2, 70.0, 72.0, "後")]
    events = segments_to_events(segs, clip_start=8.0, clip_end=60.0)
    assert [e.text for e in events] == ["中"]


def test_segments_to_events_extends_short_display_but_not_past_next():
    segs = [
        _seg(0, 0.0, 0.3, "短い字幕テキストです"),   # 0.3秒 → 最低表示時間まで延長
        _seg(1, 0.8, 2.0, "次の字幕"),
    ]
    events = segments_to_events(segs)
    assert events[0].end == pytest.approx(0.8)  # 延長するが次の開始は超えない
