"""書き出しジョブ: クリップ範囲の切り出し+字幕焼き込み。

字幕は現在のセグメント状態(指示語置換・採用ジャッジ・フィラー除去)を反映して
ASSを生成し、libassで焼き込む。出力は exports/ ディレクトリ。
"""

import json
import sqlite3
from pathlib import Path
from typing import Callable

from backend.core.config import settings
from backend.jobs.filler_job import filler_words_by_segment
from backend.jobs.queue import register
from backend.pipeline import export as export_mod
from backend.pipeline import filler as filler_mod
from backend.pipeline import subtitle as subtitle_mod


@register("export")
def run_export_job(
    conn: sqlite3.Connection,
    media_id: int,
    params: dict,
    progress: Callable[[float], None],
) -> None:
    media = conn.execute("SELECT * FROM media WHERE id=?", (media_id,)).fetchone()
    if media is None:
        raise ValueError(f"media {media_id} が見つかりません")

    input_path = Path(media["path"])
    start = float(params.get("start", 0.0))
    end = float(params.get("end", media["duration"] or 0.0))
    if end <= start:
        raise ValueError("endはstartより大きい必要があります")
    burn = bool(params.get("burn_subtitles", True))

    # クリップ相対時刻の中抜き区間(絶対時刻で来るのでオフセットする)
    cuts = [
        (max(0.0, c["start"] - start), min(end, c["end"]) - start)
        for c in params.get("cuts", [])
        if c["end"] > start and c["start"] < end
    ]

    out_dir = input_path.parent / "exports"
    out_dir.mkdir(exist_ok=True)
    base = input_path.stem
    suffix = f"_clip{params['clip_id']}" if params.get("clip_id") else ""
    out_path = out_dir / f"{base}_{int(start)}s-{int(end)}s{suffix}.mp4"

    # ---- 字幕(ASS)生成 ----
    ass_path = None
    if burn:
        segments = [dict(r) for r in conn.execute(
            "SELECT * FROM segments WHERE media_id=? ORDER BY idx", (media_id,)
        )]
        filler_words = filler_words_by_segment(conn, media_id)
        for s in segments:
            text = s["text"]
            # 適用済みフィラー編集(LLM/質問回答)を除去
            for w in filler_words.get(s["id"], []):
                text = filler_mod.remove_filler(text, w)
            # 安全群フィラーは弱モード以上なら常時除去
            if settings.filler_level in ("weak", "strong"):
                text = filler_mod.remove_fillers_weak(text)
            s["text"] = text

        style = subtitle_mod.SubtitleStyle(
            max_chars_per_line=settings.subtitle_max_chars_per_line,
        )
        events = subtitle_mod.segments_to_events(segments, clip_start=start, clip_end=end)
        ass_path = out_dir / f"{base}_{int(start)}s-{int(end)}s.ass"
        ass_path.write_text(subtitle_mod.build_ass(events, style), encoding="utf-8")

    progress(0.05)

    # ---- ffmpeg実行 ----
    cmd = export_mod.build_export_cmd(input_path, out_path, start, end, ass_path, cuts=cuts)
    export_mod.run_export(cmd, duration=end - start, progress=lambda p: progress(0.05 + p * 0.94))

    conn.execute(
        "UPDATE jobs SET result_json=? WHERE media_id=? AND type='export'"
        " AND status='running'",
        (json.dumps({"path": str(out_path)}, ensure_ascii=False), media_id),
    )
    if params.get("clip_id"):
        conn.execute(
            "UPDATE clips SET status='exported' WHERE id=?", (params["clip_id"],)
        )
    conn.commit()
    progress(1.0)
