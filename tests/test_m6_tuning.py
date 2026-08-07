"""M6: 実Ollama(qwen3:32b)+雑談編での実測から得た調整のテスト。

2026-08-07の実測で観測された問題:
  1. 「これ → そのこと」— 置換先が指示語のままで具体性がない
  2. 「そこと矛盾した(感受性)」— 注釈がフレーズ末尾に付いて読みにくい
"""

import pytest

from backend.pipeline.pronoun import (
    EditProposal,
    apply_edit,
    is_demonstrative_only,
    normalize_edit,
)


# ---- 指示語のみ判定 ----
@pytest.mark.parametrize(
    "text,expected",
    [
        ("そのこと", True),      # 実測: qwen3が出した
        ("それ", True),
        ("あれ", True),
        ("このこと", True),
        ("それを", True),
        ("そのもの", True),
        ("洋服", False),
        ("去年のハッカソン", False),
        ("知りたいという動機", False),
        ("スヌーティーの猫", False),
        ("", False),
    ],
)
def test_is_demonstrative_only(text, expected):
    assert is_demonstrative_only(text) is expected


# ---- 正規化 ----
def test_normalize_uses_referent_when_replacement_is_demonstrative():
    """実測ケース:「これ→そのこと」でもreferentが具体的なら救済し、必ずreviewに回す"""
    e = EditProposal(line=1, original="これ", replacement="そのこと",
                     referent="知りたいという動機", confidence="auto")
    out = normalize_edit(e)
    assert out is not None
    assert out.replacement == "知りたいという動機"
    assert out.confidence == "review"  # 補正した編集は自動適用しない


def test_normalize_rejects_when_both_are_demonstrative():
    e = EditProposal(line=1, original="これ", replacement="そのこと", referent="それ")
    assert normalize_edit(e) is None


def test_normalize_keeps_concrete_replacement_as_is():
    e = EditProposal(line=1, original="これ", replacement="洋服",
                     referent="洋服", confidence="auto")
    out = normalize_edit(e)
    assert out is e  # 変更なし(confidenceも保持)


# ---- 注釈の挿入位置 ----
def test_annotate_inserts_after_leading_demonstrative():
    """実測ケース: 「そこと矛盾した」→「そこ(感受性)と矛盾した」"""
    e = EditProposal(line=1, original="そこと矛盾した", replacement="感受性と矛盾した",
                     referent="感受性")
    out = apply_edit("なんかそこと矛盾した表面的な何か、", e, form="annotate")
    assert out == "なんかそこ(感受性)と矛盾した表面的な何か、"


def test_annotate_simple_demonstrative_unchanged():
    e = EditProposal(line=1, original="これ", replacement="洋服", referent="洋服")
    assert apply_edit("これ、", e, form="annotate") == "これ(洋服)、"


def test_annotate_demonstrative_plus_noun_annotates_whole():
    """「この人」のような指示語+名詞は「この(稲見)人」にせず名詞ごと注釈する"""
    e = EditProposal(line=1, original="この人", replacement="稲見", referent="稲見")
    assert apply_edit("この人とは多分", e, form="annotate") == "この人(稲見)とは多分"


def test_annotate_demonstrative_plus_noun_phrase():
    e = EditProposal(line=1, original="そういう話", replacement="ステレオタイプの話",
                     referent="ステレオタイプの話")
    assert apply_edit("そういう話があって", e, form="annotate") == \
        "そういう話(ステレオタイプの話)があって"


def test_annotate_demonstrative_followed_by_particle_wo():
    e = EditProposal(line=1, original="これを", replacement="意識のメカニズムを",
                     referent="意識のメカニズム")
    assert apply_edit("これを自由エネルギーっていう", e, form="annotate") == \
        "これ(意識のメカニズム)を自由エネルギーっていう"
