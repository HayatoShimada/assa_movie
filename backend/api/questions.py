"""LLMからの質問(固有名詞の表記確認など)のAPI。"""

import json
import sqlite3

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.api.deps import get_db
from backend.jobs.terms_job import apply_term_answer

router = APIRouter(prefix="/api", tags=["questions"])


class Question(BaseModel):
    id: int
    media_id: int
    kind: str
    question_text: str
    candidates: list[str] = []
    target: dict = {}
    status: str
    answer: str | None = None
    created_at: str


class Answer(BaseModel):
    text: str


def _to_question(row: sqlite3.Row) -> Question:
    return Question(
        id=row["id"], media_id=row["media_id"], kind=row["kind"],
        question_text=row["question_text"],
        candidates=json.loads(row["candidates_json"] or "[]"),
        target=json.loads(row["target_json"] or "{}"),
        status=row["status"], answer=row["answer"], created_at=row["created_at"],
    )


@router.get("/media/{media_id}/questions", response_model=list[Question])
def list_questions(
    media_id: int, status: str | None = "open", db: sqlite3.Connection = Depends(get_db)
):
    sql = "SELECT * FROM questions WHERE media_id=?"
    args: list = [media_id]
    if status:
        sql += " AND status=?"
        args.append(status)
    return [_to_question(r) for r in db.execute(sql + " ORDER BY id", args)]


@router.post("/questions/{question_id}/answer")
def answer_question(
    question_id: int, body: Answer, db: sqlite3.Connection = Depends(get_db)
):
    try:
        return apply_term_answer(db, question_id, body.text)
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.post("/questions/{question_id}/dismiss", response_model=Question)
def dismiss_question(question_id: int, db: sqlite3.Connection = Depends(get_db)):
    row = db.execute("SELECT * FROM questions WHERE id=?", (question_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "質問が見つかりません")
    db.execute("UPDATE questions SET status='dismissed' WHERE id=?", (question_id,))
    db.commit()
    return _to_question(db.execute(
        "SELECT * FROM questions WHERE id=?", (question_id,)
    ).fetchone())
