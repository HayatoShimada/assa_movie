"""クリップ(切り抜き)のCRUD・ジェットカット・自己完結化・書き出し。"""

import json
import shutil
import sqlite3
import subprocess
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.core.project_settings import resolve_settings
from backend.api.deps import get_db, get_jobs
from backend.jobs.queue import JobQueue
from backend.pipeline import export as export_mod
from backend.pipeline.attention import parse_silences
from backend.pipeline.layout import CONVERT_METHODS

router = APIRouter(prefix="/api", tags=["clips"])

# 中抜き提案とみなす無音の最小長(秒)
SILENCE_MIN_DURATION = 0.6
SILENCE_NOISE_DB = -35


def _require_ffmpeg() -> None:
    if shutil.which("ffmpeg") is None:
        raise HTTPException(400, export_mod.FFMPEG_MISSING_MSG)


class Clip(BaseModel):
    id: int
    media_id: int
    start: float
    end: float
    title: str | None = None
    hook_text: str | None = None
    score: float | None = None
    score_reasons: list[str] = []
    subtitle_position: str = "bottom"
    subtitle_offset_y: int = 0
    convert_method: str | None = None  # None=プロジェクト既定(crop|blur_pad|face)
    crop_x: float = 0.5  # crop時の切り出し位置(0..1)
    target_duration: float | None = None
    meta: dict | None = None
    status: str
    cuts: list[dict] = []


class ClipCreate(BaseModel):
    start: float
    end: float
    title: str | None = None


class ClipUpdate(BaseModel):
    start: float | None = None
    end: float | None = None
    title: str | None = None
    hook_text: str | None = None
    subtitle_position: str | None = None
    subtitle_offset_y: int | None = None
    convert_method: str | None = None
    crop_x: float | None = None
    status: str | None = None


def _to_clip(db: sqlite3.Connection, row: sqlite3.Row) -> Clip:
    cuts = [dict(r) for r in db.execute(
        "SELECT id, start, end, source, active FROM clip_cuts WHERE clip_id=? ORDER BY start",
        (row["id"],),
    )]
    return Clip(
        id=row["id"], media_id=row["media_id"], start=row["start"], end=row["end"],
        title=row["title"], hook_text=row["hook_text"], score=row["score"],
        score_reasons=json.loads(row["score_reasons_json"] or "[]"),
        subtitle_position=row["subtitle_position"],
        subtitle_offset_y=row["subtitle_offset_y"],
        convert_method=row["convert_method"], crop_x=row["crop_x"],
        target_duration=row["target_duration"],
        meta=json.loads(row["meta_json"] or "null"),
        status=row["status"], cuts=cuts,
    )


def _get_clip_row(db: sqlite3.Connection, clip_id: int) -> sqlite3.Row:
    row = db.execute("SELECT * FROM clips WHERE id=?", (clip_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "クリップが見つかりません")
    return row


@router.get("/media/{media_id}/clips", response_model=list[Clip])
def list_clips(media_id: int, db: sqlite3.Connection = Depends(get_db)):
    rows = db.execute(
        "SELECT * FROM clips WHERE media_id=? ORDER BY score DESC, id", (media_id,)
    ).fetchall()
    return [_to_clip(db, r) for r in rows]


@router.post("/media/{media_id}/clips", response_model=Clip)
def create_clip(
    media_id: int, body: ClipCreate, db: sqlite3.Connection = Depends(get_db)
):
    if body.end <= body.start:
        raise HTTPException(400, "endはstartより大きい必要があります")
    s = resolve_settings(db, media_id=media_id)
    cur = db.execute(
        "INSERT INTO clips (media_id, start, end, title, subtitle_position, subtitle_offset_y, status)"
        " VALUES (?,?,?,?,?,?,'draft')",
        (
            media_id,
            body.start,
            body.end,
            body.title,
            s.subtitle_position,
            int(s.subtitle_offset_y),
        ),
    )
    db.commit()
    return _to_clip(db, _get_clip_row(db, cur.lastrowid))


@router.patch("/clips/{clip_id}", response_model=Clip)
def update_clip(clip_id: int, body: ClipUpdate, db: sqlite3.Connection = Depends(get_db)):
    row = _get_clip_row(db, clip_id)
    fields = body.model_dump(exclude_none=True)
    if not fields:
        return _to_clip(db, row)
    if "convert_method" in fields and fields["convert_method"] not in CONVERT_METHODS:
        raise HTTPException(400, f"未知の変換方式: {fields['convert_method']}")
    if "crop_x" in fields:
        fields["crop_x"] = max(0.0, min(1.0, float(fields["crop_x"])))
    new_start = fields.get("start", row["start"])
    new_end = fields.get("end", row["end"])
    if new_end <= new_start:
        raise HTTPException(400, "endはstartより大きい必要があります")
    sets = ", ".join(f"{k}=?" for k in fields)
    db.execute(f"UPDATE clips SET {sets} WHERE id=?", (*fields.values(), clip_id))
    # 範囲を変えたら範囲外の中抜きは削除する
    db.execute(
        "DELETE FROM clip_cuts WHERE clip_id=? AND (end <= ? OR start >= ?)",
        (clip_id, new_start, new_end),
    )
    db.commit()
    return _to_clip(db, _get_clip_row(db, clip_id))


@router.delete("/clips/{clip_id}")
def delete_clip(clip_id: int, db: sqlite3.Connection = Depends(get_db)):
    _get_clip_row(db, clip_id)
    db.execute("DELETE FROM clips WHERE id=?", (clip_id,))
    db.commit()
    return {"deleted": clip_id}


@router.post("/clips/{clip_id}/jetcut", response_model=Clip)
def jetcut(clip_id: int, db: sqlite3.Connection = Depends(get_db)):
    """中抜き(ジェットカット)提案: 無音区間(ffmpeg silencedetect)+相槌セグメント"""
    clip = _get_clip_row(db, clip_id)
    media = db.execute("SELECT path FROM media WHERE id=?", (clip["media_id"],)).fetchone()
    db.execute("DELETE FROM clip_cuts WHERE clip_id=? AND source != 'manual'", (clip_id,))

    proposals: list[tuple[float, float, str]] = []

    # 無音検出(ffmpegが無い・失敗した場合は相槌のみで続行)
    if shutil.which("ffmpeg"):
        try:
            out = subprocess.run(
                ["ffmpeg", "-hide_banner", "-nostats",
                 "-ss", str(clip["start"]), "-t", str(clip["end"] - clip["start"]),
                 "-i", media["path"], "-af",
                 f"silencedetect=noise={SILENCE_NOISE_DB}dB:d={SILENCE_MIN_DURATION}",
                 "-f", "null", "-"],
                capture_output=True, text=True, timeout=120,
            )
            for s, e in parse_silences(out.stderr, offset=clip["start"]):
                proposals.append((s, e, "silence"))
        except subprocess.SubprocessError:
            pass

    # 相槌セグメント
    for r in db.execute(
        "SELECT start, end FROM segments WHERE media_id=? AND is_aizuchi=1"
        " AND start >= ? AND end <= ?",
        (clip["media_id"], clip["start"], clip["end"]),
    ):
        proposals.append((r["start"], r["end"], "aizuchi"))

    for s, e, source in proposals:
        s, e = max(s, clip["start"]), min(e, clip["end"])
        if e - s < 0.2:
            continue
        db.execute(
            "INSERT INTO clip_cuts (clip_id, start, end, source, active) VALUES (?,?,?,?,1)",
            (clip_id, round(s, 3), round(e, 3), source),
        )
    db.commit()
    return _to_clip(db, _get_clip_row(db, clip_id))


@router.patch("/clip_cuts/{cut_id}")
def toggle_cut(cut_id: int, active: bool, db: sqlite3.Connection = Depends(get_db)):
    row = db.execute("SELECT * FROM clip_cuts WHERE id=?", (cut_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "中抜き区間が見つかりません")
    db.execute("UPDATE clip_cuts SET active=? WHERE id=?", (int(active), cut_id))
    db.commit()
    return dict(db.execute("SELECT * FROM clip_cuts WHERE id=?", (cut_id,)).fetchone())


class ResolveClipRequest(BaseModel):
    pass


@router.post("/clips/{clip_id}/resolve")
def resolve_clip(
    clip_id: int,
    db: sqlite3.Connection = Depends(get_db),
    jobs: JobQueue = Depends(get_jobs),
):
    """クリップ文脈の指示語自己完結化。切り抜くと前の文脈が消えるため、
    クリップ内だけで意味が通るように指示語を解決する(M4の機構を再利用)"""
    clip = _get_clip_row(db, clip_id)
    seg_ids = [r["id"] for r in db.execute(
        "SELECT id FROM segments WHERE media_id=? AND start < ? AND end > ?",
        (clip["media_id"], clip["end"], clip["start"]),
    )]
    if not seg_ids:
        raise HTTPException(400, "クリップ範囲にセグメントがありません")
    job_id = jobs.enqueue(clip["media_id"], "resolve", {
        "scope": "segment_ids",
        "segment_ids": seg_ids,
        "extra_instruction": (
            "この範囲は切り抜き動画として単体で公開される。範囲より前の文脈は視聴者に"
            "見えないため、範囲内で参照先が示されていない指示語は特に積極的に解決すること。"
        ),
    })
    return {"job_id": job_id, "segment_count": len(seg_ids)}


@router.post("/clips/{clip_id}/export")
def export_clip(
    clip_id: int,
    db: sqlite3.Connection = Depends(get_db),
    jobs: JobQueue = Depends(get_jobs),
):
    """クリップを書き出す(有効な中抜きを反映)"""
    _require_ffmpeg()  # ジョブ投入後に失敗するより先にUIへ伝える
    clip = _get_clip_row(db, clip_id)
    cuts = [
        {"start": r["start"], "end": r["end"]}
        for r in db.execute(
            "SELECT start, end FROM clip_cuts WHERE clip_id=? AND active=1 ORDER BY start",
            (clip_id,),
        )
    ]
    job_id = jobs.enqueue(clip["media_id"], "export", {
        "start": clip["start"], "end": clip["end"],
        "burn_subtitles": True, "cuts": cuts, "clip_id": clip_id,
        "subtitle_position": clip["subtitle_position"],
        "subtitle_offset_y": clip["subtitle_offset_y"],
        "convert_method": clip["convert_method"],  # None=プロジェクト既定
        "crop_x": clip["crop_x"],
    })
    db.execute("UPDATE clips SET status='exporting' WHERE id=?", (clip_id,))
    db.commit()
    return {"job_id": job_id}
