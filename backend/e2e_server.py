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
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

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


FAKE_ATTENTION = {
    "candidates": [
        {"start_line": 1, "end_line": 3, "title": "ハッカソンの話",
         "hook": "去年の意外な挑戦", "score": 8, "reasons": ["完結した話題"]}
    ]
}
FAKE_META = {
    "title": "ハッカソンで見つけた答え",
    "hooks": ["去年の意外な挑戦", "AIと古着の出会い", "結果は予想外"],
    "description": "去年のハッカソンについての対談クリップ。",
    "hashtags": ["#AI", "#ハッカソン"],
}


def _fake_llm(system: str, user: str) -> dict:
    """呼び出し内容で応答を出し分ける(プロンプトの種類で判別)"""
    if "編集アシスタント" in system:
        return FAKE_ASSIST
    if "音は合っているが漢字表記が誤っている" in system:
        return FAKE_QUESTIONS
    if "切り抜き候補" in system:
        return FAKE_ATTENTION
    if "投稿を最適化" in system:
        return FAKE_META
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

# E2E用の使い捨てライセンス発行鍵(プロセスごとに作り直す)
_E2E_ISSUER = Ed25519PrivateKey.generate()


@router.post("/reset")
def reset(request: Request) -> dict:
    """DBを空にして、テストの独立性を保つ"""
    db = request.app.state.db
    for table in ("edits", "feedback", "questions", "clip_cuts", "clips",
                  "segments", "jobs", "glossary", "llm_instructions", "media", "projects"):
        db.execute(f"DELETE FROM {table}")
    db.commit()
    # 登録済みライセンスも消す(specの実行順に結果が左右されないように)
    from backend.api import license_api

    license_api.key_path().unlink(missing_ok=True)
    from backend.api import keys_api

    for provider in keys_api.PROVIDERS:
        keys_api.key_path(provider).unlink(missing_ok=True)
    return {"status": "reset"}


@router.post("/seed")
def seed(request: Request, output_orientation: str = "landscape") -> dict:
    """プロジェクト+メディアを1件作る(文字起こしは別途ジョブで)。

    output_orientation=portrait を渡すと縦書き出しプロジェクトになる
    (M15の縦変換UIのE2E用)。メディアは1920×1080の横ソース扱い。
    """
    db = request.app.state.db
    cur = db.execute(
        "INSERT INTO projects (name, input_orientation, output_orientation)"
        " VALUES ('E2Eテスト対談', 'landscape', ?)",
        (output_orientation,),
    )
    project_id = cur.lastrowid
    cur = db.execute(
        "INSERT INTO media (project_id, path, duration, width, height, status)"
        " VALUES (?,?,?,?,?,'registered')",
        (project_id, "/e2e/sample.mov", 120.0, 1920, 1080),
    )
    db.commit()
    return {"project_id": project_id, "media_id": cur.lastrowid}


@router.post("/license-key")
def issue_license_key() -> dict:
    """テスト用の正規キーを1本発行する。

    本番の秘密鍵はリポジトリに無いので、E2Eでは使い捨ての鍵ペアを作り、
    アプリ側の公開鍵をそれに差し替えている(build_app参照)。
    """
    from backend.core import license as lic

    return {"key": lic.sign_payload(
        {"p": lic.PRODUCT, "e": "pro", "i": "2026-01-01", "x": "2099-01-01",
         "l": "E2Eテスト", "s": 1},
        _E2E_ISSUER,
    )}


def build_app():
    tmp = Path(tempfile.gettempdir()) / "whisper_e2e.db"
    tmp.unlink(missing_ok=True)
    settings.db_path = tmp
    settings.diarization_enabled = False

    from backend.api import license_api
    from backend.app import app
    from backend.core import license as lic

    # ライセンスは使い捨ての鍵ペアで検証し、保存先も一時ディレクトリにする
    license_api.PUBLIC_KEY = lic.public_key_to_text(_E2E_ISSUER.public_key())
    license_dir = Path(tempfile.mkdtemp(prefix="ks-e2e-license-"))
    license_api.key_path = lambda: license_dir / "license.key"

    # APIキーも一時ディレクトリへ(開発機の本物のキーを読まない・書き換えない)
    from backend.api import keys_api

    key_dir = Path(tempfile.mkdtemp(prefix="ks-e2e-keys-"))
    keys_api.key_path = lambda provider: key_dir / f"{provider}.txt"

    # モデルも一時ディレクトリを指す。開発機に本物が入っているかどうかで
    # セットアップ画面のE2Eの結果が変わらないようにする
    from backend.engines.asr import whispercpp
    from backend.engines.diarize import onnx

    model_dir = Path(tempfile.mkdtemp(prefix="ks-e2e-models-"))
    onnx.DEFAULT_SEGMENTATION = model_dir / "seg" / "model.onnx"
    onnx.DEFAULT_EMBEDDING = model_dir / "embedding.onnx"
    whispercpp.DEFAULT_BINARY = model_dir / "bin" / "whisper-cli"
    whispercpp.DEFAULT_MODEL = model_dir / "models" / "ggml-large-v3.bin"

    app.include_router(router)
    resolve_job.set_client_factory(lambda: FakeLLMClient(responses=_fake_llm))
    return app


app = build_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=E2E_PORT, log_level="warning")
