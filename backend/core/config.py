"""アプリ設定。UIの設定タブと1対1で対応する。

環境変数(接頭辞 WL_)または .env で上書き可能。
例: WL_ASR_MODEL=large-v3-turbo
"""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="WL_", env_file=".env", extra="ignore"
    )

    # ---- 基盤 ----
    db_path: Path = PROJECT_ROOT / "whisper.db"
    hf_token_file: Path = PROJECT_ROOT / "hf_token.txt"

    # ---- ASR ----
    # 既定はlarge-v3(精度優先・単語タイムスタンプ必須の要件による。BACKEND_DESIGN.md参照)
    asr_model: str = "large-v3"
    asr_compute_type: str = "float16"  # Blackwellではint8がクラッシュするため固定
    asr_language: str = "ja"
    asr_beam_size: int = 5
    asr_vad_filter: bool = True

    # ---- 話者分離 ----
    diarization_enabled: bool = True
    diarization_model: str = "pyannote/speaker-diarization-3.1"
    num_speakers: int | None = 2
    male_name: str = "話者A"
    female_name: str = "話者B"

    # ---- 相槌除外 ----
    aizuchi_filter_enabled: bool = True
    aizuchi_max_duration: float = 2.0

    # ---- フィラー排除 ----
    filler_level: str = "off"  # off | weak | strong

    # ---- 指示語置換 ----
    pronoun_enabled: bool = True
    pronoun_level: str = "medium"  # weak | medium | strong
    pronoun_form: str = "annotate"  # annotate | replace | complete
    pronoun_apply_mode: str = "auto_and_review"  # full_auto | auto_and_review | all_review

    # ---- 字幕 ----
    subtitle_mode: str = "all"  # all | selective
    subtitle_adoption_rate: float = 0.3  # selective時の採用率
    subtitle_max_chars_per_line: int = 15
    subtitle_max_lines: int = 2

    # ---- LLM ----
    llm_provider: str = "ollama"  # ollama | anthropic
    ollama_url: str = "http://localhost:11434/api/chat"
    ollama_model: str = "qwen3:32b"
    llm_chunk_size: int = 30
    llm_context_size: int = 15

    # ---- ジョブ ----
    max_replacement_len: int = 40
    llm_retries: int = 3


settings = Settings()


def get_settings() -> Settings:
    """FastAPIの依存性注入用(テストで差し替えやすくする)"""
    return settings
