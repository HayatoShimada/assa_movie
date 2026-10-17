"""編集提案のレビューAPI(承認・却下・取り消し)と、指示・用語集のCRUD。"""

import sqlite3

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.api.deps import get_db
from backend.api.transcripts import automatic_text
from backend.core.project_settings import resolve_settings
from backend.pipeline import pronoun
from backend.pipeline.segment_text import AppliedEdit, undo_edit_in_text

router = APIRouter(prefix="/api", tags=["edits"])


class Edit(BaseModel):
    id: int
    media_id: int
    segment_id: int
    kind: str
    original: str
    replacement: str
    referent: str | None = None
    status: str
    confidence: str
    created_by: str
    created_at: str


class EditAccept(BaseModel):
    replacement: str | None = None  # 修正して承認する場合
    form: str | None = None         # annotate | replace | complete


class EditReject(BaseModel):
    note: str | None = None


class InstructionCreate(BaseModel):
    text: str
    scope: str = "all"
    media_id: int | None = None


class GlossaryCreate(BaseModel):
    term: str
    reading: str | None = None
    description: str | None = None


def _get_edit(db: sqlite3.Connection, edit_id: int) -> sqlite3.Row:
    row = db.execute("SELECT * FROM edits WHERE id=?", (edit_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "編集が見つかりません")
    return row


@router.get("/media/{media_id}/edits", response_model=list[Edit])
def list_edits(
    media_id: int, status: str | None = None, db: sqlite3.Connection = Depends(get_db)
):
    sql = "SELECT * FROM edits WHERE media_id=?"
    args: list = [media_id]
    if status:
        sql += " AND status=?"
        args.append(status)
    return [Edit(**dict(r)) for r in db.execute(sql + " ORDER BY id", args)]


@router.post("/edits/{edit_id}/accept", response_model=Edit)
def accept_edit(
    edit_id: int, body: EditAccept, db: sqlite3.Connection = Depends(get_db)
):
    edit = _get_edit(db, edit_id)
    if edit["status"] == "applied":
        return Edit(**dict(edit))

    seg = db.execute("SELECT * FROM segments WHERE id=?", (edit["segment_id"],)).fetchone()
    if seg is None:
        raise HTTPException(404, "対象セグメントが見つかりません")

    replacement = body.replacement or edit["replacement"]
    proposal = pronoun.EditProposal(
        line=0, original=edit["original"], replacement=replacement,
        referent=edit["referent"] or "",
    )
    s = resolve_settings(db, media_id=edit["media_id"])
    v = pronoun.validate_edit(proposal, seg["text"], level=s.pronoun_level)
    if not v.ok:
        raise HTTPException(400, f"この編集は適用できません: {v.reason}")

    new_text = pronoun.apply_edit(seg["text"], proposal, form=body.form or s.pronoun_form)
    db.execute("UPDATE segments SET text=? WHERE id=?", (new_text, seg["id"]))
    db.execute(
        "UPDATE edits SET status='applied', replacement=? WHERE id=?", (replacement, edit_id)
    )
    if body.replacement and body.replacement != edit["replacement"]:
        # ユーザーによる修正は学習材料として残す
        db.execute(
            "INSERT INTO feedback (media_id, edit_id, kind, before, after, note)"
            " VALUES (?,?,'correction',?,?,'ユーザーが修正して承認')",
            (edit["media_id"], edit_id, edit["replacement"], body.replacement),
        )
    db.commit()
    return Edit(**dict(_get_edit(db, edit_id)))


@router.post("/edits/{edit_id}/reject", response_model=Edit)
def reject_edit(
    edit_id: int, body: EditReject, db: sqlite3.Connection = Depends(get_db)
):
    edit = _get_edit(db, edit_id)
    if edit["status"] == "applied":
        raise HTTPException(400, "適用済みの編集は取り消し(revert)を使ってください")
    db.execute("UPDATE edits SET status='rejected' WHERE id=?", (edit_id,))
    db.execute(
        "INSERT INTO feedback (media_id, edit_id, kind, before, after, note)"
        " VALUES (?,?,'rejection',?,?,?)",
        (edit["media_id"], edit_id, edit["original"], edit["replacement"], body.note),
    )
    db.commit()
    return Edit(**dict(_get_edit(db, edit_id)))


@router.post("/edits/{edit_id}/revert", response_model=Edit)
def revert_edit(edit_id: int, db: sqlite3.Connection = Depends(get_db)):
    edit = _get_edit(db, edit_id)
    if edit["status"] != "applied":
        raise HTTPException(400, "適用済みの編集ではありません")

    seg = db.execute("SELECT * FROM segments WHERE id=?", (edit["segment_id"],)).fetchone()
    if seg["edited_by_user"]:
        # 手で直した行は原文から作り直すと手直しが消えるので、この編集の部分だけを戻す
        text = undo_edit_in_text(
            seg["text"],
            AppliedEdit(
                id=edit["id"], kind=edit["kind"], original=edit["original"],
                replacement=edit["replacement"], referent=edit["referent"] or "",
            ),
        )
        if text is None:
            raise HTTPException(
                400,
                "この行は手で直してあり、AIの修正箇所が見つからないため取り消せません。"
                "文字起こしの画面で直接直してください",
            )
        db.execute("UPDATE edits SET status='reverted' WHERE id=?", (edit_id,))
    else:
        # 同一セグメントの他の適用済み編集を原文から再適用して復元する
        db.execute("UPDATE edits SET status='reverted' WHERE id=?", (edit_id,))
        text, _dropped = automatic_text(db, seg)
    db.execute("UPDATE segments SET text=? WHERE id=?", (text, seg["id"]))
    db.commit()
    return Edit(**dict(_get_edit(db, edit_id)))


# ---- カスタム指示・用語集 ----
@router.get("/projects/{project_id}/instructions")
def list_instructions(project_id: int, db: sqlite3.Connection = Depends(get_db)):
    return [dict(r) for r in db.execute(
        "SELECT * FROM llm_instructions WHERE project_id=? ORDER BY id", (project_id,)
    )]


@router.post("/projects/{project_id}/instructions")
def create_instruction(
    project_id: int, body: InstructionCreate, db: sqlite3.Connection = Depends(get_db)
):
    cur = db.execute(
        "INSERT INTO llm_instructions (project_id, media_id, scope, text) VALUES (?,?,?,?)",
        (project_id, body.media_id, body.scope, body.text),
    )
    db.commit()
    return dict(db.execute(
        "SELECT * FROM llm_instructions WHERE id=?", (cur.lastrowid,)
    ).fetchone())


@router.patch("/instructions/{instruction_id}")
def toggle_instruction(
    instruction_id: int, enabled: bool, db: sqlite3.Connection = Depends(get_db)
):
    db.execute(
        "UPDATE llm_instructions SET enabled=? WHERE id=?", (int(enabled), instruction_id)
    )
    db.commit()
    row = db.execute(
        "SELECT * FROM llm_instructions WHERE id=?", (instruction_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(404, "指示が見つかりません")
    return dict(row)


@router.get("/projects/{project_id}/glossary")
def list_glossary(project_id: int, db: sqlite3.Connection = Depends(get_db)):
    return [dict(r) for r in db.execute(
        "SELECT * FROM glossary WHERE project_id=? ORDER BY id", (project_id,)
    )]


@router.post("/projects/{project_id}/glossary")
def create_glossary(
    project_id: int, body: GlossaryCreate, db: sqlite3.Connection = Depends(get_db)
):
    cur = db.execute(
        "INSERT INTO glossary (project_id, term, reading, description) VALUES (?,?,?,?)",
        (project_id, body.term, body.reading, body.description),
    )
    db.commit()
    return dict(db.execute("SELECT * FROM glossary WHERE id=?", (cur.lastrowid,)).fetchone())
