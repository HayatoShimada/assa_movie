"""文字起こしの手直し(純関数)のテスト。

original_text は常に原文を保持し、表示用の text はそこから
「適用済みの編集」と「手直し」で作られる。ここではその組み立てだけを見る。
"""

import pytest

from backend.pipeline.segment_text import (
    AppliedEdit,
    rebuild_text,
    undo_edit_in_text,
    validate_speaker_name,
)

ORIGINAL = "それがすごく良くて、反動体の話もした"


# ---- 原文+適用済み編集から本文を作り直す ----
@pytest.mark.parametrize(
    ("edits", "form", "expected"),
    [
        ([], "annotate", ORIGINAL),
        (
            [AppliedEdit(id=1, kind="pronoun", original="それ", replacement="ハッカソン",
                         referent="ハッカソン")],
            "annotate",
            "それ(ハッカソン)がすごく良くて、反動体の話もした",
        ),
        (
            [AppliedEdit(id=1, kind="pronoun", original="それ", replacement="ハッカソン",
                         referent="ハッカソン")],
            "replace",
            "ハッカソンがすごく良くて、反動体の話もした",
        ),
        # 固有名詞の一括修正(質問への回答)は置き換え。注釈にしない
        (
            [AppliedEdit(id=2, kind="term", original="反動体", replacement="半導体")],
            "annotate",
            "それがすごく良くて、半導体の話もした",
        ),
        # フィラー除去は字幕を作るときだけ効く(本文は変えない)
        (
            [AppliedEdit(id=3, kind="filler", original="すごく", replacement="")],
            "annotate",
            ORIGINAL,
        ),
        (
            [
                AppliedEdit(id=1, kind="pronoun", original="それ", replacement="ハッカソン",
                            referent="ハッカソン"),
                AppliedEdit(id=2, kind="term", original="反動体", replacement="半導体"),
            ],
            "annotate",
            "それ(ハッカソン)がすごく良くて、半導体の話もした",
        ),
    ],
    ids=["編集なしは原文", "指示語は注釈", "指示語は置換形式", "固有名詞は置き換え",
         "フィラーは本文を変えない", "複数の編集を順に"],
)
def test_rebuild_text(edits, form, expected):
    text, dropped = rebuild_text(ORIGINAL, edits, form=form)
    assert text == expected
    assert dropped == []


def test_rebuild_text_reports_edits_that_no_longer_fit():
    """手直しの上に承認した編集は、原文からは作り直せない(取りこぼしを報告する)"""
    edits = [AppliedEdit(id=9, kind="pronoun", original="あれ", replacement="イベント",
                         referent="イベント")]
    text, dropped = rebuild_text(ORIGINAL, edits, form="annotate")
    assert text == ORIGINAL
    assert dropped == [9]


# ---- 手直し済みの行で、AIの編集だけを取り消す ----
@pytest.mark.parametrize(
    ("text", "edit", "expected"),
    [
        (
            "それ(ハッカソン)がとても良かった",
            AppliedEdit(id=1, kind="pronoun", original="それ", replacement="ハッカソン",
                        referent="ハッカソン"),
            "それがとても良かった",
        ),
        # 承認したときの表現形式は記録していないので、どの形式でも戻せる
        (
            "ハッカソンがとても良かった",
            AppliedEdit(id=1, kind="pronoun", original="それ", replacement="ハッカソン",
                        referent="ハッカソン"),
            "それがとても良かった",
        ),
        # 補完形式は置換形式の文字列を含む。長い方を先に外す
        (
            "ハッカソン(ハッカソン)がとても良かった",
            AppliedEdit(id=1, kind="pronoun", original="それ", replacement="ハッカソン",
                        referent="ハッカソン"),
            "それがとても良かった",
        ),
        (
            "半導体の話と半導体の未来",
            AppliedEdit(id=2, kind="term", original="反動体", replacement="半導体"),
            "反動体の話と反動体の未来",
        ),
        # 手直しで該当箇所が消えている → 戻せない(None)
        (
            "とても良かった",
            AppliedEdit(id=1, kind="pronoun", original="それ", replacement="ハッカソン",
                        referent="ハッカソン"),
            None,
        ),
    ],
    ids=["注釈を外す", "置換形式で入ったものを戻す", "補完形式を戻す", "固有名詞を戻す", "見つからなければ戻せない"],
)
def test_undo_edit_in_text(text, edit, expected):
    assert undo_edit_in_text(text, edit) == expected


# ---- 話者名 ----
@pytest.mark.parametrize(
    ("name", "error"),
    [
        ("山田", None),
        ("  高田さん  ", None),  # 前後の空白は落として受け付ける
        ("", "名前を入れてください"),
        ("   ", "名前を入れてください"),
        ("あ" * 21, "話者名は20文字以内にしてください"),
        # 字幕ファイル(ASS)の区切りと、本文の「話者: 」表記に使う文字
        ("山田,太郎", "話者名に「,」「:」は使えません"),
        ("山田:太郎", "話者名に「,」「:」は使えません"),
        ("山田\n太郎", "話者名に改行は使えません"),
    ],
)
def test_validate_speaker_name(name, error):
    assert validate_speaker_name(name) == error
