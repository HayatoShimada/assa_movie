"""固有名詞スキャンジョブ: 表記が確定できない固有名詞をLLMが質問として出す。

音は合っているが漢字が誤るASR特有の誤認識(例: 半導体→反動体)は機械では確定
できないため、ユーザーに聞く。回答は用語集と利用者の辞書に登録し、全出現箇所を一括修正する。

利用者の辞書(core/user_terms.py)に「以前の聞き間違い」があれば、AIに聞く前に
それを本文から探して質問にする(前の動画で答えた内容を次の動画で活かす)。
適用はしない。答えるのは利用者(非破壊・提案だけの原則は同じ)。
"""

import json
import sqlite3
from collections import Counter
from typing import Callable

from backend.core import user_terms
from backend.core.project_settings import resolve_settings
from backend.jobs.queue import register
from backend.jobs.resolve_job import _get_client
from backend.pipeline.job_summary import terms_summary

QUESTIONS_SCHEMA = {
    "type": "object",
    "properties": {
        "questions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "term": {"type": "string"},
                    "reason": {"type": "string"},
                    "candidates": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["term", "reason", "candidates"],
            },
        }
    },
    "required": ["questions"],
}

SYSTEM_PROMPT = """あなたは日本語の音声認識結果を校正する編集者です。
文字起こしの中から、**音は合っているが漢字表記が誤っている可能性が高い固有名詞・専門用語**を
見つけて、ユーザーに確認する質問を作ってください。

着目する点:
1. 一般的でない漢字の組み合わせ(例:「反動体」は「半導体」の誤認識の可能性が高い)
2. 同じ語の表記ゆれ(例:「箱ストア」と「ハコストア」が混在)
3. 人名・会社名・製品名・イベント名で表記が確定できないもの

ルール:
- 明らかに正しい一般語は挙げない。確認が必要なものだけに絞る。
- candidates には推定される正しい表記を可能性の高い順に最大3つ挙げる。
- reason には「なぜ誤認識と思われるか」を1文で書く。
- 該当が無ければ {"questions": []} を返す。

出力形式: {"questions": [{"term": "反動体", "reason": "半導体の誤認識と思われます",
"candidates": ["半導体"]}]}"""


@register("extract_terms")
def run_extract_terms(
    conn: sqlite3.Connection,
    media_id: int,
    params: dict,
    progress: Callable[[float], None],
) -> dict:
    rows = conn.execute(
        "SELECT text FROM segments WHERE media_id=? AND is_aizuchi=0 ORDER BY idx",
        (media_id,),
    ).fetchall()
    if not rows:
        progress(1.0)
        return terms_summary(found=0, lines=0)

    texts = [r["text"] for r in rows]
    joined = "\n".join(texts)
    existing = {
        r["question_text"]: json.loads(r["target_json"] or "{}").get("term")
        for r in conn.execute(
            "SELECT question_text, target_json FROM questions WHERE media_id=? AND kind='term'",
            (media_id,),
        )
    }
    asked = {term for term in existing.values() if term}
    created = 0  # 今回新しく作った質問の数(結果の説明に使う)

    # ---- 辞書にある「以前の聞き間違い」(AIを呼ぶ前に済ませる。AIに繋がらなくても残る) ----
    dictionary = user_terms.list_terms(conn)
    known = {d["term"] for d in dictionary}
    for wrong, correct, count in user_terms.find_misrecognitions(
        joined, [(d["term"], d["misrecognitions"]) for d in dictionary]
    ):
        if wrong in asked or wrong in known:
            continue
        text = (f"「{wrong}」({count}回出現)は、辞書にある「{correct}」の聞き間違いかも"
                "しれません。正式な表記を教えてください。")
        _insert_question(conn, media_id, wrong, count, text, [correct], source="dictionary")
        asked.add(wrong)
        created += 1
    conn.commit()

    client = _get_client(resolve_settings(conn, media_id=media_id))
    chunk_size = params.get("chunk_size", 100)
    chunks = [texts[i:i + chunk_size] for i in range(0, len(texts), chunk_size)]

    found: dict[str, dict] = {}
    for n, chunk in enumerate(chunks):
        payload = client.complete_json(
            SYSTEM_PROMPT, "\n".join(chunk), QUESTIONS_SCHEMA
        )
        for q in payload.get("questions", []) or []:
            term = str(q.get("term", "")).strip()
            if term and term not in found:
                found[term] = {
                    "reason": str(q.get("reason", "")),
                    "candidates": [str(c) for c in (q.get("candidates") or [])][:3],
                }
        progress(min((n + 1) / len(chunks) * 0.9, 0.9))

    # 出現回数を数え、既存の質問と重複しないものだけ登録する
    for term, info in found.items():
        count = joined.count(term)
        if count == 0:
            continue  # LLMが実在しない語を作った場合は捨てる
        if term in known or term in asked:
            continue  # 辞書で確定済みの表記・同じ語への質問がすでにある
        candidates = info["candidates"]
        suggestion = f"「{candidates[0]}」の誤認識と思われます。" if candidates else ""
        text = f"「{term}」({count}回出現)は{suggestion}正式な表記を教えてください。"
        if text in existing:
            continue
        _insert_question(conn, media_id, term, count, text, candidates)
        created += 1

    conn.commit()
    progress(1.0)
    return terms_summary(found=created, lines=len(texts))


def _insert_question(
    conn: sqlite3.Connection,
    media_id: int,
    term: str,
    count: int,
    text: str,
    candidates: list[str],
    source: str = "llm",
) -> None:
    target = {"term": term, "count": count}
    if source != "llm":
        target["source"] = source
    conn.execute(
        "INSERT INTO questions (media_id, kind, target_json, question_text, candidates_json)"
        " VALUES (?,'term',?,?,?)",
        (media_id, json.dumps(target, ensure_ascii=False), text,
         json.dumps(candidates, ensure_ascii=False)),
    )


def apply_term_answer(
    conn: sqlite3.Connection, question_id: int, answer: str
) -> dict:
    """質問への回答を適用する: 用語集に登録し、全出現箇所を一括修正する。"""
    q = conn.execute("SELECT * FROM questions WHERE id=?", (question_id,)).fetchone()
    if q is None:
        raise ValueError("質問が見つかりません")

    target = json.loads(q["target_json"])
    term = target.get("term", "")
    media_id = q["media_id"]
    project_id = conn.execute(
        "SELECT project_id FROM media WHERE id=?", (media_id,)
    ).fetchone()["project_id"]

    changed = 0
    if term and answer and answer != term:
        # LIKE だと語に含まれる % や _ がワイルドカードになるので instr で探す
        for seg in conn.execute(
            "SELECT id, text FROM segments WHERE media_id=? AND instr(text, ?) > 0",
            (media_id, term),
        ).fetchall():
            new_text = user_terms.replace_misrecognition(seg["text"], term, answer)
            if new_text == seg["text"]:
                continue  # 正しい表記の中にしか出ていない(ハコスト ⊂ ハコストア)
            conn.execute("UPDATE segments SET text=? WHERE id=?", (new_text, seg["id"]))
            conn.execute(
                "INSERT INTO edits (media_id, segment_id, kind, original, replacement,"
                " status, confidence, created_by) VALUES (?,?,'term',?,?,'applied','auto','user')",
                (media_id, seg["id"], term, answer),
            )
            changed += 1

    # プロジェクトの用語集に登録(指示語解決などLLMのプロンプトで使う)
    if answer and not conn.execute(
        "SELECT 1 FROM glossary WHERE project_id=? AND term=?", (project_id, answer)
    ).fetchone():
        conn.execute(
            "INSERT INTO glossary (project_id, term, description) VALUES (?,?,?)",
            (project_id, answer, f"文字起こしで「{term}」と誤認識されることがある"),
        )
    # 利用者の辞書にも覚える(全プロジェクト共通。次の文字起こしでWhisperに渡す)。
    # 辞書に入らない語(空・長すぎる)でも、回答そのものの適用は止めない
    try:
        user_terms.add_term(
            conn, answer,
            misrecognitions=[term] if term and term != answer else [],
            source="question", commit=False,
        )
    except user_terms.InvalidTermError:
        pass

    conn.execute(
        "UPDATE questions SET status='answered', answer=? WHERE id=?", (answer, question_id)
    )
    conn.commit()
    return {"question_id": question_id, "answer": answer, "segments_changed": changed}
