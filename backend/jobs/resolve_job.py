"""指示語置換ジョブ: LLMに提案させ、機械ガードを通ったものだけをeditsに保存する。

LLMは提案するだけで適用判断はしない。適用はレビューAPI(またはauto設定)で行う。
"""

import sqlite3
from typing import Callable

from backend.core.config import Settings
from backend.core.project_settings import resolve_settings
from backend.engines.llm.base import LLMClient
from backend.engines.llm.registry import build_client
from backend.jobs.queue import register
from backend.pipeline import pronoun

# テストからLLMクライアントを差し替えるためのフック
_client_factory: Callable[[], LLMClient] | None = None


def set_client_factory(factory: Callable[[], LLMClient] | None) -> None:
    global _client_factory
    _client_factory = factory


def _get_client(s: Settings | None = None) -> LLMClient:
    """解決済み設定sからLLMクライアントを作る(省略時はグローバル既定)"""
    if _client_factory:
        return _client_factory()
    return build_client(s if s is not None else resolve_settings())


def _load_prompt_parts(conn: sqlite3.Connection, media_id: int, level: str) -> pronoun.PromptParts:
    import json as json_mod

    media = conn.execute(
        "SELECT project_id, brief_json FROM media WHERE id=?", (media_id,)
    ).fetchone()
    project_id = media["project_id"]

    brief_data = json_mod.loads(media["brief_json"] or "{}")
    brief_lines = []
    if brief_data.get("theme"):
        brief_lines.append(f"主題: {brief_data['theme']}")
    if brief_data.get("people"):
        brief_lines.append(f"登場人物: {brief_data['people']}")
    if brief_data.get("notes"):
        brief_lines.append(f"補足: {brief_data['notes']}")

    glossary = [
        dict(r) for r in conn.execute(
            "SELECT term, reading, description FROM glossary WHERE project_id=?", (project_id,)
        )
    ]
    instructions = [
        r["text"] for r in conn.execute(
            "SELECT text FROM llm_instructions WHERE project_id=? AND enabled=1"
            " AND scope IN ('all','pronoun') AND (media_id IS NULL OR media_id=?)"
            " ORDER BY id", (project_id, media_id),
        )
    ]
    feedback = [
        dict(r) for r in conn.execute(
            "SELECT before, after, note FROM feedback WHERE media_id=?"
            " AND kind IN ('rejection','correction') ORDER BY id DESC LIMIT 20", (media_id,)
        )
    ]
    return pronoun.PromptParts(
        level=level, brief="\n".join(brief_lines),
        glossary=glossary, instructions=instructions, feedback=feedback,
    )


def _target_segments(conn: sqlite3.Connection, media_id: int, params: dict) -> list[sqlite3.Row]:
    """再実行の範囲を決める。承認済みの編集がある行はそのまま残る(editsを消さないため)。"""
    scope = params.get("scope", "all")
    if scope == "segment_ids":
        ids = params.get("segment_ids") or []
        if not ids:
            return []
        marks = ",".join("?" * len(ids))
        return conn.execute(
            f"SELECT * FROM segments WHERE media_id=? AND id IN ({marks}) ORDER BY idx",
            (media_id, *ids),
        ).fetchall()
    if scope == "unresolved":
        # まだ編集提案が付いていないセグメントだけを対象にする
        return conn.execute(
            "SELECT * FROM segments s WHERE s.media_id=? AND NOT EXISTS ("
            "  SELECT 1 FROM edits e WHERE e.segment_id=s.id AND e.kind='pronoun'"
            "    AND e.status IN ('proposed','applied')"
            ") ORDER BY s.idx",
            (media_id,),
        ).fetchall()
    return conn.execute(
        "SELECT * FROM segments WHERE media_id=? ORDER BY idx", (media_id,)
    ).fetchall()


@register("resolve")
def run_resolve(
    conn: sqlite3.Connection,
    media_id: int,
    params: dict,
    progress: Callable[[float], None],
) -> None:
    s = resolve_settings(conn, media_id=media_id)
    level = params.get("level", s.pronoun_level)
    form = params.get("form", s.pronoun_form)
    apply_mode = params.get("apply_mode", s.pronoun_apply_mode)
    chunk_size = params.get("chunk_size", s.llm_chunk_size)

    segments = _target_segments(conn, media_id, params)
    if not segments:
        progress(1.0)
        return

    # プロンプトの行番号は「全セグメント中の位置」に揃える(文脈が正しく引けるように)
    all_rows = conn.execute(
        "SELECT id, text FROM segments WHERE media_id=? ORDER BY idx", (media_id,)
    ).fetchall()
    lines = [r["text"] for r in all_rows]
    id_by_line = {i + 1: r["id"] for i, r in enumerate(all_rows)}
    line_by_id = {r["id"]: i + 1 for i, r in enumerate(all_rows)}

    target_lines = sorted(line_by_id[seg["id"]] for seg in segments)
    client = _get_client(s)
    parts = _load_prompt_parts(conn, media_id, level)
    # クリップの自己完結化など、この実行だけの追加指示
    if params.get("extra_instruction"):
        parts.instructions = [*parts.instructions, str(params["extra_instruction"])]
    system = pronoun.build_system_prompt(parts)

    proposals: list[tuple[pronoun.EditProposal, int]] = []
    chunks = [target_lines[i:i + chunk_size] for i in range(0, len(target_lines), chunk_size)]

    for n, chunk in enumerate(chunks):
        user = pronoun.build_user_prompt(lines, chunk, s.llm_context_size)
        payload = client.complete_json(system, user, pronoun.EDITS_SCHEMA)
        for edit in pronoun.parse_edits(payload):
            proposals.append((edit, (chunk[0], chunk[-1])))
        progress(min((n + 1) / len(chunks) * 0.9, 0.9))

    # ---- 機械ガード → 保存 ----
    accepted = 0
    for raw_edit, line_range in proposals:
        segment_id = id_by_line.get(raw_edit.line)
        if segment_id is None:
            continue
        # 置換先が指示語のまま(「これ→そのこと」)なら referent で補正、不能なら却下
        edit = pronoun.normalize_edit(raw_edit)
        if edit is None:
            conn.execute(
                "INSERT INTO feedback (media_id, kind, before, after, note)"
                " VALUES (?,'rejection',?,?,?)",
                (media_id, raw_edit.original, raw_edit.replacement,
                 "機械ガード: 参照先が指示語のまま具体的でない"),
            )
            continue
        line_text = lines[edit.line - 1]
        v = pronoun.validate_edit(edit, line_text, level=level, line_range=line_range)
        if not v.ok:
            # 却下理由をfeedbackに残し、次回のfew-shotに使う
            conn.execute(
                "INSERT INTO feedback (media_id, kind, before, after, note)"
                " VALUES (?,'rejection',?,?,?)",
                (media_id, edit.original, edit.replacement, f"機械ガード: {v.reason}"),
            )
            continue

        auto = edit.confidence == "auto"
        status = "proposed"
        if apply_mode == "full_auto" or (apply_mode == "auto_and_review" and auto):
            new_text = pronoun.apply_edit(line_text, edit, form=form)
            conn.execute(
                "UPDATE segments SET text=? WHERE id=? AND edited_by_user=0",
                (new_text, segment_id),
            )
            status = "applied"
        conn.execute(
            "INSERT INTO edits (media_id, segment_id, kind, original, replacement,"
            " referent, status, confidence, created_by)"
            " VALUES (?,?,'pronoun',?,?,?,?,?, 'llm')",
            (media_id, segment_id, edit.original, edit.replacement,
             edit.referent, status, edit.confidence),
        )
        accepted += 1

    conn.commit()
    progress(1.0)
