"""SQLiteスキーマ定義と接続管理。BACKEND_DESIGN.md「データモデル」と対応。"""

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    name               TEXT NOT NULL,
    -- テンプレート(縦→縦/横→縦/横→横/縦→横)は入力・出力の向きの組で表現する
    input_orientation  TEXT NOT NULL DEFAULT 'landscape',
    output_orientation TEXT NOT NULL DEFAULT 'landscape',
    -- グローバル設定との差分のみを持つ(core/project_settings.py参照)
    settings_json      TEXT,
    created_at         TEXT NOT NULL DEFAULT (datetime('now'))
);

-- UIで変更したグローバル設定の永続化(key単位のupsert)
CREATE TABLE IF NOT EXISTS app_settings (
    key        TEXT PRIMARY KEY,
    value_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS media (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    path       TEXT NOT NULL,
    duration   REAL,
    status     TEXT NOT NULL DEFAULT 'registered',
    brief_json TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS segments (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    media_id              INTEGER NOT NULL REFERENCES media(id) ON DELETE CASCADE,
    idx                   INTEGER NOT NULL,
    start                 REAL NOT NULL,
    end                   REAL NOT NULL,
    text                  TEXT NOT NULL,
    original_text         TEXT NOT NULL,
    speaker               TEXT,
    is_aizuchi            INTEGER NOT NULL DEFAULT 0,
    edited_by_user        INTEGER NOT NULL DEFAULT 0,
    asr_confidence        REAL,
    subtitle_show         TEXT NOT NULL DEFAULT 'auto_show',
    subtitle_reasons_json TEXT,
    words_json            TEXT,
    filler_candidates_json TEXT,
    UNIQUE (media_id, idx)
);

CREATE TABLE IF NOT EXISTS edits (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    media_id    INTEGER NOT NULL REFERENCES media(id) ON DELETE CASCADE,
    segment_id  INTEGER NOT NULL REFERENCES segments(id) ON DELETE CASCADE,
    kind        TEXT NOT NULL DEFAULT 'pronoun',
    original    TEXT NOT NULL,
    replacement TEXT NOT NULL,
    referent    TEXT,
    status      TEXT NOT NULL DEFAULT 'proposed',
    confidence  TEXT NOT NULL DEFAULT 'review',
    created_by  TEXT NOT NULL DEFAULT 'llm',
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS llm_instructions (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    media_id   INTEGER REFERENCES media(id) ON DELETE CASCADE,
    scope      TEXT NOT NULL DEFAULT 'all',
    text       TEXT NOT NULL,
    enabled    INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS glossary (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id  INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    term        TEXT NOT NULL,
    reading     TEXT,
    description TEXT
);

CREATE TABLE IF NOT EXISTS feedback (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    media_id   INTEGER NOT NULL REFERENCES media(id) ON DELETE CASCADE,
    edit_id    INTEGER REFERENCES edits(id) ON DELETE SET NULL,
    kind       TEXT NOT NULL,
    before     TEXT NOT NULL,
    after      TEXT,
    note       TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS questions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    media_id        INTEGER NOT NULL REFERENCES media(id) ON DELETE CASCADE,
    kind            TEXT NOT NULL,
    target_json     TEXT NOT NULL,
    question_text   TEXT NOT NULL,
    candidates_json TEXT,
    status          TEXT NOT NULL DEFAULT 'open',
    answer          TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS clips (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    media_id           INTEGER NOT NULL REFERENCES media(id) ON DELETE CASCADE,
    start              REAL NOT NULL,
    end                REAL NOT NULL,
    title              TEXT,
    hook_text          TEXT,
    score              REAL,
    score_reasons_json TEXT,
    layout             TEXT NOT NULL DEFAULT 'landscape',
    subtitle_position  TEXT NOT NULL DEFAULT 'bottom',
    subtitle_offset_y  INTEGER NOT NULL DEFAULT 0,
    template_id        INTEGER REFERENCES templates(id) ON DELETE SET NULL,
    target_duration    REAL,
    meta_json          TEXT,
    status             TEXT NOT NULL DEFAULT 'draft'
);

CREATE TABLE IF NOT EXISTS clip_cuts (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    clip_id INTEGER NOT NULL REFERENCES clips(id) ON DELETE CASCADE,
    start   REAL NOT NULL,
    end     REAL NOT NULL,
    source  TEXT NOT NULL DEFAULT 'manual',
    active  INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS templates (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    name                 TEXT NOT NULL,
    subtitle_style_json  TEXT,
    layout               TEXT NOT NULL DEFAULT 'landscape',
    target_duration      REAL
);

CREATE TABLE IF NOT EXISTS jobs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    media_id    INTEGER REFERENCES media(id) ON DELETE CASCADE,
    type        TEXT NOT NULL,
    params_json TEXT,
    status      TEXT NOT NULL DEFAULT 'queued',
    progress    REAL NOT NULL DEFAULT 0.0,
    error       TEXT,
    result_json TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_segments_media ON segments(media_id, idx);
CREATE INDEX IF NOT EXISTS idx_edits_media    ON edits(media_id, status);
CREATE INDEX IF NOT EXISTS idx_jobs_status    ON jobs(status, id);
"""


def connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    # APIスレッドとジョブワーカーの別接続が書き込みで衝突しても待てるようにする
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


# 後から追加された列(既存DBにはALTERで足す)
_MIGRATIONS = [
    ("media", "brief_json", "TEXT"),
    ("segments", "filler_candidates_json", "TEXT"),
    ("jobs", "result_json", "TEXT"),
    ("clips", "meta_json", "TEXT"),
    ("clips", "subtitle_position", "TEXT NOT NULL DEFAULT 'bottom'"),
    ("clips", "subtitle_offset_y", "INTEGER NOT NULL DEFAULT 0"),
    ("projects", "input_orientation", "TEXT NOT NULL DEFAULT 'landscape'"),
    ("projects", "output_orientation", "TEXT NOT NULL DEFAULT 'landscape'"),
    ("projects", "settings_json", "TEXT"),
    ("media", "width", "INTEGER"),
    ("media", "height", "INTEGER"),
    # NULL=プロジェクト既定に従う(クリップ単位の上書き)
    ("clips", "convert_method", "TEXT"),
    ("clips", "crop_x", "REAL NOT NULL DEFAULT 0.5"),
]


def init_db(db_path: Path) -> sqlite3.Connection:
    """スキーマを作成(既存なら何もしない)して接続を返す"""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(db_path)
    conn.executescript(SCHEMA)
    for table, column, coltype in _MIGRATIONS:
        cols = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
        if column not in cols:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}")
    _release_pinned_asr_engine(conn)
    conn.commit()
    return conn


# 一度だけ行う移行の記録に使うキー(app_settingsに置く)
_ASR_ENGINE_MIGRATION = "_migrated_asr_engine_auto"


def _release_pinned_asr_engine(conn: sqlite3.Connection) -> None:
    """初回セットアップが固定した asr_engine を外し、autoに戻す(一度だけ)。

    v0.9.5のウィザードは「推奨設定を適用」で asr_engine を具体名で保存していた。
    その後 whisper.cpp を同梱してもエンジンの選択がその値に固定されたままになり、
    GPUがあっても遅いエンジンが使われ続ける(実機で確認)。
    利用者が選んだ値ではなくこちらが書いた値なので、一度だけ解除する。

    以降に利用者が明示的に選んだ値は残る(記録キーがあるので再実行しない)。
    """
    done = conn.execute(
        "SELECT 1 FROM app_settings WHERE key=?", (_ASR_ENGINE_MIGRATION,)
    ).fetchone()
    if done:
        return
    conn.execute("DELETE FROM app_settings WHERE key='asr_engine'")
    conn.execute(
        "INSERT INTO app_settings (key, value_json) VALUES (?, 'true')"
        " ON CONFLICT(key) DO NOTHING",
        (_ASR_ENGINE_MIGRATION,),
    )
