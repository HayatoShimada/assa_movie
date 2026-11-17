"""プレビュー用の字幕(書き出しと同じ libass で描いた透過画像)のAPI。

時刻表(いつ・どの画像を出すか)と画像の2つ。時刻表は書き出しと同じ関数
(backend/jobs/export_job.py の subtitle_events / subtitle_style)で作るので、
フィラー除去・表示時間の延長・話者の色・位置まで書き出しと同じになる。
"""

import sqlite3

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from backend.api.deps import get_db
from backend.core.ffmpeg import ffmpeg_path, missing_message
from backend.core.project_settings import resolve_settings
from backend.jobs.export_job import output_size, subtitle_events, subtitle_style
from backend.pipeline import subtitle_preview

router = APIRouter(prefix="/api", tags=["preview"])


class SubtitlePreviewEvent(BaseModel):
    # 元動画の絶対時刻(秒)
    start: float
    end: float
    # 画像の識別子。/api/media/{id}/subtitle-preview/{key}.png で取れる
    key: str
    # 折り返し済みの文(画像の代替文字)
    text: str


class SubtitlePreview(BaseModel):
    # 画像を描けるか(ffmpegが無いと描けない)
    available: bool
    # 描けない理由と直し方
    reason: str = ""
    # 書き出される動画の解像度(画像もこの大きさ)
    width: int
    height: int
    events: list[SubtitlePreviewEvent]


def _plan(
    db: sqlite3.Connection,
    media_id: int,
    position: str | None,
    offset_y: int | None,
    start: float | None,
    end: float | None,
):
    media = db.execute("SELECT * FROM media WHERE id=?", (media_id,)).fetchone()
    if media is None:
        raise HTTPException(404, "メディアが見つかりません")
    if position not in (None, "top", "center", "bottom"):
        raise HTTPException(400, f"字幕の位置が正しくありません: {position}")
    s = resolve_settings(db, media_id=media_id)
    width, height = output_size(db, media)
    params = {"subtitle_position": position, "subtitle_offset_y": offset_y}
    clip_start = float(start or 0.0)
    events = subtitle_events(db, media_id, s, clip_start, end)
    timeline, jobs = subtitle_preview.plan(
        events, subtitle_style(s, params, width, height), clip_start
    )
    return timeline, jobs, width, height


@router.get("/media/{media_id}/subtitle-preview", response_model=SubtitlePreview)
def get_subtitle_preview(
    media_id: int,
    position: str | None = None,
    offset_y: int | None = None,
    start: float | None = None,
    end: float | None = None,
    db: sqlite3.Connection = Depends(get_db),
) -> SubtitlePreview:
    """プレビューに出す字幕の時刻表。

    position / offset_y: クリップの字幕位置(省略時は設定の値。書き出しと同じ規則)。
    start / end: クリップの範囲。話者の色は「書き出す範囲に出てくる話者」に
    順に割り当てるので、範囲が違うと色が変わる。クリップを見ているときは渡す。
    """
    timeline, jobs, width, height = _plan(db, media_id, position, offset_y, start, end)
    subtitle_preview.cache.register(jobs)
    available = ffmpeg_path() is not None
    return SubtitlePreview(
        available=available,
        reason="" if available else f"字幕のプレビューには ffmpeg が必要です。{missing_message()}",
        width=width,
        height=height,
        events=[SubtitlePreviewEvent(**e.__dict__) for e in timeline],
    )


@router.get("/media/{media_id}/subtitle-preview/{key}.png")
def get_subtitle_preview_image(
    media_id: int,
    key: str,
    position: str | None = None,
    offset_y: int | None = None,
    start: float | None = None,
    end: float | None = None,
    db: sqlite3.Connection = Depends(get_db),
) -> Response:
    """字幕1件の透過画像(書き出しの解像度)。

    キーは見た目から決まるので、同じキーの画像は変わらない(長くキャッシュさせる)。
    アプリを再起動して材料を忘れていたら、同じ条件で時刻表を作り直して探す。
    """
    if not subtitle_preview.cache.knows(key):
        _, jobs, _, _ = _plan(db, media_id, position, offset_y, start, end)
        subtitle_preview.cache.register(jobs)
    try:
        png = subtitle_preview.cache.image(key)
    except (RuntimeError, OSError) as e:
        raise HTTPException(503, str(e))
    if png is None:
        raise HTTPException(404, "この字幕はもうありません(文字起こしか設定が変わりました)")
    return Response(
        png, media_type="image/png",
        headers={"Cache-Control": "private, max-age=31536000, immutable"},
    )
