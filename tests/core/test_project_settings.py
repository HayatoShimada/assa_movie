"""M12: プロジェクト単位設定・テンプレート(向き)・グローバル設定の永続化のテスト"""

import pytest
from fastapi.testclient import TestClient

from backend.core.project_settings import (
    PROJECT_OVERRIDABLE,
    resolve_settings,
)
from backend.models import schema


@pytest.fixture
def conn(tmp_path):
    c = schema.init_db(tmp_path / "m12_unit.db")
    yield c
    c.close()


# ---- resolve_settings(テーブル駆動) ----

def _make_project(conn, settings_json: str | None = None) -> int:
    cur = conn.execute(
        "INSERT INTO projects (name, settings_json) VALUES ('p', ?)", (settings_json,)
    )
    conn.commit()
    return cur.lastrowid


@pytest.mark.parametrize(
    "name, settings_json, key, expected_is_global",
    [
        ("オーバーライドなし→グローバル値", None, "subtitle_font_size", True),
        ("空JSON→グローバル値", "{}", "subtitle_font_size", True),
        ("オーバーライドあり→その値", '{"subtitle_font_size": 60}', "subtitle_font_size", False),
        ("未知キーは無視される", '{"unknown_key": 1, "subtitle_font_size": 60}', "subtitle_font_size", False),
        ("許可外キー(db_path等)は無視される", '{"db_path": "/tmp/x.db"}', "subtitle_font_size", True),
    ],
)
def test_resolve_settings_table(conn, name, settings_json, key, expected_is_global):
    from backend.core.config import settings as global_settings

    pid = _make_project(conn, settings_json)
    s = resolve_settings(conn, project_id=pid)
    if expected_is_global:
        assert getattr(s, key) == getattr(global_settings, key), name
    else:
        assert getattr(s, key) == 60, name
    # db_pathのような危険項目は常にグローバルのまま
    assert s.db_path == global_settings.db_path


def test_resolve_settings_via_media_id(conn):
    pid = _make_project(conn, '{"subtitle_font_size": 64}')
    cur = conn.execute(
        "INSERT INTO media (project_id, path) VALUES (?, '/tmp/a.mov')", (pid,)
    )
    conn.commit()
    s = resolve_settings(conn, media_id=cur.lastrowid)
    assert s.subtitle_font_size == 64


def test_resolve_settings_without_context_returns_global_copy():
    from backend.core.config import settings as global_settings

    s = resolve_settings()
    assert s.subtitle_font_size == global_settings.subtitle_font_size
    s.subtitle_font_size = 1  # コピーなのでグローバルは汚れない
    assert global_settings.subtitle_font_size != 1


def test_project_overridable_excludes_dangerous_fields():
    assert "db_path" not in PROJECT_OVERRIDABLE
    assert "hf_token_file" not in PROJECT_OVERRIDABLE
    assert "convert_method" in PROJECT_OVERRIDABLE


# ---- プロジェクトAPI(テンプレート・設定) ----

def test_create_project_with_template_and_settings(client):
    r = client.post("/api/projects", json={
        "name": "縦動画",
        "input_orientation": "landscape",
        "output_orientation": "portrait",
        "settings": {"subtitle_font_size": 56, "convert_method": "crop"},
    })
    assert r.status_code == 200
    body = r.json()
    assert body["input_orientation"] == "landscape"
    assert body["output_orientation"] == "portrait"
    assert body["settings"]["subtitle_font_size"] == 56

    got = client.get(f"/api/projects/{body['id']}").json()
    assert got["output_orientation"] == "portrait"
    assert got["settings"]["convert_method"] == "crop"


def test_create_project_defaults_are_landscape(client):
    body = client.post("/api/projects", json={"name": "従来型"}).json()
    assert body["input_orientation"] == "landscape"
    assert body["output_orientation"] == "landscape"
    assert body["settings"] == {}


def test_create_project_rejects_bad_orientation(client):
    r = client.post("/api/projects", json={"name": "x", "output_orientation": "diagonal"})
    assert r.status_code == 422


def test_create_project_rejects_unknown_setting_key(client):
    r = client.post("/api/projects", json={"name": "x", "settings": {"db_path": "/tmp/x"}})
    assert r.status_code == 400


def test_patch_project_settings(client):
    pid = client.post("/api/projects", json={"name": "p"}).json()["id"]
    r = client.patch(f"/api/projects/{pid}", json={
        "output_orientation": "portrait",
        "settings": {"filler_level": "weak"},
    })
    assert r.status_code == 200
    assert r.json()["settings"]["filler_level"] == "weak"
    assert r.json()["output_orientation"] == "portrait"
    # nameは変えていないので維持
    assert r.json()["name"] == "p"


def test_patch_project_settings_replace_clears_old(client):
    pid = client.post("/api/projects", json={
        "name": "p", "settings": {"subtitle_font_size": 60},
    }).json()["id"]
    r = client.patch(f"/api/projects/{pid}", json={"settings": {}})
    assert r.json()["settings"] == {}


def test_delete_project_cascades(client, tmp_path):
    pid = client.post("/api/projects", json={"name": "消すやつ"}).json()["id"]
    src = tmp_path / "v.mov"
    src.write_bytes(b"x")
    mid = client.post(f"/api/projects/{pid}/media", json={"path": str(src)}).json()["id"]

    r = client.delete(f"/api/projects/{pid}")
    assert r.status_code == 200
    assert client.get(f"/api/projects/{pid}").status_code == 404
    assert client.get(f"/api/media/{mid}").status_code == 404  # CASCADE


def test_delete_project_not_found(client):
    assert client.delete("/api/projects/99999").status_code == 404


# ---- グローバル設定のDB永続化 ----

def test_global_settings_persist_across_restart(tmp_path):
    # singletonの復元は conftest の _isolate_settings が行う
    from backend.app import app
    from backend.core import config

    original = config.settings.subtitle_font_size
    config.settings.db_path = tmp_path / "persist.db"

    with TestClient(app) as c:
        c.patch("/api/settings", json={"subtitle_font_size": 61})
        assert c.get("/api/settings").json()["values"]["subtitle_font_size"] == 61

    # 再起動相当: singletonを既定値に戻してからもう一度起動
    config.settings.subtitle_font_size = original
    with TestClient(app) as c:
        assert c.get("/api/settings").json()["values"]["subtitle_font_size"] == 61


# ---- ジョブ層がグローバルsettingsを直接importしていないことの担保 ----

def test_jobs_do_not_import_global_settings_directly():
    from pathlib import Path

    jobs_dir = Path(__file__).resolve().parents[2] / "backend" / "jobs"
    offenders = [
        p.name for p in jobs_dir.glob("*.py")
        if "from backend.core.config import settings" in p.read_text(encoding="utf-8")
    ]
    assert offenders == [], (
        f"ジョブ層はresolve_settings経由で設定を読むこと(直接import禁止): {offenders}"
    )
