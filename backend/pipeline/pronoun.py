"""指示語置換の中核。

設計はBACKEND_DESIGN.md「指示語置換(積極性 × 表現形式 の2軸)」参照。
LLMは提案するだけで、適用は機械ガードを通過したものだけ。
すべて純関数なのでテストしやすい。
"""

import difflib
from dataclasses import dataclass, field

# ---- 積極性(どの指示語を対象にするか) ----
@dataclass(frozen=True)
class Level:
    key: str
    targets: str
    max_replacement_len: int
    policy: str


LEVELS: dict[str, Level] = {
    "weak": Level(
        key="weak",
        targets="これ・それ・あれ(単体のみ)",
        max_replacement_len=20,
        policy="参照先が一意に明確な場合のみ置き換える。少しでも曖昧なら編集を出さない。",
    ),
    "medium": Level(
        key="medium",
        targets="これ・それ・あれ、および この/その/あの + 名詞",
        max_replacement_len=40,
        policy="参照先が文脈から明確に特定できる場合に置き換える。曖昧なら編集を出さない。",
    ),
    "strong": Level(
        key="strong",
        targets="これ・それ・あれ、この/その/あの + 名詞、こういう/そういう/ああいう",
        max_replacement_len=60,
        policy="文脈から合理的に推定できれば置き換える。ただし推測が飛躍する場合は出さない。",
    ),
}

# 指示語を含むが置換対象にしない慣用表現・複合語
IDIOM_WORDS = (
    "この世", "この間", "このように", "この前", "この後", "このまま",
    "これから", "これまで", "これで", "それぞれ", "それなり", "それでも",
    "それに", "そのまま", "その後", "そのうち", "その通り", "その分",
    "あれこれ", "あれから",
)

EDITS_SCHEMA = {
    "type": "object",
    "properties": {
        "edits": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "line": {"type": "integer"},
                    "original": {"type": "string"},
                    "replacement": {"type": "string"},
                    "referent": {"type": "string"},
                    "confidence": {"type": "string", "enum": ["auto", "review"]},
                },
                "required": ["line", "original", "replacement", "referent", "confidence"],
            },
        }
    },
    "required": ["edits"],
}

BASE_PROMPT = """あなたは対談の文字起こしを校正する編集者です。
与えられた発言の中の指示語のうち、**指している内容が文脈から明確に特定できるものだけ**を
指す内容に置き換える編集案をJSONで出力してください。

今回の対象: {targets}
判断方針: {policy}

厳守するルール:
1. 言い淀み・フィラーとしての「あの」「その」「なんかこう」「こう」は絶対に置き換えない。
   (例:「あの、それでですね」の「あの」はフィラー)
2. 画面・スライド・その場の物など、映像を見ないと分からないものを指す指示語は置き換えない。
3. original は対象行に実際に含まれる連続した文字列を、指示語を含む最小限の範囲で指定する。
4. replacement は置き換えても文が自然につながる表現にする。発言の意味を変えない。
5. 指示語の解決以外の編集(言い回しの修正、誤字修正など)は一切しない。
6. **指示語を単に削除するだけの編集は禁止**。replacement には指す内容を表す具体的な語句を必ず含める。
   (悪い例: 「そのAI」→「AI」、「その人」→「人」 … 参照先を明示していないので出さない)
7. 慣用表現・複合語(この世・これから・それぞれ・そのまま・その後 等)は指示語として扱わない。
8. 人称代名詞(僕・私・俺・あなた・彼・彼女)は置き換えない。話者の名前への置き換えも禁止。
9. 参照先の語が同じ行の中に既に出ている場合は置き換えない(重複した文になるため)。
10. 「編集対象」とマークされた行だけを編集する。「文脈(参照用)」の行は編集しない。
11. referent には指している内容そのもの(名詞句)を書く。
12. confidence は参照先が明白なら "auto"、迷いがあるなら "review" とする。
13. 置き換えるべきものが無ければ {{"edits": []}} を返す。

出力形式: {{"edits": [{{"line": 行番号, "original": "置換前", "replacement": "置換後",
"referent": "指している内容", "confidence": "auto"}}]}}"""


@dataclass
class EditProposal:
    line: int
    original: str
    replacement: str
    referent: str = ""
    confidence: str = "review"


@dataclass
class Validation:
    ok: bool
    reason: str = ""


@dataclass
class PromptParts:
    """プロンプト合成の材料(BACKEND_DESIGN.md「ユーザー指示の注入」の順序)"""

    level: str = "medium"
    glossary: list[dict] = field(default_factory=list)
    instructions: list[str] = field(default_factory=list)
    feedback: list[dict] = field(default_factory=list)
    max_feedback: int = 5


def build_system_prompt(parts: PromptParts) -> str:
    """レベル → 用語集 → カスタム指示 → feedback few-shot の順に合成する"""
    level = LEVELS.get(parts.level) or LEVELS["medium"]
    sections = [BASE_PROMPT.format(targets=level.targets, policy=level.policy)]

    if parts.glossary:
        lines = [
            f"- {g['term']}" + (f": {g['description']}" if g.get("description") else "")
            for g in parts.glossary
        ]
        sections.append("この対談に登場する固有名詞:\n" + "\n".join(lines))

    if parts.instructions:
        sections.append(
            "この対談固有の指示(優先して従うこと):\n"
            + "\n".join(f"- {t}" for t in parts.instructions)
        )

    if parts.feedback:
        examples = []
        for fb in parts.feedback[: parts.max_feedback]:
            line = f"- 「{fb['before']}」→「{fb.get('after') or ''}」は不採用"
            if fb.get("note"):
                line += f"(理由: {fb['note']})"
            examples.append(line)
        sections.append(
            "過去に却下された編集(同じ誤りを繰り返さないこと):\n" + "\n".join(examples)
        )

    return "\n\n".join(sections)


def build_user_prompt(
    lines: list[str], target_lines: list[int], context_size: int = 15
) -> str:
    """編集対象の行(1始まりの行番号)と、参照用の文脈を組み立てる。

    対象行は飛び飛びでもよい(未解決のみ再実行する場合など)。
    対象でない行のうち直前の文脈と対象行の間にあるものは「参照用」として渡す。
    """
    if not target_lines:
        return "## 編集対象\n(なし)"

    targets = sorted(set(target_lines))
    first, last = targets[0], targets[-1]
    target_set = set(targets)
    context = [
        n for n in range(max(1, first - context_size), last + 1)
        if n not in target_set and n <= len(lines)
    ]

    parts = []
    if context:
        parts.append("## 文脈(参照用・編集禁止)")
        parts += [f"{n}: {lines[n - 1]}" for n in context]
    parts.append("## 編集対象")
    parts += [f"{n}: {lines[n - 1]}" for n in targets if n <= len(lines)]
    return "\n".join(parts)


def inserted_chunks(orig: str, repl: str) -> list[str]:
    """origをreplに変えたとき新たに挿入される文字列の一覧"""
    sm = difflib.SequenceMatcher(None, orig, repl)
    return [
        repl[j1:j2]
        for tag, _, _, j1, j2 in sm.get_opcodes()
        if tag in ("replace", "insert")
    ]


def validate_edit(
    edit: EditProposal,
    line_text: str,
    level: str = "medium",
    line_range: tuple[int, int] | None = None,
) -> Validation:
    """LLMの編集案が適用可能かを機械的に検証する。

    プロンプト指示だけではモデルが守りきれないため、コード側で二重に防ぐ。
    実測で観測された誤編集パターン(削除のみ・既出重複・慣用表現)を弾く。
    """
    max_len = (LEVELS.get(level) or LEVELS["medium"]).max_replacement_len

    if line_range and not (line_range[0] <= edit.line <= line_range[1]):
        return Validation(False, "編集対象範囲外の行番号")
    if not edit.original or not edit.replacement or edit.original == edit.replacement:
        return Validation(False, "空または無変更の編集")
    if len(edit.replacement) > max_len:
        return Validation(False, f"置換文字列が長すぎる({len(edit.replacement)}文字)")
    if any(w in edit.original for w in IDIOM_WORDS):
        return Validation(False, "慣用表現のため対象外")
    if edit.original not in line_text:
        return Validation(False, "置換前文字列が行内に存在しない")

    inserted = [c for c in inserted_chunks(edit.original, edit.replacement) if len(c) >= 2]
    if not inserted:
        return Validation(False, "指示語の削除のみ(参照先の明示がない)")

    # 挿入文字列の3文字窓が行内に既出なら、参照先が重複する編集とみなす
    rest_of_line = line_text.replace(edit.original, "", 1)
    windows = [
        c[i:i + 3] if len(c) > 3 else c
        for c in inserted
        for i in range(max(1, len(c) - 2))
    ]
    if any(w in rest_of_line for w in windows):
        return Validation(False, "参照先が同じ行に既出(重複になる)")

    return Validation(True)


def apply_edit(line_text: str, edit: EditProposal, form: str = "annotate") -> str:
    """表現形式に応じて1件の編集を適用する。

    annotate: 発言を変えずカッコで補足(既定・最も安全)
    replace : 指示語を参照先に置き換える
    complete: 置換した上でカッコでも補足する(意訳寄り。レビュー必須)
    """
    if form == "replace":
        return line_text.replace(edit.original, edit.replacement, 1)

    referent = edit.referent or edit.replacement
    if form == "complete":
        return line_text.replace(
            edit.original, f"{edit.replacement}({referent})", 1
        )
    # annotate(既定)
    return line_text.replace(edit.original, f"{edit.original}({referent})", 1)


def parse_edits(payload: dict) -> list[EditProposal]:
    """LLM応答を EditProposal のリストにする(型が緩くても落ちないようにする)"""
    out = []
    for e in payload.get("edits", []) or []:
        try:
            out.append(
                EditProposal(
                    line=int(e.get("line", 0)),
                    original=str(e.get("original", "")),
                    replacement=str(e.get("replacement", "")),
                    referent=str(e.get("referent", "") or ""),
                    confidence="auto" if e.get("confidence") == "auto" else "review",
                )
            )
        except (TypeError, ValueError):
            continue  # 壊れた項目は捨てる(ジョブ全体を落とさない)
    return out
