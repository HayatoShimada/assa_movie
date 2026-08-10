"""アプリ設定。UIの設定タブと1対1で対応する。

環境変数(接頭辞 KS_)または .env で上書き可能。
例: KS_ASR_MODEL=large-v3-turbo

ファイルの置き場所は backend/core/paths.py が決める(既存環境ではリポジトリ直下、
新規インストールではOS標準の場所)。
"""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from backend.core import paths

PROJECT_ROOT = paths.PROJECT_ROOT


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="KS_", env_file=".env", extra="ignore"
    )

    # ---- 基盤 ----
    db_path: Path = Field(default_factory=paths.db_path)

    # ---- ASR ----
    # 既定はlarge-v3(精度優先・単語タイムスタンプ必須の要件による。BACKEND_DESIGN.md参照)
    asr_model: str = "large-v3"
    # エンジンはハードウェアプロファイル(core/hwprofile.py)で決まり、UIでは選べない。
    # 空=プロファイルに従う。KS_ASR_ENGINE 環境変数だけが上級者向けの上書き手段
    asr_engine: str = ""  # "" | faster_whisper | whispercpp
    asr_language: str = "ja"
    asr_beam_size: int = 5
    asr_vad_filter: bool = True
    # フィラー入りの文体例をinitial_promptに与え、言い淀みを忠実に転写させる
    asr_verbatim_style: bool = True

    # ---- 話者分離 ----
    # エンジンはONNX(sherpa-onnx)のみ。選択肢が1つなので設定は置かない
    diarization_enabled: bool = True
    num_speakers: int | None = 2
    male_name: str = "話者A"
    female_name: str = "話者B"

    # ---- 相槌除外 ----
    # 相槌は字幕から常に除外する(subtitle.py)。有無を切り替える設定は置かない
    aizuchi_max_duration: float = 2.0

    # ---- フィラー排除 ----
    filler_level: str = "off"  # off | weak | strong

    # ---- 指示語置換 ----
    # 実行はレビュータブのボタンで始める。使うかどうかは押すかどうかで決まる
    pronoun_level: str = "medium"  # weak | medium | strong
    pronoun_form: str = "annotate"  # annotate | replace | complete
    pronoun_apply_mode: str = "auto_and_review"  # full_auto | auto_and_review | all_review

    # ---- 字幕 ----
    # 字幕の採否は judge ジョブが決める(subtitle_show)。採用率はその閾値
    subtitle_adoption_rate: float = 0.3
    subtitle_font_size: int = 48
    subtitle_position: str = "bottom"  # top | center | bottom
    subtitle_offset_y: int = 0  # +で下、-で上
    # 行数はこの折り返し幅で決まる(上限を別に持つと二重管理になる)
    subtitle_max_chars_per_line: int = 15
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

    # ---- 初回セットアップ ----
    # 初回起動時のウィザードを済ませたか。専用のファイルやテーブルを増やさず
    # 設定として持つ(設定タブから「やり直す」でfalseに戻せる)
    setup_completed: bool = False

    # ---- LLM ----
    llm_provider: str = "ollama"  # ollama | gemini | claude
    ollama_url: str = "http://localhost:11434/api/chat"
    ollama_model: str = "qwen3:32b"
    gemini_model: str = "gemini-3.5-flash"
    gemini_key_file: Path = Field(
        default_factory=lambda: paths.config_file("gemini_api_key.txt")
    )
    claude_model: str = "claude-opus-5"
    claude_key_file: Path = Field(
        default_factory=lambda: paths.config_file("claude_api_key.txt")
    )
    llm_chunk_size: int = 30
    llm_context_size: int = 15

    # ---- ジョブ ----
    # 置換の長さ上限は積極性(pronoun_level)ごとに違うので pipeline/pronoun.py の
    # LEVELS が持つ。ここに置くと二重管理になり、実際こちらは読まれていなかった
    llm_retries: int = 3


settings = Settings()
