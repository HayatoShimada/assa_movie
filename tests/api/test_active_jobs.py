"""M41: 実行中のジョブを取り直すAPI(GET /api/jobs/active)。

編集画面のタブはジョブIDを自分のstateで持っていたため、処理中にタブを
切り替える(=アンマウントされる)と進捗が消え、ボタンがまた押せる状態に
戻っていた。画面の再読み込みでも同じ。実行中のジョブはバックエンドが
知っているので、画面はここから取り直す。

どの操作のジョブかを画面が見分けられるよう、種別に加えてパラメータも返す
(例: クリップの書き出しと範囲指定の書き出しはどちらも type=export で、
clip_id の有無で分かれる)。
"""

import threading

import pytest

from backend.jobs.queue import register
from tests.helpers import create_media

_gate = threading.Event()


@register("m41_hold")
def _hold(conn, media_id, params, progress):
    progress(0.3, "テスト中")
    _gate.wait(timeout=10)


@register("m41_quick")
def _quick(conn, media_id, params, progress):
    progress(1.0)


@pytest.fixture(autouse=True)
def _open_gate_after(client):
    # clientに依存させて、DBを閉じるより先に関所を開ける
    # (止めたまま閉じるとワーカーが閉じたDBへ書こうとする)
    _gate.clear()
    yield
    _gate.set()
    client.app.state.jobs.wait_idle(timeout=10)


def _wait_status(client, job_id, status, timeout=10.0):
    import time

    deadline = time.time() + timeout
    while time.time() < deadline:
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] == status:
            return job
        time.sleep(0.05)
    raise AssertionError(f"ジョブ{job_id}が{status}にならない: {job}")


def test_実行中と順番待ちのジョブをパラメータ付きで返す(client, tmp_path):
    media_id = create_media(client, tmp_path)["media_id"]
    running = client.post(
        f"/api/media/{media_id}/jobs", json={"type": "m41_hold", "params": {"clip_id": 7}}
    ).json()["id"]
    _wait_status(client, running, "running")
    queued = client.post(
        f"/api/media/{media_id}/jobs", json={"type": "m41_quick", "params": {"scope": "all"}}
    ).json()["id"]

    r = client.get("/api/jobs/active")
    assert r.status_code == 200, r.text
    jobs = {j["id"]: j for j in r.json()}
    assert set(jobs) == {running, queued}

    assert jobs[running]["status"] == "running"
    assert jobs[running]["media_id"] == media_id
    assert jobs[running]["type"] == "m41_hold"
    assert jobs[running]["params"] == {"clip_id": 7}
    # 実行中の進捗と工程名はメモリにある。取り直した直後のバーにもそれを出す
    assert jobs[running]["progress"] == pytest.approx(0.3)
    assert jobs[running]["phase"] == "テスト中"

    assert jobs[queued]["status"] == "queued"
    assert jobs[queued]["params"] == {"scope": "all"}


def test_終わったジョブは含めない(client, tmp_path):
    media_id = create_media(client, tmp_path)["media_id"]
    done = client.post(
        f"/api/media/{media_id}/jobs", json={"type": "m41_quick", "params": {}}
    ).json()["id"]
    _wait_status(client, done, "completed")
    held = client.post(
        f"/api/media/{media_id}/jobs", json={"type": "m41_hold", "params": {}}
    ).json()["id"]
    queued = client.post(
        f"/api/media/{media_id}/jobs", json={"type": "m41_quick", "params": {}}
    ).json()["id"]
    _wait_status(client, held, "running")
    client.post(f"/api/jobs/{queued}/cancel")  # 待機中の中止はその場で確定する
    _wait_status(client, queued, "cancelled")
    _gate.set()
    _wait_status(client, held, "completed")

    assert client.get("/api/jobs/active").json() == []


def test_メディアに紐づかないジョブも返す(client):
    """セットアップ(モデル取得)は media_id が無い。設定タブもここから取り直す"""
    job_id = client.app.state.jobs.enqueue(None, "m41_hold", {})
    _wait_status(client, job_id, "running")

    jobs = client.get("/api/jobs/active").json()
    assert [(j["id"], j["media_id"]) for j in jobs] == [(job_id, None)]


def test_個別のジョブ取得にもパラメータが付く(client, tmp_path):
    """/api/jobs/active と /api/jobs/{id} で形を揃える(フロントは同じ Job 型で扱う)"""
    media_id = create_media(client, tmp_path)["media_id"]
    job = client.post(
        f"/api/media/{media_id}/jobs", json={"type": "m41_quick", "params": {"clip_id": 3}}
    ).json()
    assert job["params"] == {"clip_id": 3}
    assert client.get(f"/api/jobs/{job['id']}").json()["params"] == {"clip_id": 3}
