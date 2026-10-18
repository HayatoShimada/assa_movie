"""利用者の辞書(名前・用語)のAPI。設定タブの「名前・用語の辞書」と対応する。

辞書は利用者単位(全プロジェクト共通)なので、プロジェクトのURLの下に置かない。
"""

import sqlite3

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.api.deps import get_db
from backend.core import user_terms
from backend.core.project_settings import resolve_settings
from backend.engines.asr import prompt as asr_prompt

router = APIRouter(prefix="/api", tags=["user_terms"])


class UserTerm(BaseModel):
    id: int
    term: str
    # 以前どう聞き間違えられたか(次の動画のスキャンで質問にする)
    misrecognitions: list[str]
    # 確認された回数(多いほど優先してWhisperに渡す)
    hits: int
    source: str  # question | manual | glossary
    created_at: str
    updated_at: str
    # 次の文字起こしでWhisperに渡るか(上限で溢れた語・辞書を使わない設定ならfalse)
    used_for_asr: bool


class UserTermCreate(BaseModel):
    term: str
    misrecognitions: list[str] = []


class UserTermUpdate(BaseModel):
    term: str | None = None
    misrecognitions: list[str] | None = None


def _with_usage(rows: list[dict]) -> list[UserTerm]:
    """グローバル設定で文字起こしたときに、どの語がWhisperに渡るかを添える。

    プロジェクト単位で辞書を切っている場合はそのプロジェクトでは渡らないが、
    この一覧は全体の辞書なのでグローバル設定で判断する。
    """
    s = resolve_settings()
    used: set[str] = set()
    if s.asr_use_user_terms:
        used = set(asr_prompt.select_prompt_terms(
            [r["term"] for r in rows],
            asr_prompt.VERBATIM_STYLE if s.asr_verbatim_style else None,
        ))
    return [UserTerm(**r, used_for_asr=r["term"] in used) for r in rows]


def _one(db: sqlite3.Connection, term_id: int) -> UserTerm:
    for t in _with_usage(user_terms.list_terms(db)):
        if t.id == term_id:
            return t
    raise HTTPException(404, "辞書に見つかりません")


@router.get("/user-terms", response_model=list[UserTerm])
def list_user_terms(db: sqlite3.Connection = Depends(get_db)):
    return _with_usage(user_terms.list_terms(db))


@router.post("/user-terms", response_model=UserTerm)
def create_user_term(body: UserTermCreate, db: sqlite3.Connection = Depends(get_db)):
    """語を足す。すでにあれば1件にまとめる(確認回数を足す)"""
    try:
        row = user_terms.add_term(db, body.term, body.misrecognitions, source="manual")
    except user_terms.InvalidTermError as e:
        raise HTTPException(400, str(e))
    return _one(db, row["id"])


@router.patch("/user-terms/{term_id}", response_model=UserTerm)
def update_user_term(
    term_id: int, body: UserTermUpdate, db: sqlite3.Connection = Depends(get_db)
):
    try:
        user_terms.update_term(db, term_id, body.term, body.misrecognitions)
    except KeyError:
        raise HTTPException(404, "辞書に見つかりません")
    except user_terms.InvalidTermError as e:
        raise HTTPException(400, str(e))
    except user_terms.DuplicateTermError as e:
        raise HTTPException(409, str(e))
    return _one(db, term_id)


@router.delete("/user-terms/{term_id}")
def delete_user_term(term_id: int, db: sqlite3.Connection = Depends(get_db)) -> dict:
    if not user_terms.delete_term(db, term_id):
        raise HTTPException(404, "辞書に見つかりません")
    return {"deleted": term_id}
