"""設定の取得・更新API。フロントの設定タブと対応する。"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.core.config import settings
from backend.engines.asr.registry import MODELS
from backend.engines.llm.gemini import load_api_key
from backend.engines.llm.registry import PROVIDERS

router = APIRouter(prefix="/api", tags=["settings"])

# UIから変更可能な項目(誤ってDBパス等を書き換えられないよう明示的に許可する)
MUTABLE_FIELDS = {
    "asr_model", "asr_language", "asr_beam_size", "asr_vad_filter",
    "diarization_enabled", "num_speakers", "male_name", "female_name",
    "aizuchi_filter_enabled", "aizuchi_max_duration",
    "filler_level",
    "pronoun_enabled", "pronoun_level", "pronoun_form", "pronoun_apply_mode",
    "subtitle_mode", "subtitle_adoption_rate",
    "subtitle_max_chars_per_line", "subtitle_max_lines",
    "llm_provider", "ollama_model", "gemini_model",
}


class SettingsUpdate(BaseModel):
    model_config = {"extra": "forbid"}

    asr_model: str | None = None
    asr_language: str | None = None
    filler_level: str | None = None
    pronoun_enabled: bool | None = None
    pronoun_level: str | None = None
    pronoun_form: str | None = None
    pronoun_apply_mode: str | None = None
    subtitle_mode: str | None = None
    subtitle_adoption_rate: float | None = None
    subtitle_max_chars_per_line: int | None = None
    diarization_enabled: bool | None = None
    num_speakers: int | None = None
    male_name: str | None = None
    female_name: str | None = None
    aizuchi_filter_enabled: bool | None = None
    llm_provider: str | None = None
    ollama_model: str | None = None
    gemini_model: str | None = None


@router.get("/settings")
def get_settings_api() -> dict:
    return {
        "values": {k: getattr(settings, k) for k in sorted(MUTABLE_FIELDS)},
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
def update_settings(body: SettingsUpdate) -> dict:
    changes = body.model_dump(exclude_none=True)
    if "asr_model" in changes and changes["asr_model"] not in MODELS:
        raise HTTPException(400, f"未知のASRモデル: {changes['asr_model']}")
    if "llm_provider" in changes and changes["llm_provider"] not in PROVIDERS:
        raise HTTPException(400, f"未知のLLMプロバイダ: {changes['llm_provider']}")
    for key, value in changes.items():
        if key not in MUTABLE_FIELDS:
            raise HTTPException(400, f"変更できない設定です: {key}")
        setattr(settings, key, value)
    return get_settings_api()
