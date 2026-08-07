"""M0: 足場のテスト"""

import sqlite3

import pytest
from fastapi.testclient import TestClient

from backend.core.config import Settings
from backend.models import schema

EXPECTED_TABLES = {
    "projects", "media", "segments", "edits", "llm_instructions",
    "glossary", "feedback", "questions", "clips", "clip_cuts",
    "templates", "jobs",
}


@pytest.fixture
def db(tmp_path):
    conn = schema.init_db(tmp_path / "test.db")
    yield conn
    conn.close()


def test_all_tables_created(db):
    rows = db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    names = {r["name"] for r in rows}
    assert EXPECTED_TABLES <= names


def test_init_db_is_idempotent(tmp_path):
    path = tmp_path / "twice.db"
    schema.init_db(path).close()
    conn = schema.init_db(path)  # 二重起動でもエラーにならない
    conn.execute("INSERT INTO projects (name) VALUES ('p')")
    conn.commit()
    assert conn.execute("SELECT COUNT(*) c FROM projects").fetchone()["c"] == 1
    conn.close()


def test_foreign_keys_enforced(db):
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("INSERT INTO media (project_id, path) VALUES (999, '/x.mov')")


def test_segments_unique_per_media(db):
    db.execute("INSERT INTO projects (name) VALUES ('p')")
    db.execute("INSERT INTO media (project_id, path) VALUES (1, '/x.mov')")
    args = (1, 0, 0.0, 1.0, "a", "a")
    db.execute(
        "INSERT INTO segments (media_id, idx, start, end, text, original_text)"
        " VALUES (?,?,?,?,?,?)", args
    )
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO segments (media_id, idx, start, end, text, original_text)"
            " VALUES (?,?,?,?,?,?)", args
        )


def test_health_endpoint(tmp_path, monkeypatch):
    from backend.core import config

    monkeypatch.setattr(config.settings, "db_path", tmp_path / "app.db")
    from backend.app import app

    with TestClient(app) as client:
        assert client.get("/api/health").json() == {"status": "ok"}


def test_settings_env_override(monkeypatch):
    monkeypatch.setenv("WL_ASR_MODEL", "large-v3-turbo")
    monkeypatch.setenv("WL_PRONOUN_LEVEL", "strong")
    s = Settings()
    assert s.asr_model == "large-v3-turbo"
    assert s.pronoun_level == "strong"


def test_settings_defaults_match_design():
    s = Settings(_env_file=None)
    # BACKEND_DESIGN.md の決定事項: 精度優先・単語TS必須のためlarge-v3が既定
    assert s.asr_model == "large-v3"
    assert s.asr_compute_type == "float16"  # Blackwellでint8はクラッシュする
    assert s.pronoun_form == "annotate"      # おすすめ既定: かっこ注釈
