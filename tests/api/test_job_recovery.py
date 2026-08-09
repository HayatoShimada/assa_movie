"""M17: サーバー再起動(--reload等)で中断されたジョブの復旧テスト"""

from backend.jobs.queue import JobQueue, register
from backend.models import schema


@register("noop_m17")
def _noop(conn, media_id, params, progress):
    progress(1.0)


def _make_queue(tmp_path):
    conn = schema.init_db(tmp_path / "m17.db")
    conn.execute("INSERT INTO projects (name) VALUES ('p')")
    conn.execute("INSERT INTO media (project_id, path) VALUES (1, '/tmp/a.mov')")
    conn.commit()
    return conn, JobQueue(conn)


def test_orphaned_running_job_is_marked_failed(tmp_path):
    conn, q = _make_queue(tmp_path)
    # 前回プロセスがrunningのまま死んだ状態を再現
    conn.execute(
        "INSERT INTO jobs (media_id, type, status, progress) VALUES (1, 'noop_m17', 'running', 0.55)"
    )
    conn.commit()

    orphaned = q.recover_orphans()
    assert orphaned == 1
    job = conn.execute("SELECT * FROM jobs WHERE id=1").fetchone()
    assert job["status"] == "failed"
    assert "再起動" in job["error"]  # UIに理由が表示される


def test_orphaned_queued_job_is_requeued_and_runs(tmp_path):
    conn, q = _make_queue(tmp_path)
    conn.execute(
        "INSERT INTO jobs (media_id, type, status) VALUES (1, 'noop_m17', 'queued')"
    )
    conn.commit()

    q.recover_orphans()
    q.start()
    try:
        job = q.wait(1, timeout=10)
        assert job["status"] == "completed"  # queuedは安全に再実行される
    finally:
        q.stop()
    conn.close()


def test_recover_orphans_noop_when_clean(tmp_path):
    conn, q = _make_queue(tmp_path)
    assert q.recover_orphans() == 0
    conn.close()
