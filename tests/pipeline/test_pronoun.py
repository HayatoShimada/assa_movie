"""M4: 指示語置換の純関数(プロンプト合成・機械ガード・表現形式)のテスト"""

import pytest

from backend.pipeline.pronoun import (
    EDITS_SCHEMA,
    LEVELS,
    EditProposal,
    PromptParts,
    apply_edit,
    build_system_prompt,
    build_user_prompt,
    inserted_chunks,
    parse_edits,
    validate_edit,
)

LINE = "はやまる: その時高田さんは自分の書いたエッセイ"


# ---- プロンプト合成 ----
def test_system_prompt_includes_level_targets():
    weak = build_system_prompt(PromptParts(level="weak"))
    strong = build_system_prompt(PromptParts(level="strong"))
    assert LEVELS["weak"].targets in weak
    assert "こういう/そういう/ああいう" in strong
    assert "こういう" not in weak.split("判断方針")[0].replace(LEVELS["weak"].targets, "")


def test_system_prompt_composition_order():
    """レベル → 用語集 → カスタム指示 → feedback の順に並ぶ"""
    p = PromptParts(
        level="medium",
        glossary=[{"term": "箱ストア", "description": "古着店"}],
        instructions=["『あれ』は基本的にAIハッカソンを指す"],
        feedback=[{"before": "その人", "after": "人", "note": "削除のみ"}],
    )
    prompt = build_system_prompt(p)
    i_glossary = prompt.index("箱ストア")
    i_instruction = prompt.index("AIハッカソン")
    i_feedback = prompt.index("却下された編集")
    assert i_glossary < i_instruction < i_feedback


def test_system_prompt_limits_feedback_examples():
    p = PromptParts(
        feedback=[{"before": f"x{i}", "after": "y"} for i in range(20)], max_feedback=3
    )
    prompt = build_system_prompt(p)
    assert prompt.count("は不採用") == 3


def test_system_prompt_without_optional_parts():
    prompt = build_system_prompt(PromptParts())
    assert "固有名詞" not in prompt
    assert "却下された編集" not in prompt


def test_user_prompt_marks_context_and_targets():
    lines = [f"行{i}" for i in range(10)]
    out = build_user_prompt(lines, target_lines=[6, 7, 8], context_size=2)
    assert "## 文脈(参照用・編集禁止)" in out
    assert "4: 行3" in out and "5: 行4" in out       # 文脈は1始まりの行番号
    targets = out.split("## 編集対象")[1]
    assert "6: 行5" in targets and "8: 行7" in targets
    assert "9: 行8" not in out                        # 範囲外は含めない


def test_user_prompt_without_context_at_start():
    out = build_user_prompt(["a", "b"], target_lines=[1, 2])
    assert "## 文脈" not in out
    assert "1: a" in out


def test_user_prompt_handles_non_contiguous_targets():
    """未解決のみ再実行する場合、対象行は飛び飛びになる"""
    lines = [f"行{i}" for i in range(5)]
    out = build_user_prompt(lines, target_lines=[1, 3], context_size=0)
    targets = out.split("## 編集対象")[1]
    assert "1: 行0" in targets and "3: 行2" in targets
    assert "2: 行1" not in targets          # 対象外の行は編集対象に入れない
    assert "2: 行1" in out.split("## 編集対象")[0]  # ただし文脈としては渡す


def test_user_prompt_with_no_targets():
    assert "(なし)" in build_user_prompt(["a"], target_lines=[])


# ---- 機械ガード(実測で観測された誤編集パターン) ----
@pytest.mark.parametrize(
    "original,replacement,line,ok,reason_part",
    [
        # 良い編集
        ("その時", "富山変人会のイベントの時", LINE, True, ""),
        # 指示語を消すだけ(参照先を明示していない)
        ("その人", "人", "はやまる: その人自身が", False, "削除のみ"),
        ("そのAI", "AI", "はやまる: 僕はそのAIと会話する", False, "削除のみ"),
        # 参照先が同じ行に既出 → 重複した文になる
        (
            "これAIで作った", "AIでチラシを作った",
            "高田さん: なんかちょっとしたなんかチラシとかをこれAIで作ったとかいう人",
            False, "既出",
        ),
        # 慣用表現
        ("この世って", "社会って", "はやまる: この世って歪んでるんだな", False, "慣用表現"),
        ("これから", "今後", "はやまる: これからの話", False, "慣用表現"),
        # 行内に存在しない
        ("存在しない語", "何か", LINE, False, "存在しない"),
        # 無変更
        ("その時", "その時", LINE, False, "無変更"),
    ],
)
def test_validate_edit_guards(original, replacement, line, ok, reason_part):
    v = validate_edit(EditProposal(line=1, original=original, replacement=replacement), line)
    assert v.ok is ok
    if not ok:
        assert reason_part in v.reason


def test_validate_edit_rejects_too_long_replacement_by_level():
    long_repl = "あ" * 30
    line = f"はやまる: それがすごい"
    edit = EditProposal(line=1, original="それ", replacement=long_repl)
    assert validate_edit(edit, line, level="weak").ok is False     # 上限20文字
    assert validate_edit(edit, line, level="medium").ok is True    # 上限40文字


def test_validate_edit_rejects_out_of_range_line():
    edit = EditProposal(line=99, original="その時", replacement="イベントの時")
    v = validate_edit(edit, LINE, line_range=(1, 30))
    assert v.ok is False and "範囲外" in v.reason


def test_inserted_chunks():
    assert "".join(inserted_chunks("その時", "イベントの時")) == "イベント"
    assert inserted_chunks("その人", "人") == []  # 削除のみなら挿入なし


# ---- 表現形式 ----
def test_apply_edit_annotate_preserves_original_wording():
    edit = EditProposal(line=1, original="それ", replacement="去年のハッカソン",
                        referent="去年のハッカソン")
    out = apply_edit("はやまる: それがすごくて", edit, form="annotate")
    assert out == "はやまる: それ(去年のハッカソン)がすごくて"
    assert "それ" in out  # 発言そのものは変えない


def test_apply_edit_replace():
    edit = EditProposal(line=1, original="それ", replacement="去年のハッカソン",
                        referent="去年のハッカソン")
    assert apply_edit("はやまる: それがすごくて", edit, form="replace") == \
        "はやまる: 去年のハッカソンがすごくて"


def test_apply_edit_complete():
    edit = EditProposal(line=1, original="それ", replacement="ハッカソン",
                        referent="運営も内容も良かったハッカソン")
    out = apply_edit("はやまる: それがすごくて", edit, form="complete")
    assert out == "はやまる: ハッカソン(運営も内容も良かったハッカソン)がすごくて"


def test_apply_edit_annotate_falls_back_to_replacement_when_no_referent():
    edit = EditProposal(line=1, original="それ", replacement="ハッカソン", referent="")
    assert apply_edit("それだよ", edit, form="annotate") == "それ(ハッカソン)だよ"


def test_apply_edit_only_first_occurrence():
    edit = EditProposal(line=1, original="それ", replacement="X", referent="X")
    assert apply_edit("それとそれ", edit, form="replace") == "Xとそれ"


# ---- 応答パース ----
def test_parse_edits_normalizes_confidence():
    payload = {"edits": [
        {"line": "3", "original": "a", "replacement": "b", "referent": "r", "confidence": "auto"},
        {"line": 4, "original": "c", "replacement": "d"},  # confidence欠落
    ]}
    edits = parse_edits(payload)
    assert edits[0].line == 3 and edits[0].confidence == "auto"
    assert edits[1].confidence == "review"  # 既定は要レビュー


def test_parse_edits_skips_broken_items():
    payload = {"edits": [
        {"line": "not-a-number", "original": "a", "replacement": "b"},
        {"line": 2, "original": "c", "replacement": "d"},
    ]}
    assert [e.line for e in parse_edits(payload)] == [2]


def test_parse_edits_handles_empty():
    assert parse_edits({}) == []
    assert parse_edits({"edits": None}) == []


def test_schema_requires_confidence_and_referent():
    props = EDITS_SCHEMA["properties"]["edits"]["items"]
    assert set(props["required"]) >= {"line", "original", "replacement", "referent", "confidence"}
