"""セグメント(文字起こし結果)の取得・編集API。

original_text は常に原文のまま残す。本文(text)の手直し・取り消し・話者名の変更は
すべてここを通る。本文の組み立ては pipeline/segment_text.py(純関数)に置く。
"""

import json
import sqlite3

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.api.deps import get_db
from backend.core.project_settings import resolve_settings
from backend.models.dto import Segment, SegmentUpdate, Word
from backend.pipeline.segment_text import AppliedEdit, rebuild_text, validate_speaker_name

router = APIRouter(prefix="/api", tags=["transcripts"])

SUBTITLE_SHOW_VALUES = {"auto_show", "auto_hide", "user_show", "user_hide"}


class SpeakerRename(BaseModel):
    current: str
    new: str


class SpeakerRenameResult(BaseModel):
    changed: int


def _to_segment(row: sqlite3.Row) -> Segment:
    d = dict(row)
    words = json.loads(d.pop("words_json") or "[]")
    d.pop("subtitle_reasons_json", None)
    return Segment(**d, words=[Word(**w) for w in words])


def _get_segment(db: sqlite3.Connection, segment_id: int) -> sqlite3.Row:
    row = db.execute("SELECT * FROM segments WHERE id=?", (segment_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "セグメントが見つかりません")
    return row


def load_applied_edits(db: sqlite3.Connection, segment_id: int) -> list[AppliedEdit]:
    """その行に適用済みの編集(古い順)"""
    return [
        AppliedEdit(
            id=r["id"], kind=r["kind"], original=r["original"],
            replacement=r["replacement"], referent=r["referent"] or "",
        )
        for r in db.execute(
            "SELECT * FROM edits WHERE segment_id=? AND status='applied' ORDER BY id",
            (segment_id,),
        )
    ]


def automatic_text(db: sqlite3.Connection, seg: sqlite3.Row) -> tuple[str, list[int]]:
    """手直しが無かった場合の本文(原文+適用済みの編集)と、当てられなかった編集のid"""
    s = resolve_settings(db, media_id=seg["media_id"])
    return rebuild_text(
        seg["original_text"], load_applied_edits(db, seg["id"]), form=s.pronoun_form
    )


def _check_speaker_name(name: str) -> str:
    error = validate_speaker_name(name)
    if error:
        raise HTTPException(400, error)
    return name.strip()


@router.get("/media/{media_id}/segments", response_model=list[Segment])
def list_segments(
    media_id: int,
    include_aizuchi: bool = True,
    db: sqlite3.Connection = Depends(get_db),
):
    sql = "SELECT * FROM segments WHERE media_id=?"
    if not include_aizuchi:
        sql += " AND is_aizuchi=0"
    rows = db.execute(sql + " ORDER BY idx", (media_id,)).fetchall()
    return [_to_segment(r) for r in rows]


@router.patch("/segments/{segment_id}", response_model=Segment)
def update_segment(
    segment_id: int, body: SegmentUpdate, db: sqlite3.Connection = Depends(get_db)
):
    row = _get_segment(db, segment_id)

    fields: dict = {}
    if body.text is not None:
        if not body.text.strip():
            raise HTTPException(400, "本文を空にはできません")
        fields["text"] = body.text
        # 上流の再実行(指示語の解決など)から手直しを守る印。直した結果が
        # 「手直しが無かった場合の本文」と同じなら手直しではない。
        # 話者の付け替えや字幕の表示切替は本文の手直しではないので印を付けない
        fields["edited_by_user"] = int(body.text != automatic_text(db, row)[0])
    if body.speaker is not None:
        fields["speaker"] = _check_speaker_name(body.speaker)
    if body.subtitle_show is not None:
        if body.subtitle_show not in SUBTITLE_SHOW_VALUES:
            raise HTTPException(400, f"不正な subtitle_show: {body.subtitle_show}")
        fields["subtitle_show"] = body.subtitle_show
    if not fields:
        return _to_segment(row)

    sets = ", ".join(f"{k}=?" for k in fields)
    db.execute(f"UPDATE segments SET {sets} WHERE id=?", (*fields.values(), segment_id))
    db.commit()
    return _to_segment(_get_segment(db, segment_id))


@router.post("/segments/{segment_id}/restore", response_model=Segment)
def restore_segment(segment_id: int, db: sqlite3.Connection = Depends(get_db)):
    """手直しを取り消す。原文に、承認済みのAIの修正だけを当てた本文に戻す。

    手直しした文に対して承認した編集は、原文には当てる場所が無いので取り消し扱いにする
    (適用済みのまま残すと、レビュー画面の表示と本文が食い違う)。
    """
    row = _get_segment(db, segment_id)
    text, dropped = automatic_text(db, row)
    for edit_id in dropped:
        db.execute("UPDATE edits SET status='reverted' WHERE id=?", (edit_id,))
    db.execute(
        "UPDATE segments SET text=?, edited_by_user=0 WHERE id=?", (text, segment_id)
    )
    db.commit()
    return _to_segment(_get_segment(db, segment_id))


@router.post("/media/{media_id}/speakers/rename", response_model=SpeakerRenameResult)
def rename_speaker(
    media_id: int, body: SpeakerRename, db: sqlite3.Connection = Depends(get_db)
):
    """この動画の話者名を変える(その話者の全行)。

    話者名は文字起こしのときに行ごとに付く(segments.speaker)ので、変える単位は動画。
    既にいる別の話者の名前にはしない。2人が混ざると元に戻せなくなるため
    (同じ人だったなら、行ごとの付け替えを使う)。
    """
    new = _check_speaker_name(body.new)
    names = {
        r["speaker"] for r in db.execute(
            "SELECT DISTINCT speaker FROM segments WHERE media_id=? AND speaker IS NOT NULL",
            (media_id,),
        )
    }
    if body.current not in names:
        raise HTTPException(404, f"この動画に「{body.current}」という話者はいません")
    if new == body.current:
        return SpeakerRenameResult(changed=0)
    if new in names:
        raise HTTPException(
            400,
            f"「{new}」はすでにこの動画にいる話者です。同じ人なら、行ごとに話者を付け替えてください",
        )
    cur = db.execute(
        "UPDATE segments SET speaker=? WHERE media_id=? AND speaker=?",
        (new, media_id, body.current),
    )
    db.commit()
    return SpeakerRenameResult(changed=cur.rowcount)
