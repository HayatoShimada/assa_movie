"""E2Eテスト用のバックエンド起動スクリプト。

本番と違う点:
  - 一時DBを使う(本番のwhisper.dbを汚さない)
  - LLMはFakeに差し替える(Ollama/Geminiが無くてもE2Eが通る)
  - 文字起こしジョブもFakeに差し替える(GPUと実音声が無くても通る)
  - シード用エンドポイント /api/e2e/reset を持つ

起動: uv run python -m backend.e2e_server
"""

import sqlite3
import tempfile
from pathlib import Path
from typing import Callable

from fastapi import APIRouter, Request

from backend.core.config import settings
from backend.engines.llm.base import FakeLLMClient
from backend.jobs import queue as job_queue
from backend.jobs import resolve_job

E2E_PORT = 8001

# 決まった応答を返すFakeLLM(E2Eの期待値を固定するため)
FAKE_EDITS = {
    "edits": [
        {
            "line": 2, "original": "それ", "replacement": "去年のハッカソン",
            "referent": "去年のハッカソン", "confidence": "review",
        }
    ]
}
FAKE_QUESTIONS = {
    "questions": [
        {"term": "反動体", "reason": "半導体の誤認識と思われます", "candidates": ["半導体"]}
    ]
}

SEED_SEGMENTS = [
    ("はやまる: 去年ハッカソンに出たんですよ", "はやまる"),
    ("はやまる: それがすごく良くて", "はやまる"),
    ("高田さん: 反動体の話も面白かったです", "高田さん"),
    ("はやまる: うん", "はやまる"),
]


FAKE_ASSIST = {
    "reply": "『反動体』は半導体の誤認識と判断し、注釈を提案しました。",
    "edits": [
        {"original": "反動体", "replacement": "半導体", "referent": "半導体"}
    ],
    "instruction_suggestion": "「反動体」は「半導体」の誤認識として扱う",
}


def _fake_llm(system: str, user: str) -> dict:
    """呼び出し内容で応答を出し分ける(プロンプトの種類で判別)"""
    if "編集アシスタント" in system:
        return FAKE_ASSIST
    if "音は合っているが漢字表記が誤っている" in system:
        return FAKE_QUESTIONS
    return FAKE_EDITS


@job_queue.register("transcribe_fake")
def _fake_transcribe(
    conn: sqlite3.Connection, media_id: int, params: dict, progress: Callable[[float], None]
) -> None:
    """GPUも音声ファイルも使わずにセグメントを作る"""
    import time

    conn.execute("DELETE FROM segments WHERE media_id=?", (media_id,))
    for idx, (text, speaker) in enumerate(SEED_SEGMENTS):
        progress((idx + 1) / len(SEED_SEGMENTS) * 0.9)
        time.sleep(0.15)  # 進捗表示をUIで観測できるよう少し待つ
        conn.execute(
            "INSERT INTO segments (media_id, idx, start, end, text, original_text,"
            " speaker, is_aizuchi, words_json) VALUES (?,?,?,?,?,?,?,?,?)",
            (media_id, idx, idx * 2.0, idx * 2.0 + 1.8, text, text, speaker,
             int(text.endswith("うん")), "[]"),
        )
    conn.execute("UPDATE media SET status='transcribed' WHERE id=?", (media_id,))
    conn.commit()
    progress(1.0)


router = APIRouter(prefix="/api/e2e", tags=["e2e"])


@router.post("/reset")
def reset(request: Request) -> dict:
    """DBを空にして、テストの独立性を保つ"""
    db = request.app.state.db
    for table in ("edits", "feedback", "questions", "clip_cuts", "clips",
                  "segments", "jobs", "glossary", "llm_instructions", "media", "projects"):
        db.execute(f"DELETE FROM {table}")
    db.commit()
    return {"status": "reset"}


@router.post("/seed")
def seed(request: Request) -> dict:
    """プロジェクト+メディアを1件作る(文字起こしは別途ジョブで)"""
    db = request.app.state.db
    cur = db.execute("INSERT INTO projects (name) VALUES ('E2Eテスト対談')")
    project_id = cur.lastrowid
    cur = db.execute(
        "INSERT INTO media (project_id, path, duration, status) VALUES (?,?,?,'registered')",
        (project_id, "/e2e/sample.mov", 120.0),
    )
    db.commit()
    return {"project_id": project_id, "media_id": cur.lastrowid}


def build_app():
    tmp = Path(tempfile.gettempdir()) / "whisper_e2e.db"
    tmp.unlink(missing_ok=True)
    settings.db_path = tmp
    settings.diarization_enabled = False

    from backend.app import app

    app.include_router(router)
    resolve_job.set_client_factory(lambda: FakeLLMClient(responses=_fake_llm))
    return app


app = build_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=E2E_PORT, log_level="warning")
