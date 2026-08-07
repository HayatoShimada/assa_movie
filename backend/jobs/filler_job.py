"""フィラー排除ジョブ。

Whisper段階の一次判定(segments.filler_candidates_json)を消費する2段構成:
  - weak : 'filler_likely' を機械適用(LLM不要・即時)
  - strong: weak + 'ambiguous' だけをLLMで再判定
            → filler: edits化 / ambiguous: ユーザーへの質問(kind='filler')

安全群(えっと・あのー・そのー等)は字幕生成時にremove_fillers_weakで常時除去されるため
このジョブの対象外。フィラー除去は segments.text を変更しない(字幕・書き出しのみ)。
"""

import json
import sqlite3
from typing import Callable

from backend.core.project_settings import resolve_settings
from backend.jobs.queue import register
from backend.jobs.resolve_job import _get_client
from backend.pipeline import filler as filler_mod

CHUNK_SIZE = 40


def _insert_filler_edit(conn, media_id, segment_id, word, status, created_by="rule"):
    conn.execute(
        "INSERT INTO edits (media_id, segment_id, kind, original, replacement,"
        " status, confidence, created_by) VALUES (?,?,'filler',?,'',?,?,?)",
        (media_id, segment_id, word, status,
         "auto" if status == "applied" else "review", created_by),
    )


@register("filler")
def run_filler(
    conn: sqlite3.Connection,
    media_id: int,
    params: dict,
    progress: Callable[[float], None],
) -> None:
    s = resolve_settings(conn, media_id=media_id)
    level = params.get("level", s.filler_level)
    if level == "off":
        progress(1.0)
        return

    rows = conn.execute(
        "SELECT id, idx, text, filler_candidates_json FROM segments"
        " WHERE media_id=? AND is_aizuchi=0 ORDER BY idx",
        (media_id,),
    ).fetchall()

    existing = {
        (r["segment_id"], r["original"]) for r in conn.execute(
            "SELECT segment_id, original FROM edits WHERE media_id=? AND kind='filler'"
            " AND status IN ('proposed','applied')", (media_id,)
        )
    }
    existing_questions = {
        r["question_text"] for r in conn.execute(
            "SELECT question_text FROM questions WHERE media_id=? AND kind='filler'", (media_id,)
        )
    }

    # ---- 1段目: Whisper段階の判定を機械適用(filler_likely) ----
    ambiguous: list[tuple[sqlite3.Row, dict]] = []
    for r in rows:
        for c in json.loads(r["filler_candidates_json"] or "[]"):
            if not filler_mod.validate_filler(c["word"], r["text"]):
                continue
            if (r["id"], c["word"]) in existing:
                continue
            if c["class"] == "filler_likely":
                _insert_filler_edit(conn, media_id, r["id"], c["word"], "applied")
                existing.add((r["id"], c["word"]))
            elif c["class"] == "ambiguous":
                ambiguous.append((r, c))
    progress(0.3 if level == "strong" and ambiguous else 0.99)

    # ---- 2段目(strong): 曖昧なものだけLLMで再判定 ----
    if level == "strong" and ambiguous:
        client = _get_client(s)
        line_no = {r["id"]: i + 1 for i, r in enumerate(rows)}
        chunks = [ambiguous[i:i + CHUNK_SIZE] for i in range(0, len(ambiguous), CHUNK_SIZE)]
        for n, chunk in enumerate(chunks):
            lines = []
            for r, c in chunk:
                hint = []
                if c.get("elongated"):
                    hint.append("長音あり")
                if c.get("duration"):
                    hint.append(f"発話{c['duration']}秒")
                if c.get("gap_after"):
                    hint.append(f"直後ポーズ{c['gap_after']}秒")
                suffix = f"  [候補:『{c['word']}』 {'/'.join(hint)}]" if hint else f"  [候補:『{c['word']}』]"
                lines.append(f"{line_no[r['id']]}: {r['text']}{suffix}")

            payload = client.complete_json(
                filler_mod.FILLER_PROMPT, "\n".join(lines), filler_mod.FILLER_SCHEMA
            )
            id_by_line = {line_no[r["id"]]: r["id"] for r, _ in chunk}
            text_by_line = {line_no[r["id"]]: r["text"] for r, _ in chunk}
            for f in payload.get("fillers", []) or []:
                ln, word = int(f.get("line", 0)), str(f.get("word", ""))
                segment_id = id_by_line.get(ln)
                if segment_id is None or not filler_mod.validate_filler(word, text_by_line.get(ln, "")):
                    continue
                if (segment_id, word) in existing:
                    continue
                if f.get("judgment") == "filler":
                    apply_mode = params.get("apply_mode", s.pronoun_apply_mode)
                    status = "applied" if apply_mode == "full_auto" else "proposed"
                    _insert_filler_edit(conn, media_id, segment_id, word, status, created_by="llm")
                    existing.add((segment_id, word))
                else:  # LLMでも曖昧 → ユーザーに質問
                    q_text = (
                        f"「{text_by_line[ln]}」の『{word}』はフィラー(削除可)ですか、"
                        "意味のある語(指示語など)ですか?"
                    )
                    if q_text in existing_questions:
                        continue
                    conn.execute(
                        "INSERT INTO questions (media_id, kind, target_json, question_text,"
                        " candidates_json) VALUES (?,'filler',?,?,?)",
                        (media_id,
                         json.dumps({"segment_id": segment_id, "word": word}, ensure_ascii=False),
                         q_text,
                         json.dumps(["フィラー(字幕から削除)", "意味がある(残す)"],
                                    ensure_ascii=False)),
                    )
                    existing_questions.add(q_text)
            progress(0.3 + (n + 1) / len(chunks) * 0.69)

    conn.commit()
    progress(1.0)


def apply_filler_answer(conn: sqlite3.Connection, question_id: int, answer: str) -> dict:
    """フィラー質問への回答: 「削除」なら適用済みfiller editを作る。「残す」なら記録のみ"""
    q = conn.execute("SELECT * FROM questions WHERE id=?", (question_id,)).fetchone()
    if q is None:
        raise ValueError("質問が見つかりません")
    target = json.loads(q["target_json"])
    changed = 0
    if "削除" in answer:
        _insert_filler_edit(conn, q["media_id"], target["segment_id"], target["word"],
                            "applied", created_by="user")
        changed = 1
    conn.execute(
        "UPDATE questions SET status='answered', answer=? WHERE id=?", (answer, question_id)
    )
    conn.commit()
    return {"question_id": question_id, "answer": answer, "segments_changed": changed}


def filler_words_by_segment(conn: sqlite3.Connection, media_id: int) -> dict[int, list[str]]:
    """字幕生成時に適用する、セグメントごとの削除対象フィラー語"""
    out: dict[int, list[str]] = {}
    for r in conn.execute(
        "SELECT segment_id, original FROM edits WHERE media_id=? AND kind='filler'"
        " AND status='applied'", (media_id,)
    ):
        out.setdefault(r["segment_id"], []).append(r["original"])
    return out
