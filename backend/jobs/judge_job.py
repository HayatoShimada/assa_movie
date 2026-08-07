"""字幕採用ジャッジジョブ: 選択字幕モードの採用/非採用を決める。

ユーザーが手動で切り替えた行(user_show/user_hide)は常に保護する。
切替はfeedbackに蓄積され、将来の再ジャッジのfew-shotに使える。
"""

import json
import sqlite3
from typing import Callable

from backend.core.config import settings
from backend.jobs.queue import register
from backend.jobs.resolve_job import _get_client
from backend.pipeline import judge as judge_mod


@register("judge_subtitles")
def run_judge(
    conn: sqlite3.Connection,
    media_id: int,
    params: dict,
    progress: Callable[[float], None],
) -> None:
    rate = float(params.get("rate", settings.subtitle_adoption_rate))
    use_llm = bool(params.get("use_llm", True))

    rows = conn.execute(
        "SELECT id, idx, text, start, end, asr_confidence, subtitle_show FROM segments"
        " WHERE media_id=? AND is_aizuchi=0 ORDER BY idx", (media_id,)
    ).fetchall()
    if not rows:
        progress(1.0)
        return

    project_id = conn.execute(
        "SELECT project_id FROM media WHERE id=?", (media_id,)
    ).fetchone()["project_id"]
    terms = [r["term"] for r in conn.execute(
        "SELECT term FROM glossary WHERE project_id=?", (project_id,)
    )]

    # ---- LLMによる重要行の判定(任意) ----
    important: set[int] = set()
    if use_llm:
        client = _get_client()
        lines = [f"{i + 1}: {r['text']}" for i, r in enumerate(rows)]
        chunk = 150
        for n in range(0, len(lines), chunk):
            payload = client.complete_json(
                judge_mod.IMPORTANCE_PROMPT,
                "\n".join(lines[n:n + chunk]),
                judge_mod.IMPORTANCE_SCHEMA,
            )
            for ln in payload.get("important_lines", []) or []:
                if isinstance(ln, int) and 1 <= ln <= len(rows):
                    important.add(rows[ln - 1]["idx"])
            progress(min(0.7, (n + chunk) / len(lines) * 0.7))

    # ---- 機械シグナルとの合成 → 採用決定 ----
    inputs = [
        judge_mod.JudgeInput(
            idx=r["idx"],
            text=r["text"],
            duration=max(r["end"] - r["start"], 0.01),
            confidence=r["asr_confidence"],
            has_term=any(t in r["text"] for t in terms),
            llm_important=r["idx"] in important,
        )
        for r in rows
    ]
    selected = judge_mod.select_subtitles(inputs, rate)

    for r in rows:
        if r["subtitle_show"].startswith("user_"):
            continue  # ユーザーの手動切替は常に優先
        show = "auto_show" if r["idx"] in selected else "auto_hide"
        reasons = []
        inp = next(i for i in inputs if i.idx == r["idx"])
        if inp.confidence is not None and inp.confidence < -0.5:
            reasons.append("聞き取りにくい")
        if inp.has_term:
            reasons.append("固有名詞")
        if inp.llm_important:
            reasons.append("重要な発言")
        conn.execute(
            "UPDATE segments SET subtitle_show=?, subtitle_reasons_json=? WHERE id=?",
            (show, json.dumps(reasons, ensure_ascii=False), r["id"]),
        )

    conn.commit()
    progress(1.0)
