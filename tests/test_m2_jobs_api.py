"""M2: ジョブ基盤とAPIのテスト"""

import json
import threading
import time

import pytest
from fastapi.testclient import TestClient

from backend.jobs.queue import JobQueue, register
from backend.models import schema


@pytest.fixture
def db(tmp_path):
    conn = schema.init_db(tmp_path / "m2.db")
    yield conn
    conn.close()


@pytest.fixture
def jobs(db):
    q = JobQueue(db)
    q.start()
    yield q
    q.stop()


# ---- ジョブハンドラ(テスト専用) ----
_order: list[str] = []


@register("test_ok")
def _handler_ok(conn, media_id, params, progress):
    progress(0.5)
    _order.append(params.get("tag", "?"))
    time.sleep(params.get("sleep", 0))
    progress(1.0)


@register("test_fail")
def _handler_fail(conn, media_id, params, progress):
    raise RuntimeError("意図的な失敗")


def test_job_runs_and_completes(jobs):
    job_id = jobs.enqueue(None, "test_ok", {"tag": "a"})
    job = jobs.wait(job_id, timeout=10)
    assert job["status"] == "completed"
    assert job["progress"] == 1.0


def test_jobs_run_serially_in_order(jobs):
    _order.clear()
    ids = [jobs.enqueue(None, "test_ok", {"tag": t, "sleep": 0.05}) for t in "abc"]
    for i in ids:
        jobs.wait(i, timeout=10)
    assert _order == ["a", "b", "c"]  # GPUジョブ前提なので直列実行


def test_failed_job_records_error(jobs):
    job_id = jobs.enqueue(None, "test_fail", {})
    job = jobs.wait(job_id, timeout=10)
    assert job["status"] == "failed"
    assert "意図的な失敗" in job["error"]


def test_enqueue_unknown_type_raises(jobs):
    with pytest.raises(ValueError):
        jobs.enqueue(None, "no_such_job", {})


def test_progress_is_persisted(db):
    q = JobQueue(db)
    seen = threading.Event()

    @register("test_progress")
    def _h(conn, media_id, params, progress):
        progress(0.42)
        seen.wait(timeout=5)  # 進捗が読めるまで止める

    q.start()
    try:
        job_id = q.enqueue(None, "test_progress", {})
        deadline = time.time() + 5
        while time.time() < deadline and q.get(job_id)["progress"] != 0.42:
            time.sleep(0.02)
        assert q.get(job_id)["progress"] == 0.42
    finally:
        seen.set()
        q.stop()


# ---- API ----
@pytest.fixture
def client(tmp_path, monkeypatch):
    from backend.core import config

    monkeypatch.setattr(config.settings, "db_path", tmp_path / "api.db")
    from backend.app import app

    with TestClient(app) as c:
        yield c


def _make_media(client, tmp_path) -> int:
    pid = client.post("/api/projects", json={"name": "p"}).json()["id"]
    media_file = tmp_path / "sample.wav"
    media_file.write_bytes(b"RIFF____WAVE")
    r = client.post(f"/api/projects/{pid}/media", json={"path": str(media_file)})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def test_create_project_and_media(client, tmp_path):
    media_id = _make_media(client, tmp_path)
    assert media_id > 0
    projects = client.get("/api/projects").json()
    assert len(projects) == 1


def test_add_media_rejects_missing_file(client):
    pid = client.post("/api/projects", json={"name": "p"}).json()["id"]
    r = client.post(f"/api/projects/{pid}/media", json={"path": "/no/such/file.mov"})
    assert r.status_code == 400


def test_add_media_rejects_unknown_project(client, tmp_path):
    f = tmp_path / "a.wav"
    f.write_bytes(b"x")
    assert client.post("/api/projects/999/media", json={"path": str(f)}).status_code == 404


def test_create_job_and_poll(client, tmp_path):
    media_id = _make_media(client, tmp_path)
    r = client.post(f"/api/media/{media_id}/jobs", json={"type": "test_ok", "params": {}})
    assert r.status_code == 200, r.text
    job_id = r.json()["id"]

    deadline = time.time() + 10
    while time.time() < deadline:
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] == "completed":
            break
        time.sleep(0.05)
    assert job["status"] == "completed"


def test_create_job_rejects_unknown_type(client, tmp_path):
    media_id = _make_media(client, tmp_path)
    r = client.post(f"/api/media/{media_id}/jobs", json={"type": "nope", "params": {}})
    assert r.status_code == 400


def test_job_events_sse_streams_completion(client, tmp_path):
    media_id = _make_media(client, tmp_path)
    job_id = client.post(
        f"/api/media/{media_id}/jobs", json={"type": "test_ok", "params": {}}
    ).json()["id"]

    with client.stream("GET", f"/api/jobs/{job_id}/events") as resp:
        assert resp.status_code == 200
        payloads = []
        for line in resp.iter_lines():
            if line.startswith("data:"):
                payloads.append(json.loads(line[5:].strip()))
                if payloads[-1]["status"] in ("completed", "failed"):
                    break
    assert payloads[-1]["status"] == "completed"
    assert payloads[-1]["progress"] == 1.0


# ---- セグメントAPI ----
def _insert_segment(client, media_id, idx=0, text="これはテスト", speaker="話者1"):
    db = client.app.state.db
    db.execute(
        "INSERT INTO segments (media_id, idx, start, end, text, original_text, speaker,"
        " is_aizuchi, words_json) VALUES (?,?,?,?,?,?,?,?,?)",
        (media_id, idx, 0.0, 1.5, text, text, speaker, 0,
         json.dumps([{"start": 0.0, "end": 1.5, "text": text}])),
    )
    db.commit()
    return db.execute(
        "SELECT id FROM segments WHERE media_id=? AND idx=?", (media_id, idx)
    ).fetchone()["id"]


def test_list_segments(client, tmp_path):
    media_id = _make_media(client, tmp_path)
    _insert_segment(client, media_id)
    segs = client.get(f"/api/media/{media_id}/segments").json()
    assert len(segs) == 1
    assert segs[0]["text"] == "これはテスト"
    assert segs[0]["words"][0]["text"] == "これはテスト"


def test_list_segments_can_exclude_aizuchi(client, tmp_path):
    media_id = _make_media(client, tmp_path)
    _insert_segment(client, media_id, idx=0)
    sid = _insert_segment(client, media_id, idx=1, text="うん")
    client.app.state.db.execute("UPDATE segments SET is_aizuchi=1 WHERE id=?", (sid,))
    client.app.state.db.commit()

    assert len(client.get(f"/api/media/{media_id}/segments").json()) == 2
    filtered = client.get(f"/api/media/{media_id}/segments?include_aizuchi=false").json()
    assert len(filtered) == 1


def test_patch_segment_sets_edited_flag(client, tmp_path):
    media_id = _make_media(client, tmp_path)
    sid = _insert_segment(client, media_id)
    r = client.patch(f"/api/segments/{sid}", json={"text": "修正後", "speaker": "高田さん"})
    assert r.status_code == 200
    body = r.json()
    assert body["text"] == "修正後"
    assert body["speaker"] == "高田さん"
    assert body["edited_by_user"] is True
    assert body["original_text"] == "これはテスト"  # 原文は保持される


def test_patch_segment_rejects_bad_subtitle_show(client, tmp_path):
    media_id = _make_media(client, tmp_path)
    sid = _insert_segment(client, media_id)
    r = client.patch(f"/api/segments/{sid}", json={"subtitle_show": "invalid"})
    assert r.status_code == 400


def test_patch_unknown_segment_404(client):
    assert client.patch("/api/segments/999", json={"text": "x"}).status_code == 404
