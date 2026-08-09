"""M37: ジョブの中止と、削除時のプロセス停止。

文字起こしは数十分かかることがある。間違えて始めたら止められる必要がある。
またプロジェクトを削除するとき、走っているジョブを止めずに消すと、
whisper-cliやffmpegが動画ファイルを掴んだまま残る(実測。DBからは消えるが
uploadsの削除は静かに失敗し、CPUも取られたままになる)。

止め方は2つ要る:
  - 進捗通知の時点で JobCancelled を送出する(ハンドラ側に分岐を書かせない)
  - 子プロセスを直接殺す(whisper-cli等は制御を返さないのでフラグでは止まらない)
"""

import threading
import time

import pytest

from backend.core.cancellation import JobCancelled
from backend.jobs.queue import JobQueue, register
from backend.models import schema


@pytest.fixture
def jobs(tmp_path):
    conn = schema.init_db(tmp_path / "t.db")
    q = JobQueue(conn)
    q.start()
    yield q
    q.stop()
    conn.close()


def _wait(q, job_id, statuses, timeout=10.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = q.get(job_id)
        if job and job["status"] in statuses:
            return job
        time.sleep(0.05)
    return q.get(job_id)


# ---- 実行中の中止 ----
def test_実行中のジョブを中止できる(jobs):
    started = threading.Event()

    @register("m37_long")
    def _long(conn, media_id, params, progress):
        started.set()
        for i in range(200):
            progress(i / 200)  # ここで JobCancelled が送出される
            time.sleep(0.02)

    job_id = jobs.enqueue(None, "m37_long", {})
    assert started.wait(5), "ジョブが始まらない"

    assert jobs.cancel(job_id) is True

    job = _wait(jobs, job_id, {"cancelled", "failed", "completed"})
    assert job["status"] == "cancelled", f"失敗扱いになっている: {job.get('error')}"


def test_中止したジョブはfailedにしない(jobs):
    """子プロセスを殺すとハンドラは別の例外を投げる。中止として扱う"""

    @register("m37_raises")
    def _raises(conn, media_id, params, progress):
        progress(0.1)
        time.sleep(0.3)
        raise RuntimeError("プロセスが殺されたときに出るような例外")

    job_id = jobs.enqueue(None, "m37_raises", {})
    time.sleep(0.2)
    jobs.cancel(job_id)

    job = _wait(jobs, job_id, {"cancelled", "failed"})
    assert job["status"] == "cancelled"
    assert not job["error"], "中止に失敗理由を残さない"


# ---- 待機中の中止 ----
def test_待機中のジョブを中止すると実行されない(jobs):
    ran = threading.Event()
    block = threading.Event()

    @register("m37_block")
    def _block(conn, media_id, params, progress):
        block.wait(timeout=5)

    @register("m37_second")
    def _second(conn, media_id, params, progress):
        ran.set()

    first = jobs.enqueue(None, "m37_block", {})
    second = jobs.enqueue(None, "m37_second", {})
    time.sleep(0.2)  # 1つ目が走り出すのを待つ

    assert jobs.cancel(second) is True
    assert jobs.get(second)["status"] == "cancelled"

    block.set()
    _wait(jobs, first, {"completed", "cancelled", "failed"})
    time.sleep(0.3)
    assert not ran.is_set(), "中止したジョブが実行された"


# ---- 終わったジョブ ----
def test_終わったジョブは中止できない(jobs):
    @register("m37_quick")
    def _quick(conn, media_id, params, progress):
        return

    job_id = jobs.enqueue(None, "m37_quick", {})
    _wait(jobs, job_id, {"completed"})
    assert jobs.cancel(job_id) is False
    assert jobs.get(job_id)["status"] == "completed"


def test_存在しないジョブは中止できない(jobs):
    assert jobs.cancel(9999) is False


# ---- 子プロセスの停止 ----
class FakeProc:
    def __init__(self):
        self.killed = False

    def kill(self):
        self.killed = True


def test_登録した子プロセスを止める(jobs):
    from backend.core import cancellation

    proc = FakeProc()
    started = threading.Event()

    @register("m37_proc")
    def _proc(conn, media_id, params, progress):
        cancellation.register_process(proc)
        started.set()
        for i in range(200):
            progress(i / 200)
            time.sleep(0.02)

    job_id = jobs.enqueue(None, "m37_proc", {})
    assert started.wait(5)
    jobs.cancel(job_id)
    _wait(jobs, job_id, {"cancelled", "failed"})

    assert proc.killed, "子プロセスが止められていない"


def test_中止後に登録された子プロセスも止める(jobs):
    """kill要求と登録が競っても取りこぼさない"""
    proc = FakeProc()
    jobs._cancelled.add(1234)
    jobs.attach_process(1234, proc)
    assert proc.killed


def test_ジョブ以外から呼んでも落ちない():
    """CLIやテストから同じ関数を通ることがある"""
    from backend.core import cancellation

    cancellation.unbind()
    cancellation.register_process(FakeProc())  # 例外が出ないこと


# ---- 削除の前処理 ----
def test_メディア指定でまとめて中止できる(jobs):
    started = threading.Event()

    @register("m37_media")
    def _media(conn, media_id, params, progress):
        started.set()
        for i in range(200):
            progress(i / 200)
            time.sleep(0.02)

    jobs.conn.execute("INSERT INTO projects (name) VALUES ('p')")
    jobs.conn.execute("INSERT INTO media (project_id, path) VALUES (1, 'x')")
    jobs.conn.commit()

    job_id = jobs.enqueue(1, "m37_media", {})
    assert started.wait(5)

    assert jobs.cancel_for_media([1]) == 1
    job = _wait(jobs, job_id, {"cancelled", "failed"})
    assert job["status"] == "cancelled"


def test_wait_idleは実行中が無くなると戻る(jobs):
    assert jobs.wait_idle(timeout=2.0) is True


def test_JobCancelledは進捗通知から送出される(jobs):
    """ハンドラ側に中止の分岐を書かせない設計であることの確認"""
    seen = {}

    @register("m37_catch")
    def _catch(conn, media_id, params, progress):
        progress(0.1)
        time.sleep(0.3)
        try:
            progress(0.2)
        except JobCancelled:
            seen["raised"] = True
            raise

    job_id = jobs.enqueue(None, "m37_catch", {})
    time.sleep(0.2)
    jobs.cancel(job_id)
    _wait(jobs, job_id, {"cancelled", "failed"})
    assert seen.get("raised") is True
