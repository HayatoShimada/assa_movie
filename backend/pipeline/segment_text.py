"""文字起こしの本文を組み立て直す・戻す(純関数)。

segments.original_text は常に原文(文字起こし結果)のまま保持する。
表示用の segments.text は次の2通りで変わる:
  - 編集(edits)の適用: 指示語の注釈(kind='pronoun')・固有名詞の一括修正(kind='term')
  - 利用者の手直し(PATCH /api/segments/{id}。edited_by_user=1 になる)

手直しの無い行は「原文 + 適用済みの編集」から作り直せる(rebuild_text)。
手直しのある行は作り直すと手直しが消えるので、その編集の部分だけを戻す
(undo_edit_in_text)。フィラー除去(kind='filler')は字幕を作るときだけ効き、
本文は変えないので、ここでは扱わない。
"""

from dataclasses import dataclass

from backend.pipeline import pronoun

FORMS = ("annotate", "replace", "complete")

SPEAKER_NAME_MAX = 20


@dataclass(frozen=True)
class AppliedEdit:
    id: int
    kind: str
    original: str
    replacement: str
    referent: str = ""


def _proposal(edit: AppliedEdit) -> pronoun.EditProposal:
    return pronoun.EditProposal(
        line=0, original=edit.original, replacement=edit.replacement,
        referent=edit.referent or "",
    )


def apply_one(text: str, edit: AppliedEdit, form: str) -> str | None:
    """1件の編集を本文に当てる。当てる場所が無ければ None"""
    if edit.kind == "filler":
        return text  # 本文は変えない(字幕生成時に除去する)
    if not edit.original or edit.original not in text:
        return None
    if edit.kind == "term":
        # 質問への回答による固有名詞の修正は、行内の全出現を置き換える(terms_job と同じ)
        return text.replace(edit.original, edit.replacement)
    return pronoun.apply_edit(text, _proposal(edit), form=form)


def rebuild_text(
    original_text: str, edits: list[AppliedEdit], form: str
) -> tuple[str, list[int]]:
    """原文に適用済みの編集を順に当てて本文を作る。

    戻り値は (本文, 当てられなかった編集のid)。当てられないのは、手直しした文に対して
    承認した編集など、原文には無い文字列を対象にしたもの。
    """
    text = original_text
    dropped: list[int] = []
    for edit in edits:
        applied = apply_one(text, edit, form)
        if applied is None:
            dropped.append(edit.id)
        else:
            text = applied
    return text, dropped


def undo_edit_in_text(text: str, edit: AppliedEdit) -> str | None:
    """手直し済みの本文から、1件の編集が入れた部分だけを元に戻す。

    承認したときの表現形式は記録していないので、全形式を試す。補完形式の
    「ハッカソン(ハッカソン)」は置換形式の「ハッカソン」を含むので、長いものから試す。
    手直しで該当箇所が消えていれば戻せない(None)。
    """
    if edit.kind == "filler":
        return text
    if edit.kind == "term":
        if not edit.replacement or edit.replacement not in text:
            return None
        return text.replace(edit.replacement, edit.original)
    pieces = {pronoun.apply_edit(edit.original, _proposal(edit), form=f) for f in FORMS}
    pieces.discard(edit.original)
    for piece in sorted(pieces, key=len, reverse=True):
        if piece in text:
            return text.replace(piece, edit.original, 1)
    return None


def validate_speaker_name(name: str) -> str | None:
    """話者名として使えるか。使えなければ理由(画面にそのまま出す)を返す"""
    if "\n" in name or "\r" in name:
        return "話者名に改行は使えません"
    stripped = name.strip()
    if not stripped:
        return "名前を入れてください"
    if len(stripped) > SPEAKER_NAME_MAX:
        return f"話者名は{SPEAKER_NAME_MAX}文字以内にしてください"
    # 「,」は字幕ファイル(ASS)の区切り、「:」は本文の「話者: 」表記に使われている
    if "," in stripped or ":" in stripped:
        return "話者名に「,」「:」は使えません"
    return None
