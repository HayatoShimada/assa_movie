"""切り抜き候補の生成ジョブとクリップ関連ジョブ。"""

import json
import sqlite3
from typing import Callable

from backend.core.config import settings
from backend.jobs.queue import register
from backend.jobs.resolve_job import _get_client, _load_prompt_parts
from backend.pipeline import attention as att

CHUNK_LINES = 250  # 一度にLLMへ渡す行数(長尺は重なり付きで分割)
OVERLAP = 30


@register("attention")
def run_attention(
    conn: sqlite3.Connection,
    media_id: int,
    params: dict,
    progress: Callable[[float], None],
) -> None:
    target_duration = params.get("target_duration")
    rows = [dict(r) for r in conn.execute(
        "SELECT id, idx, start, end, text, speaker, is_aizuchi FROM segments"
        " WHERE media_id=? ORDER BY idx", (media_id,)
    )]
    speech = [r for r in rows if not r["is_aizuchi"]]
    if not speech:
        progress(1.0)
        return

    # 概要(ブリーフ)があれば候補選定の文脈として渡す
    parts = _load_prompt_parts(conn, media_id, settings.pronoun_level)
    system = att.build_attention_prompt(target_duration)
    if parts.brief:
        system += f"\n\nこの動画の概要(ユーザー提供):\n{parts.brief}"

    client = _get_client()
    lines = [f"{i + 1}: [{r['speaker'] or '?'}] {r['text']}" for i, r in enumerate(speech)]

    raw_candidates = []
    starts = list(range(0, len(lines), CHUNK_LINES - OVERLAP))
    for n, s in enumerate(starts):
        chunk = lines[s:s + CHUNK_LINES]
        payload = client.complete_json(system, "\n".join(chunk), att.ATTENTION_SCHEMA)
        for c in payload.get("candidates", []) or []:
            raw_candidates.append(c)
        progress(min(0.8, (n + 1) / len(starts) * 0.8))

    # ---- 行番号→時刻に変換し、機械特徴と合成 ----
    conn.execute("DELETE FROM clips WHERE media_id=? AND status='suggested'", (media_id,))
    seen_ranges: list[tuple[float, float]] = []
    inserted = 0
    for c in raw_candidates:
        try:
            i0 = max(1, int(c["start_line"])) - 1
            i1 = min(len(speech), int(c["end_line"])) - 1
        except (TypeError, ValueError, KeyError):
            continue
        if i1 <= i0:
            continue
        start, end = speech[i0]["start"], speech[i1]["end"]
        # 既出候補と大きく重なるものは捨てる(チャンク重なり由来の重複対策)
        if any(min(end, e) - max(start, s) > 0.6 * (end - start) for s, e in seen_ranges):
            continue

        features = att.clip_features(rows, start, end)
        score, mech_reasons = att.combined_score(
            float(c.get("score", 5)), features, target_duration
        )
        reasons = list(dict.fromkeys([*(c.get("reasons") or []), *mech_reasons]))[:5]
        conn.execute(
            "INSERT INTO clips (media_id, start, end, title, hook_text, score,"
            " score_reasons_json, target_duration, status)"
            " VALUES (?,?,?,?,?,?,?,?,'suggested')",
            (media_id, start, end, str(c.get("title", ""))[:60],
             str(c.get("hook", ""))[:40], score,
             json.dumps(reasons, ensure_ascii=False), target_duration),
        )
        seen_ranges.append((start, end))
        inserted += 1

    conn.commit()
    progress(1.0)


@register("clip_meta")
def run_clip_meta(
    conn: sqlite3.Connection,
    media_id: int,
    params: dict,
    progress: Callable[[float], None],
) -> None:
    """クリップの投稿用メタ情報(タイトル・フック3案・概要欄・ハッシュタグ)を生成する"""
    clip_id = int(params["clip_id"])
    clip = conn.execute("SELECT * FROM clips WHERE id=?", (clip_id,)).fetchone()
    if clip is None:
        raise ValueError("クリップが見つかりません")

    rows = conn.execute(
        "SELECT text FROM segments WHERE media_id=? AND is_aizuchi=0"
        " AND start < ? AND end > ? ORDER BY idx",
        (media_id, clip["end"], clip["start"]),
    ).fetchall()
    transcript = "\n".join(r["text"] for r in rows)
    progress(0.1)

    parts = _load_prompt_parts(conn, media_id, settings.pronoun_level)
    system = att.META_PROMPT
    if parts.brief:
        system += f"\n\nこの動画の概要(ユーザー提供):\n{parts.brief}"

    payload = _get_client().complete_json(system, transcript, att.META_SCHEMA)
    meta = {
        "title": str(payload.get("title", "")),
        "hooks": [str(h) for h in (payload.get("hooks") or [])][:3],
        "description": str(payload.get("description", "")),
        "hashtags": [str(h) for h in (payload.get("hashtags") or [])][:5],
    }
    conn.execute(
        "UPDATE clips SET meta_json=?, title=COALESCE(NULLIF(title,''), ?),"
        " hook_text=COALESCE(NULLIF(hook_text,''), ?) WHERE id=?",
        (json.dumps(meta, ensure_ascii=False), meta["title"],
         (meta["hooks"] or [""])[0], clip_id),
    )
    conn.commit()
    progress(1.0)
