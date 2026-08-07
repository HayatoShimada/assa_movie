"""設定の取得・更新API。フロントの設定タブと対応する。

変更はプロセス内singletonに反映しつつ app_settings テーブルにも永続化する
(MUTABLE_FIELDSの定義は backend/core/project_settings.py)。
"""

import sqlite3

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.api.deps import get_db
from backend.core.config import settings
from backend.core.environment import recommend, scan_environment
from backend.core.project_settings import MUTABLE_FIELDS, save_global_overrides
from backend.engines.asr.registry import ENGINES, MODELS
from backend.engines.llm.gemini import load_api_key
from backend.engines.llm.registry import PROVIDERS

router = APIRouter(prefix="/api", tags=["settings"])


class SettingsUpdate(BaseModel):
    model_config = {"extra": "forbid"}

    asr_model: str | None = None
    asr_engine: str | None = None
    asr_language: str | None = None
    filler_level: str | None = None
    pronoun_enabled: bool | None = None
    pronoun_level: str | None = None
    pronoun_form: str | None = None
    pronoun_apply_mode: str | None = None
    subtitle_mode: str | None = None
    subtitle_adoption_rate: float | None = None
    subtitle_font_size: int | None = None
    subtitle_position: str | None = None
    subtitle_offset_y: int | None = None
    subtitle_max_chars_per_line: int | None = None
    subtitle_font_family: str | None = None
    subtitle_text_color: str | None = None
    subtitle_speaker_colors: bool | None = None
    subtitle_bg: str | None = None
    subtitle_bg_color: str | None = None
    subtitle_bg_opacity: float | None = None
    vram_budget_mb: int | None = None
    diarization_enabled: bool | None = None
    num_speakers: int | None = None
    male_name: str | None = None
    female_name: str | None = None
    aizuchi_filter_enabled: bool | None = None
    convert_method: str | None = None
    llm_provider: str | None = None
    ollama_model: str | None = None
    gemini_model: str | None = None


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
        for engine, vram in (("faster_whisper", m.vram_fw_mb), ("transformers", m.vram_tf_mb))
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
    return {
        "values": {k: getattr(settings, k) for k in sorted(MUTABLE_FIELDS)},
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
                "ready": p.local or bool(load_api_key(settings.gemini_key_file)),
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
    if "llm_provider" in changes and changes["llm_provider"] not in PROVIDERS:
        raise HTTPException(400, f"未知のLLMプロバイダ: {changes['llm_provider']}")
    for key, value in changes.items():
        if key not in MUTABLE_FIELDS:
            raise HTTPException(400, f"変更できない設定です: {key}")
        setattr(settings, key, value)
    save_global_overrides(db, changes)  # 再起動しても消えないようDBにも保存
    return get_settings_api()
