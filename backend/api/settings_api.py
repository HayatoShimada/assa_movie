"""設定の取得・更新API。フロントの設定タブと対応する。

変更はプロセス内singletonに反映しつつ app_settings テーブルにも永続化する
(MUTABLE_FIELDSの定義は backend/core/project_settings.py)。
"""

import sqlite3

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, create_model

from backend.api.deps import get_db, get_jobs
from backend.core.config import Settings, settings
from backend.core.environment import recommend, scan_environment
from backend.core.project_settings import MUTABLE_FIELDS, save_global_overrides
from backend.engines.asr.registry import ENGINES, MODELS
from backend.engines.diarize.registry import ENGINES as DIARIZE_ENGINES
from backend.engines.diarize.registry import resolve_engine as resolve_diarize_engine
from backend.api.keys_api import provider_ready
from backend.engines.llm.registry import PROVIDERS

router = APIRouter(prefix="/api", tags=["settings"])


# 変更可能項目とその型は Settings が持つ唯一の定義から組み立てる。
# 手書きすると項目の追加漏れで「UIに出るのに保存できない設定」が生まれる
SettingsUpdate = create_model(
    "SettingsUpdate",
    __config__=ConfigDict(extra="forbid"),
    **{
        name: (Settings.model_fields[name].annotation | None, None)
        for name in sorted(MUTABLE_FIELDS)
    },
)


@router.get("/environment")
def get_environment() -> dict:
    """環境スキャン結果と、割当VRAMに収まるASR/LLMの推奨を返す(設定タブの環境パネル用)"""
    env = scan_environment(settings)
    total = env["gpu"].get("vram_total_mb", 0)
    budget = int(settings.vram_budget_mb or 0)
    effective = min(budget, total) if budget > 0 else total
    has_gpu = bool(env["gpu"])

    asr_options = [
        {
            "model": m.id,
            "engine": engine,
            "vram_mb": vram,
            # CPU実行はVRAM制約なし。GPUがあれば割当内に収まるかを判定
            "fits": (not has_gpu) or vram <= effective,
        }
        for m in MODELS.values()
        for engine in ENGINES
        if engine != "auto"
        for vram in [m.vram_mb(engine)]
    ]
    ollama_options = [
        {**m, "fits": has_gpu and m["vram_mb"] <= effective}
        for m in env["ollama"]["models"]
    ]
    return {
        **env,
        "vram_budget_mb": budget,
        "effective_vram_mb": effective,
        "recommendations": recommend(effective, env["accel"], env["ollama"]["models"]),
        "asr_options": asr_options,
        "ollama_options": ollama_options,
    }


def parse_fc_list(output: str) -> list[str]:
    """`fc-list :lang=ja family` の出力からファミリ名一覧を作る(純関数)。

    カンマ区切りの別名(ローカライズ名等)は先頭の英名を採用する。
    """
    fonts = {
        line.split(",")[0].strip()
        for line in output.splitlines()
        if line.strip()
    }
    return sorted(fonts)


@router.get("/fonts")
def list_fonts() -> dict:
    """日本語対応フォントの一覧(字幕のフォント選択UI用)"""
    import shutil
    import subprocess

    fonts: list[str] = []
    if shutil.which("fc-list"):
        try:
            out = subprocess.run(
                ["fc-list", ":lang=ja", "family"],
                capture_output=True, text=True, timeout=10,
            )
            fonts = parse_fc_list(out.stdout)
        except subprocess.SubprocessError:
            fonts = []
    if not fonts:
        fonts = ["Noto Sans JP"]  # fc-list不在でも既定フォントは選べるようにする
    return {"fonts": fonts}


@router.get("/settings")
def get_settings_api() -> dict:
    from backend.engines.diarize.pyannote import load_hf_token

    has_token = bool(load_hf_token(settings.hf_token_file))
    return {
        "values": {k: getattr(settings, k) for k in sorted(MUTABLE_FIELDS)},
        "diarization_engines": [
            {
                "id": engine_id, "label": label,
                # モデル未取得/トークン未設定のエンジンはUIで選べないよう伝える
                "ready": resolve_diarize_engine(engine_id, has_token=has_token) is not None,
            }
            for engine_id, label in DIARIZE_ENGINES.items()
        ],
        "asr_engines": [
            {"id": engine_id, "label": label} for engine_id, label in ENGINES.items()
        ],
        "asr_models": [
            {
                "id": m.id, "label": m.label, "rtf": m.rtf,
                "word_timestamps": m.word_timestamps, "note": m.note,
            }
            for m in MODELS.values()
        ],
        "llm_providers": [
            {
                "id": p.id, "label": p.label, "local": p.local,
                "models": list(p.models), "note": p.note,
                # クラウドは鍵が無いと使えないのでUIで事前に案内できるようにする
                # (プロバイダごとに別のキーを見る)
                "ready": p.local or provider_ready(p.id),
            }
            for p in PROVIDERS.values()
        ],
    }


@router.patch("/settings")
def update_settings(body: SettingsUpdate, db: sqlite3.Connection = Depends(get_db)) -> dict:
    changes = body.model_dump(exclude_none=True)
    if "asr_model" in changes and changes["asr_model"] not in MODELS:
        raise HTTPException(400, f"未知のASRモデル: {changes['asr_model']}")
    if "asr_engine" in changes and changes["asr_engine"] not in ENGINES:
        raise HTTPException(400, f"未知のASRエンジン: {changes['asr_engine']}")
    if "diarization_engine" in changes and changes["diarization_engine"] not in DIARIZE_ENGINES:
        raise HTTPException(400, f"未知の話者分離エンジン: {changes['diarization_engine']}")
    if "llm_provider" in changes and changes["llm_provider"] not in PROVIDERS:
        raise HTTPException(400, f"未知のLLMプロバイダ: {changes['llm_provider']}")
    for key, value in changes.items():
        if key not in MUTABLE_FIELDS:
            raise HTTPException(400, f"変更できない設定です: {key}")
        setattr(settings, key, value)
    save_global_overrides(db, changes)  # 再起動しても消えないようDBにも保存
    return get_settings_api()


@router.get("/setup")
def get_setup_status() -> dict:
    """初回セットアップの状態(モデルが揃っているか)"""
    from backend.jobs.setup_job import status

    return status()


# アプリから取得できるもの(画面のIDとジョブ種別の対応)
SETUP_JOBS = {"diarization": "setup_diarization"}


@router.post("/setup/{item}")
def start_setup(item: str, jobs=Depends(get_jobs)) -> dict:
    """モデル取得を始める。進捗は既存のジョブAPI(SSE)で受け取る"""
    if item not in SETUP_JOBS:
        raise HTTPException(404, f"アプリから取得できない項目です: {item}")
    # メディアに紐づかないジョブなので media_id は None
    job_id = jobs.enqueue(None, SETUP_JOBS[item], {})
    return {"id": job_id, "type": SETUP_JOBS[item], "status": "queued", "progress": 0.0}
