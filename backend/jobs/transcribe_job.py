"""文字起こしジョブ: デコード → 話者分離 → ASR → セグメント保存。

M1で移植したモジュールを繋ぐだけの層。処理内容はtranscribe.py CLIと同じ。
"""

import json
import sqlite3
from pathlib import Path
from typing import Callable

from backend.core.project_settings import resolve_settings
from backend.engines.asr.registry import build_engine
from backend.engines.diarize import labels as diarize_labels
from backend.engines.diarize import registry as diarize
from backend.jobs.queue import register
from backend.pipeline import audio as audio_io
from backend.pipeline import filler as filler_mod
from backend.pipeline.aizuchi import is_aizuchi

# 進捗の配分: 話者分離40% + 文字起こし55% + 保存5%
# 進捗には工程名も添える。ずっと「文字起こし中」だと、先に走る話者分離が
# 止まっているように見える(実際にそう見えていた)
DECODE_SHARE = 0.05
DIARIZE_SHARE = 0.4
ASR_SHARE = 0.55


@register("transcribe")
def run_transcribe(
    conn: sqlite3.Connection,
    media_id: int,
    params: dict,
    progress: Callable[[float], None],
) -> None:
    row = conn.execute("SELECT path FROM media WHERE id=?", (media_id,)).fetchone()
    if row is None:
        raise ValueError(f"media {media_id} が見つかりません")

    s = resolve_settings(conn, media_id=media_id)
    language = params.get("language", s.asr_language)
    # 長尺のデコードや初回のモデルDL中に0%のまま見えないよう、開始を即時通知する
    progress(0.01, "音声を読み込み中")
    audio = audio_io.decode(Path(row["path"]))
    progress(DECODE_SHARE)

    # ---- 話者分離 ----
    turns: list = []
    label_map: dict[str, str] = {}
    if s.diarization_enabled:
        progress(DECODE_SHARE, "話者分離中")
        turns, _engine = diarize.run_diarization(
            audio, s,
            # 5%(デコード後)〜40%を話者分離の実進捗で埋める
            progress=lambda p: progress(
                DECODE_SHARE + p * (DIARIZE_SHARE - DECODE_SHARE)
            ),
        )
        if turns:
            label_map = diarize_labels.build_label_map(
                audio, turns,
                male_name=s.male_name,
                female_name=s.female_name,
                log=lambda *_: None,
            )
    progress(DIARIZE_SHARE, "文字起こし中")

    # ---- 文字起こし ----
    # initial_prompt: フィラーを含む文体例を与えるとWhisperが言い淀みを忠実に転写する。
    # 用語集の語も併せて渡し、固有名詞の認識精度を上げる(量子化段階の工夫)
    project_id = conn.execute(
        "SELECT project_id FROM media WHERE id=?", (media_id,)
    ).fetchone()["project_id"]
    terms = [r["term"] for r in conn.execute(
        "SELECT term FROM glossary WHERE project_id=?", (project_id,)
    )]
    prompt_parts = []
    if s.asr_verbatim_style:
        prompt_parts.append("えーと、あのー、そのー、なんか、うん。")
    if terms:
        prompt_parts.append("、".join(terms[:30]) + "。")
    initial_prompt = " ".join(prompt_parts) or None

    engine = build_engine(s)
    try:
        result = engine.transcribe(
            audio,
            language=language,
            progress=lambda p: progress(DIARIZE_SHARE + p * ASR_SHARE),
            initial_prompt=initial_prompt,
        )
    finally:
        engine.unload()

    # ---- 保存(再実行時は作り直す) ----
    progress(DIARIZE_SHARE + ASR_SHARE, "保存中")
    conn.execute("DELETE FROM segments WHERE media_id=?", (media_id,))
    rows = []
    for idx, seg in enumerate(result.segments):
        speaker_label = diarize_labels.assign_speaker(seg, turns) if turns else None
        words = [
            {"start": w.start, "end": w.end, "text": w.text, "probability": w.probability}
            for w in (seg.words or [])
        ]
        # Whisper段階のフィラー一次判定(音響+表記シグナル)をメタデータとして保存
        filler_candidates = filler_mod.analyze_line(seg.text, words)
        rows.append((
            media_id, idx, seg.start, seg.end, seg.text, seg.text,
            label_map.get(speaker_label, speaker_label),
            int(is_aizuchi(seg.text, seg.end - seg.start, s.aizuchi_max_duration)),
            seg.confidence,
            json.dumps(words, ensure_ascii=False),
            json.dumps(filler_candidates, ensure_ascii=False) if filler_candidates else None,
        ))
    conn.executemany(
        "INSERT INTO segments (media_id, idx, start, end, text, original_text,"
        " speaker, is_aizuchi, asr_confidence, words_json, filler_candidates_json)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        rows,
    )
    conn.execute("UPDATE media SET status='transcribed' WHERE id=?", (media_id,))
    conn.commit()
    progress(1.0)
