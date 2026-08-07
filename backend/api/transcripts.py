"""セグメント(文字起こし結果)の取得・編集API。"""

import json
import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from backend.api.deps import get_db
from backend.models.dto import Segment, SegmentUpdate, Word

router = APIRouter(prefix="/api", tags=["transcripts"])

SUBTITLE_SHOW_VALUES = {"auto_show", "auto_hide", "user_show", "user_hide"}


def _to_segment(row: sqlite3.Row) -> Segment:
    d = dict(row)
    words = json.loads(d.pop("words_json") or "[]")
    d.pop("subtitle_reasons_json", None)
    return Segment(**d, words=[Word(**w) for w in words])


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
    row = db.execute("SELECT * FROM segments WHERE id=?", (segment_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "セグメントが見つかりません")

    fields: dict = {}
    if body.text is not None:
        fields["text"] = body.text
    if body.speaker is not None:
        fields["speaker"] = body.speaker
    if body.subtitle_show is not None:
        if body.subtitle_show not in SUBTITLE_SHOW_VALUES:
            raise HTTPException(400, f"不正な subtitle_show: {body.subtitle_show}")
        fields["subtitle_show"] = body.subtitle_show
    if not fields:
        return _to_segment(row)

    fields["edited_by_user"] = 1  # 上流の再実行時に手動編集を保護するための印
    sets = ", ".join(f"{k}=?" for k in fields)
    db.execute(f"UPDATE segments SET {sets} WHERE id=?", (*fields.values(), segment_id))
    db.commit()
    return _to_segment(db.execute("SELECT * FROM segments WHERE id=?", (segment_id,)).fetchone())
