"""設定の3層解決(グローバル既定 → プロジェクト上書き → ジョブparams)。

- グローバル設定はUIで変更されると app_settings テーブルに永続化される
- プロジェクトは projects.settings_json にグローバルとの差分だけを持つ
  (差分方式なので、未上書き項目はグローバル変更に自動追従する)
- ジョブ・APIは resolve_settings() で解決済みSettingsを受け取り、
  グローバルsingletonを直接importしない(tests/test_m12参照)
"""

import json
import sqlite3

from backend.core.config import Settings, settings

# UIから変更可能な項目(誤ってDBパス等を書き換えられないよう明示的に許可する)
MUTABLE_FIELDS = {
    "asr_model", "asr_engine", "asr_language", "asr_beam_size", "asr_vad_filter",
    "diarization_enabled", "diarization_engine",
    "num_speakers", "male_name", "female_name",
    "aizuchi_filter_enabled", "aizuchi_max_duration",
    "filler_level",
    "pronoun_enabled", "pronoun_level", "pronoun_form", "pronoun_apply_mode",
    "subtitle_mode", "subtitle_adoption_rate",
    "subtitle_font_size", "subtitle_position", "subtitle_offset_y",
    "subtitle_max_chars_per_line", "subtitle_max_lines",
    "subtitle_font_family", "subtitle_text_color", "subtitle_speaker_colors",
    "subtitle_bg", "subtitle_bg_color", "subtitle_bg_opacity",
    "convert_method",
    "llm_provider", "ollama_model", "gemini_model",
    "vram_budget_mb",
}

# プロジェクト単位で上書きできる項目。
# VRAM割当はマシン全体の資源なのでプロジェクト単位化しない
PROJECT_OVERRIDABLE = set(MUTABLE_FIELDS) - {"vram_budget_mb"}


def project_overrides(conn: sqlite3.Connection, project_id: int) -> dict:
    """プロジェクトの設定差分(許可項目のみ)を返す"""
    row = conn.execute(
        "SELECT settings_json FROM projects WHERE id=?", (project_id,)
    ).fetchone()
    if row is None or not row["settings_json"]:
        return {}
    try:
        raw = json.loads(row["settings_json"])
    except (json.JSONDecodeError, TypeError):
        return {}
    return {k: v for k, v in raw.items() if k in PROJECT_OVERRIDABLE}


def resolve_settings(
    conn: sqlite3.Connection | None = None,
    *,
    project_id: int | None = None,
    media_id: int | None = None,
) -> Settings:
    """グローバル設定のコピーにプロジェクト差分を適用して返す。

    コンテキスト無し(conn=None)でもグローバルのコピーを返すので、
    呼び出し側は常にこの戻り値だけを見ればよい。
    """
    if conn is not None and media_id is not None and project_id is None:
        row = conn.execute(
            "SELECT project_id FROM media WHERE id=?", (media_id,)
        ).fetchone()
        project_id = row["project_id"] if row else None
    overrides = {}
    if conn is not None and project_id is not None:
        overrides = project_overrides(conn, project_id)
    return settings.model_copy(update=overrides)


def load_global_overrides(conn: sqlite3.Connection) -> None:
    """起動時にDB保存値をグローバルsingletonへ適用する。

    優先順位: pydantic既定 < .env/環境変数 < DB保存値(UIでの最終操作が勝つ)
    """
    try:
        rows = conn.execute("SELECT key, value_json FROM app_settings").fetchall()
    except sqlite3.OperationalError:
        return
    for r in rows:
        if r["key"] in MUTABLE_FIELDS:
            try:
                setattr(settings, r["key"], json.loads(r["value_json"]))
            except (json.JSONDecodeError, ValueError):
                continue


def save_global_overrides(conn: sqlite3.Connection, changes: dict) -> None:
    """UIで変更されたグローバル設定をDBへ永続化する"""
    for key, value in changes.items():
        conn.execute(
            "INSERT INTO app_settings (key, value_json) VALUES (?,?)"
            " ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json",
            (key, json.dumps(value, ensure_ascii=False)),
        )
    conn.commit()
