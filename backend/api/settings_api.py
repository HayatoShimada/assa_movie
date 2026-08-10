"""設定の取得・更新API。フロントの設定タブと対応する。

変更はプロセス内singletonに反映しつつ app_settings テーブルにも永続化する
(MUTABLE_FIELDSの定義は backend/core/project_settings.py)。
"""

import sqlite3

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, create_model

from backend.api.deps import get_db, get_jobs
from backend.core import hwprofile
from backend.core.config import Settings, settings
from backend.core.console import SUBPROCESS_TEXT
from backend.core.environment import recommend, scan_environment
from backend.core.project_settings import MUTABLE_FIELDS, save_global_overrides
from backend.engines.asr.registry import MODELS
from backend.engines.diarize import registry as diarize
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
    """確定済みプロファイルと、VRAMに収まるASR/LLMモデルの推奨(設定タブの環境パネル用)"""
    env = scan_environment(settings)
    # GPUで計算する構成のときだけVRAMを前提にモデルを選ばせる
    on_gpu = env["resolved"]["engine"] == "whispercpp"
    total = env["gpu"].get("vram_total_mb", 0) if on_gpu else 0

    ollama_options = [
        {**m, "fits": on_gpu and m["vram_mb"] <= total}
        for m in env["ollama"]["models"]
    ]
    return {
        **env,
        "recommendations": recommend(
            total, env["resolved"]["engine"], env["ollama"]["models"]
        ),
        "ollama_options": ollama_options,
    }


@router.post("/environment/redetect")
def redetect_environment(db: sqlite3.Connection = Depends(get_db)) -> dict:
    """実行環境の再検出(GPU増設・ドライバ導入後の唯一の追従手段)"""
    hwprofile.redetect(db)
    return get_environment()


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


# fc-listはLinux(fontconfig)専用。無いOSでの候補は「そのOSに標準で入って
# いるもの」を挙げる。存在しないフォント名だけを出すと、選んでも反映されず
# 字幕フォントが実質変えられない状態になる(Windowsが Noto Sans JP 固定だった)
FALLBACK_FONTS = {
    "Windows": ["Yu Gothic UI", "Yu Gothic", "Meiryo", "MS Gothic", "MS Mincho"],
    "Darwin": ["Hiragino Sans", "Hiragino Kaku Gothic ProN", "Hiragino Mincho ProN"],
    "Linux": ["Noto Sans JP", "IPAGothic", "TakaoGothic"],
}


def fallback_fonts(os_name: str | None = None) -> list[str]:
    """fc-listが使えないときのフォント候補(純関数)。

    知らないOSはLinux扱いにする。候補を空で返すとUIの選択肢が消えるため、
    必ず1つ以上返す。
    """
    import platform

    return FALLBACK_FONTS.get(os_name or platform.system(), FALLBACK_FONTS["Linux"])


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
                capture_output=True, timeout=10, **SUBPROCESS_TEXT,
            )
            fonts = parse_fc_list(out.stdout)
        except subprocess.SubprocessError:
            fonts = []
    return {"fonts": fonts or fallback_fonts()}


@router.get("/settings")
def get_settings_api() -> dict:
    return {
        "values": {k: getattr(settings, k) for k in sorted(MUTABLE_FIELDS)},
        # 話者分離はONNXのみ。モデル未取得ならUIでスイッチを無効化する
        "diarization_ready": diarize.available(),
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
SETUP_JOBS = {"diarization": "setup_diarization", "whispercpp": "setup_whispercpp"}


@router.post("/setup/{item}")
def start_setup(item: str, jobs=Depends(get_jobs)) -> dict:
    """モデル取得を始める。進捗は既存のジョブAPI(SSE)で受け取る"""
    if item not in SETUP_JOBS:
        raise HTTPException(404, f"アプリから取得できない項目です: {item}")
    # メディアに紐づかないジョブなので media_id は None
    job_id = jobs.enqueue(None, SETUP_JOBS[item], {})
    return {"id": job_id, "type": SETUP_JOBS[item], "status": "queued", "progress": 0.0}
