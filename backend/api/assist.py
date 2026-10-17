"""対話アシスト: セグメントを選んで自然言語で指示し、編集提案を受け取る。

例:「この『それ』は文字起こしアプリのこと」→ LLMが編集提案を返す → 承認で適用。
提案は通常のeditsとして保存されるので、レビュー・取り消し・feedback学習を共用できる。
"""

import sqlite3

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.api.deps import get_db
from backend.api.edits import Edit
from backend.core.project_settings import resolve_settings
from backend.jobs.resolve_job import _get_client, _load_prompt_parts
from backend.pipeline import pronoun
from backend.pipeline.assist_reply import compose_assist_reply

router = APIRouter(prefix="/api", tags=["assist"])

ASSIST_SCHEMA = {
    "type": "object",
    "properties": {
        "reply": {"type": "string"},
        "edits": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "original": {"type": "string"},
                    "replacement": {"type": "string"},
                    "referent": {"type": "string"},
                },
                "required": ["original", "replacement", "referent"],
            },
        },
        "instruction_suggestion": {"type": "string"},
    },
    "required": ["reply", "edits"],
}

ASSIST_PROMPT = """あなたは対談の文字起こしを校正する編集アシスタントです。
ユーザーが対象行についての指示や質問を日本語で伝えるので、それに従って編集案を出してください。

ルール:
1. 編集は「対象行」だけに対して行う。original は対象行に実際に含まれる連続した文字列にする。
2. referent には指している内容(名詞句)を書く。
3. ユーザーの指示が編集を必要としない質問なら、edits は空にして reply で答える。
4. reply には何をしたか・何が分かったかを1〜2文の日本語で書く。
5. ユーザーの指示が「今後も同じ解釈を使うべき恒久的なルール」に見える場合は
   instruction_suggestion にルール文を1文で書く(例:「『あれ』は基本的に先月のイベントを指す」)。
   一度きりの修正なら instruction_suggestion は空にする。"""

CONTEXT_RADIUS = 10  # 対象行の前後に渡す文脈の行数


class AssistRequest(BaseModel):
    message: str


class AssistEdit(Edit):
    # 承認したときの行の本文(今の表現形式で当てた結果)。「何が変わるか」を見せるため
    after_text: str


class AssistResponse(BaseModel):
    # 実際の状態(承認待ちの案が何件あるか等)から機械側で作る文。
    # LLMの返事は「変更しました」と言いがちだが、この時点では何も変わっていない
    reply: str
    edits: list[AssistEdit]
    instruction_suggestion: str | None = None


@router.post("/segments/{segment_id}/assist", response_model=AssistResponse)
def assist(
    segment_id: int, body: AssistRequest, db: sqlite3.Connection = Depends(get_db)
):
    seg = db.execute("SELECT * FROM segments WHERE id=?", (segment_id,)).fetchone()
    if seg is None:
        raise HTTPException(404, "セグメントが見つかりません")

    media_id = seg["media_id"]
    rows = db.execute(
        "SELECT idx, text FROM segments WHERE media_id=? AND idx BETWEEN ? AND ? ORDER BY idx",
        (media_id, seg["idx"] - CONTEXT_RADIUS, seg["idx"] + CONTEXT_RADIUS),
    ).fetchall()
    context = "\n".join(
        f"{'▶ 対象行' if r['idx'] == seg['idx'] else '  文脈'}: {r['text']}" for r in rows
    )

    s = resolve_settings(db, media_id=media_id)
    parts = _load_prompt_parts(db, media_id, s.pronoun_level)
    system = ASSIST_PROMPT
    if parts.glossary:
        terms = ", ".join(g["term"] for g in parts.glossary)
        system += f"\n\nこの対談の固有名詞: {terms}"

    user = f"{context}\n\nユーザーの指示: {body.message}"
    payload = _get_client(s).complete_json(system, user, ASSIST_SCHEMA)

    saved: list[AssistEdit] = []
    proposals: list[tuple[str, str]] = []
    rejected: list[str] = []
    for e in payload.get("edits", []) or []:
        proposal = pronoun.EditProposal(
            line=0,
            original=str(e.get("original", "")),
            replacement=str(e.get("replacement", "")),
            referent=str(e.get("referent", "") or ""),
            confidence="review",
        )
        # ユーザー主導の編集でも機械ガードは通す(壊れた提案の適用を防ぐ)
        v = pronoun.validate_edit(proposal, seg["text"], level=s.pronoun_level)
        if not v.ok:
            rejected.append(v.reason)
            continue
        cur = db.execute(
            "INSERT INTO edits (media_id, segment_id, kind, original, replacement,"
            " referent, status, confidence, created_by)"
            " VALUES (?,?,'pronoun',?,?,?,'proposed','review','assist')",
            (media_id, segment_id, proposal.original, proposal.replacement, proposal.referent),
        )
        row = db.execute("SELECT * FROM edits WHERE id=?", (cur.lastrowid,)).fetchone()
        saved.append(AssistEdit(
            **dict(row),
            after_text=pronoun.apply_edit(seg["text"], proposal, form=s.pronoun_form),
        ))
        proposals.append((
            proposal.original,
            pronoun.apply_edit(proposal.original, proposal, form=s.pronoun_form),
        ))
    db.commit()

    suggestion = str(payload.get("instruction_suggestion") or "").strip() or None
    reply = compose_assist_reply(str(payload.get("reply", "") or ""), proposals, rejected)
    return AssistResponse(reply=reply, edits=saved, instruction_suggestion=suggestion)
