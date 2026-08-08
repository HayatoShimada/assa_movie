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
    # auto: CUDA→faster-whisper / ROCm→transformers / CPU→faster-whisper(int8)
    asr_engine: str = "auto"  # auto | faster_whisper | transformers
    asr_compute_type: str = "float16"  # Blackwellではint8がクラッシュするため固定
    asr_language: str = "ja"
    asr_beam_size: int = 5
    asr_vad_filter: bool = True
    # フィラー入りの文体例をinitial_promptに与え、言い淀みを忠実に転写させる
    asr_verbatim_style: bool = True

    # ---- 話者分離 ----
    diarization_enabled: bool = True
    # auto: ONNXモデルがあればONNX / 無ければHFトークン次第でpyannote
    diarization_engine: str = "auto"  # auto | onnx | pyannote
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
    subtitle_font_size: int = 48
    subtitle_position: str = "bottom"  # top | center | bottom
    subtitle_offset_y: int = 0  # +で下、-で上
    subtitle_max_chars_per_line: int = 15
    subtitle_max_lines: int = 2
    # スタイル(px値は1920×1080基準。出力解像度へは幅/高さ比率で自動換算)
    subtitle_font_family: str = "Noto Sans JP"
    subtitle_text_color: str = "#FFFFFF"
    subtitle_speaker_colors: bool = True  # 話者ごとの色分け(Falseで全員text_color)
    subtitle_bg: str = "none"  # none(縁取り) | box(背景ボックス)
    subtitle_bg_color: str = "#000000"
    subtitle_bg_opacity: float = 0.5

    # ---- レイアウト(向き変換) ----
    # 入力と出力の向きが違うときの変換方式。クリップ単位でも上書き可能
    convert_method: str = "blur_pad"  # crop | blur_pad | face

    # ---- LLM ----
    llm_provider: str = "ollama"  # ollama | gemini
    ollama_url: str = "http://localhost:11434/api/chat"
    ollama_model: str = "qwen3:32b"
    gemini_model: str = "gemini-3.5-flash"
    gemini_key_file: Path = PROJECT_ROOT / "gemini_api_key.txt"
    llm_chunk_size: int = 30
    llm_context_size: int = 15

    # ---- リソース ----
    # torch系コンポーネントのVRAM使用上限(MB)。0=無制限。
    # ASR/LLMモデルの推奨判定にも使う(設定タブの環境パネル)
    vram_budget_mb: int = 0

    # ---- ジョブ ----
    max_replacement_len: int = 40
    llm_retries: int = 3


settings = Settings()


def get_settings() -> Settings:
    """FastAPIの依存性注入用(テストで差し替えやすくする)"""
    return settings
