"""M7-5: フィラー排除のテスト(言語学ベースのシグナル判別含む)"""

import pytest

from backend.pipeline.filler import (
    FillerSignals,
    analyze_line,
    collect_signals,
    remove_filler,
    remove_fillers_weak,
    validate_filler,
)


# ---- 安全群の機械除去(弱モード) ----
@pytest.mark.parametrize(
    "text,expected",
    [
        ("えっと、今日は晴れです", "今日は晴れです"),
        ("あのー、それでですね", "それでですね"),
        ("そのー、人と話すときに", "人と話すときに"),      # 長音つき=フィラー
        ("あのーーそれで", "それで"),                      # 長音の連続
        ("えーと今日は", "今日は"),
        ("うーんと、どうかな", "どうかな"),
        # 読点つきのみ除去する語
        ("あー、それはですね", "それはですね"),
        ("まあ、そうですね", "そうですね"),
        ("その、人と話すとき", "人と話すとき"),
        # 除去してはいけないケース(意味を持つ用法)
        ("その人と話すとき", "その人と話すとき"),          # 指示語(読点なし)
        ("まあまあの出来です", "まあまあの出来です"),      # 「まあまあ」は別語
        ("あの本を読んだ", "あの本を読んだ"),              # 指示語
        ("うーんと唸った", "うーんと唸った"),              # 「うーんと唸る」は動作
        # 文中の出現
        ("今日は、えっと、晴れです", "今日は、晴れです"),
        ("今日は、あー、晴れです", "今日は、晴れです"),
        # 変化なし
        ("普通の文です", "普通の文です"),
    ],
)
def test_remove_fillers_weak(text, expected):
    assert remove_fillers_weak(text) == expected


# ---- 言語学ベースのシグナル分類 ----
def test_classify_elongated_is_filler_likely():
    """長音で伸びる「そのー」はフィラーの可能性が高い(ユーザー知見+文献)"""
    s = FillerSignals(elongated=True)
    assert s.classify() == "filler_likely"


def test_classify_duration_and_pause_is_filler_likely():
    """発話が長く直後にポーズ → 言い淀み"""
    s = FillerSignals(duration=0.5, gap_after=0.4)
    assert s.classify() == "filler_likely"


def test_classify_followed_by_noun_is_demonstrative():
    """後続が漢字/カタカナ(名詞)なら連体詞用法の可能性が高い"""
    s = FillerSignals(next_is_kanji_katakana=True)
    assert s.classify() == "demonstrative_likely"


def test_classify_low_probability_adds_filler_evidence():
    """Whisperの単語確率が低い=音が崩れている → フィラー寄り"""
    s = FillerSignals(duration=0.5, probability=0.3)
    assert s.classify() == "filler_likely"
    assert FillerSignals(duration=0.5, probability=0.9).classify() == "ambiguous"


def test_classify_short_clean_is_ambiguous():
    s = FillerSignals(duration=0.2, gap_after=0.05)
    assert s.classify() == "ambiguous"


def test_collect_signals_reads_text_and_words():
    words = [
        {"start": 0.0, "end": 0.5, "text": "その", "probability": 0.4},
        {"start": 0.9, "end": 1.2, "text": "人と", "probability": 0.9},
    ]
    s = collect_signals("その", "その、人と話すとき", words)
    assert s.followed_by_comma is True
    assert s.duration == 0.5
    assert s.gap_after == pytest.approx(0.4)
    assert s.probability == 0.4


def test_collect_signals_detects_following_noun():
    s = collect_signals("その", "その半導体の話", None)
    assert s.next_is_kanji_katakana is True
    s2 = collect_signals("その", "その、でですね", None)
    assert s2.next_is_kanji_katakana is False


def test_analyze_line_classifies_candidates():
    words = [{"start": 0.0, "end": 0.6, "text": "そのー", "probability": 0.5}]
    out = analyze_line("そのー、人と話すとき", words)
    assert any(c["word"] == "その" and c["class"] == "filler_likely" for c in out)


def test_analyze_line_skips_multiple_occurrences():
    out = analyze_line("そのそのその", None)
    assert all(c["word"] != "その" for c in out)


# ---- 強モードの検証と適用 ----
def test_validate_filler():
    assert validate_filler("なんか", "なんかいい感じ") is True
    assert validate_filler("なんか", "なんかなんか") is False   # 2回出現は曖昧
    assert validate_filler("存在しない", "テキスト") is False   # 候補語以外は拒否


def test_remove_filler_takes_comma_along():
    assert remove_filler("なんか、いい感じ", "なんか") == "いい感じ"
    assert remove_filler("今日は、なんか、いい", "なんか") == "今日は、いい"
    assert remove_filler("なんかいい感じ", "なんか") == "いい感じ"
