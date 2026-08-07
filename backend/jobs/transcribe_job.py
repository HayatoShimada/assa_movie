"""文字起こしジョブ: デコード → 話者分離 → ASR → セグメント保存。

M1で移植したモジュールを繋ぐだけの層。処理内容はtranscribe.py CLIと同じ。
"""

import json
import sqlite3
from pathlib import Path
from typing import Callable

from backend.core.config import settings
from backend.engines.asr.registry import build_engine
from backend.engines.diarize import pyannote as diarize
from backend.jobs.queue import register
from backend.pipeline import audio as audio_io
from backend.pipeline import filler as filler_mod
from backend.pipeline.aizuchi import is_aizuchi

# 進捗の配分: 話者分離40% + 文字起こし55% + 保存5%
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

    language = params.get("language", settings.asr_language)
    audio = audio_io.decode(Path(row["path"]))
    progress(0.05)

    # ---- 話者分離 ----
    turns: list = []
    label_map: dict[str, str] = {}
    if settings.diarization_enabled:
        token = diarize.load_hf_token(settings.hf_token_file)
        if token:
            turns = diarize.run_diarization(
                audio, token,
                model=settings.diarization_model,
                num_speakers=settings.num_speakers,
            )
            label_map = diarize.build_label_map(
                audio, turns,
                male_name=settings.male_name,
                female_name=settings.female_name,
                log=lambda *_: None,
            )
    progress(DIARIZE_SHARE)

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
    if settings.asr_verbatim_style:
        prompt_parts.append("えーと、あのー、そのー、なんか、うん。")
    if terms:
        prompt_parts.append("、".join(terms[:30]) + "。")
    initial_prompt = " ".join(prompt_parts) or None

    engine = build_engine(settings)
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
    conn.execute("DELETE FROM segments WHERE media_id=?", (media_id,))
    rows = []
    for idx, seg in enumerate(result.segments):
        speaker_label = diarize.assign_speaker(seg, turns) if turns else None
        words = [
            {"start": w.start, "end": w.end, "text": w.text, "probability": w.probability}
            for w in (seg.words or [])
        ]
        # Whisper段階のフィラー一次判定(音響+表記シグナル)をメタデータとして保存
        filler_candidates = filler_mod.analyze_line(seg.text, words)
        rows.append((
            media_id, idx, seg.start, seg.end, seg.text, seg.text,
            label_map.get(speaker_label, speaker_label),
            int(is_aizuchi(seg.text, seg.end - seg.start, settings.aizuchi_max_duration)),
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
