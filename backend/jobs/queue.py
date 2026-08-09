"""ジョブキュー。GPUジョブは直列実行が前提なので単一ワーカーで足りる。

ハンドラは `register(type)` デコレータで登録する。
ハンドラのシグネチャ: (conn, media_id, params, progress) -> None
"""

import json
import queue
import sqlite3
import threading
import traceback
from typing import Callable

from backend.core.cancellation import JobCancelled, bind, unbind

Handler = Callable[[sqlite3.Connection, int | None, dict, Callable[[float], None]], None]

_HANDLERS: dict[str, Handler] = {}


def register(job_type: str):
    def deco(fn: Handler) -> Handler:
        _HANDLERS[job_type] = fn
        return fn

    return deco


class JobQueue:
    """SQLiteのjobsテーブルを台帳に、単一スレッドでジョブを直列処理する"""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        # 台帳接続はワーカースレッドとAPIスレッドで共有するため書き込みを直列化する
        self.lock = threading.Lock()
        self._q: queue.Queue[int] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        # 実行中ジョブの進捗はメモリ保持(ハンドラのトランザクション中に
        # DBへ書くとロック競合するため。終端状態の書き込み時に確定させる)
        self._progress: dict[int, float] = {}
        # 中止を要求されたジョブ。進捗通知の時点で JobCancelled にする
        self._cancelled: set[int] = set()
        # 実行中ジョブが持つ子プロセス。中止時に直接止める
        # (whisper-cli等は走っている間こちらへ制御を返さない)
        self._procs: dict[int, list] = {}

    def recover_orphans(self) -> int:
        """前回プロセスの中断(--reload・強制終了)で残ったジョブを整理する。

        running のまま残ったジョブは再開できないため、明示的に失敗させてUIに伝える。
        queued のものは安全に再実行できるのでキューに積み直す。
        """
        with self.lock:
            cur = self.conn.execute(
                "UPDATE jobs SET status='failed',"
                " error='サーバー再起動により中断されました。再実行してください。'"
                " WHERE status='running'"
            )
            orphaned = cur.rowcount
            requeued = [
                r["id"] for r in self.conn.execute(
                    "SELECT id FROM jobs WHERE status='queued' ORDER BY id"
                )
            ]
            self.conn.commit()
        for job_id in requeued:
            self._q.put(job_id)
        return orphaned

    # ---- 台帳操作(呼び出し側スレッドから) ----
    def enqueue(self, media_id: int | None, job_type: str, params: dict | None = None) -> int:
        if job_type not in _HANDLERS:
            raise ValueError(f"未登録のジョブ種別: {job_type}")
        with self.lock:
            cur = self.conn.execute(
                "INSERT INTO jobs (media_id, type, params_json, status) VALUES (?,?,?,'queued')",
                (media_id, job_type, json.dumps(params or {}, ensure_ascii=False)),
            )
            self.conn.commit()
            job_id = cur.lastrowid
        self._q.put(job_id)
        return job_id

    def cancel(self, job_id: int) -> bool:
        """待機中・実行中のジョブを中止する。終わっているジョブにはFalseを返す。

        子プロセスはその場で止める。フラグだけでは、次に進捗が通知されるまで
        止まらない(whisper-cliは数十分返ってこないことがある)。
        """
        with self.lock:
            row = self.conn.execute(
                "SELECT status FROM jobs WHERE id=?", (job_id,)
            ).fetchone()
            if row is None or row["status"] not in ("queued", "running"):
                return False
            self._cancelled.add(job_id)
            procs = list(self._procs.get(job_id, []))
            was_queued = row["status"] == "queued"

        for proc in procs:
            try:
                proc.kill()
            except Exception:
                pass  # 既に終わっている場合など。中止処理は止めない
        if was_queued:
            # まだ動いていないのでワーカーを待たずに確定させる
            self._update(job_id, status="cancelled", progress=0.0)
        return True

    def cancel_for_media(self, media_ids: list[int]) -> int:
        """指定メディアの未終了ジョブをまとめて中止する(削除の前処理)"""
        if not media_ids:
            return 0
        placeholders = ",".join("?" * len(media_ids))
        with self.lock:
            ids = [
                r["id"] for r in self.conn.execute(
                    f"SELECT id FROM jobs WHERE media_id IN ({placeholders})"
                    " AND status IN ('queued','running')",
                    media_ids,
                )
            ]
        return sum(1 for job_id in ids if self.cancel(job_id))

    def attach_process(self, job_id: int, proc) -> None:
        """実行中ジョブの子プロセスを登録する(backend/core/cancellation.py から)"""
        with self.lock:
            already_cancelled = job_id in self._cancelled
            self._procs.setdefault(job_id, []).append(proc)
        # 登録前に中止されていた場合を取りこぼさない
        if already_cancelled:
            try:
                proc.kill()
            except Exception:
                pass

    def wait_idle(self, timeout: float = 10.0) -> bool:
        """実行中のジョブが無くなるまで待つ。時間内に空になればTrue"""
        import time

        deadline = time.time() + timeout
        while time.time() < deadline:
            with self.lock:
                busy = bool(self._progress)
            if not busy:
                return True
            time.sleep(0.1)
        return False

    def get(self, job_id: int) -> dict | None:
        with self.lock:
            row = self.conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            mem_progress = self._progress.get(job_id)
        if row is None:
            return None
        job = dict(row)
        if mem_progress is not None and job["status"] == "running":
            job["progress"] = mem_progress
        return job

    # ---- ワーカー ----
    def start(self) -> None:
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        self._q.put(-1)  # ワーカーを起こす
        if self._thread:
            self._thread.join(timeout=timeout)
            self._thread = None

    def _set_progress(self, job_id: int, p: float) -> None:
        with self.lock:
            cancelled = job_id in self._cancelled
            self._progress[job_id] = round(p, 4)
        # ハンドラ側に中止の分岐を書かせない。ここで送出すればfinallyが走る
        if cancelled:
            raise JobCancelled()

    def _update(self, job_id: int, **fields) -> None:
        sets = ", ".join(f"{k}=?" for k in fields)
        with self.lock:
            self.conn.execute(
                f"UPDATE jobs SET {sets} WHERE id=?", (*fields.values(), job_id)
            )
            self.conn.commit()

    def _worker_conn(self) -> sqlite3.Connection:
        """ハンドラ用の専用接続を開く。

        APIスレッドと同じ接続でクエリを並行実行するとSQLiteがクラッシュ的な
        SystemErrorを出すことがあるため、ワーカーは自分の接続を持つ
        (台帳操作 enqueue/get/_update は従来どおり共有接続+lock)。
        """
        with self.lock:  # 共有接続への並行アクセスはSystemErrorを起こす
            row = self.conn.execute("PRAGMA database_list").fetchone()
            db_file = row["file"] if row else ""
        if not db_file:  # インメモリDBは接続を分けられないので共有のまま
            return self.conn
        from backend.models import schema

        return schema.connect(db_file)

    def _run(self) -> None:
        conn = self._worker_conn()
        try:
            while not self._stop.is_set():
                job_id = self._q.get()
                if job_id == -1:
                    continue
                job = self.get(job_id)
                if not job or job["status"] != "queued":
                    continue
                with self.lock:
                    cancelled_before_start = job_id in self._cancelled
                if cancelled_before_start:
                    # 待機中に中止された。cancel()が既に確定させている
                    continue

                self._update(job_id, status="running", progress=0.0)
                bind(self, job_id)  # ハンドラから子プロセスを登録できるようにする
                try:
                    handler = _HANDLERS[job["type"]]
                    params = json.loads(job["params_json"] or "{}")
                    handler(
                        conn,
                        job["media_id"],
                        params,
                        lambda p, _id=job_id: self._set_progress(_id, float(p)),
                    )
                    conn.commit()  # ハンドラのcommit漏れでロックを持ち越さない
                    self._update(job_id, status="completed", progress=1.0)
                except Exception as e:
                    # 未完トランザクションを解放しないと台帳更新がロック待ちになる
                    try:
                        conn.rollback()
                    except sqlite3.Error:
                        pass
                    with self.lock:
                        cancelled = job_id in self._cancelled
                    # 子プロセスを殺した結果ハンドラが別の例外を出すことがある。
                    # 中止を要求されていたなら失敗ではなく中止として扱う
                    if cancelled or isinstance(e, JobCancelled):
                        self._update(job_id, status="cancelled")
                    else:
                        self._update(
                            job_id, status="failed",
                            error=f"{type(e).__name__}: {e}\n{traceback.format_exc()[-2000:]}",
                        )
                finally:
                    unbind()
                    with self.lock:
                        self._progress.pop(job_id, None)
                        self._cancelled.discard(job_id)
                        self._procs.pop(job_id, None)
        finally:
            if conn is not self.conn:
                conn.close()

    def wait(self, job_id: int, timeout: float = 60.0) -> dict:
        """テスト用: ジョブが終端状態になるまで待つ"""
        import time

        deadline = time.time() + timeout
        while time.time() < deadline:
            job = self.get(job_id)
            if job and job["status"] in ("completed", "failed"):
                return job
            time.sleep(0.05)
        raise TimeoutError(f"ジョブ {job_id} がタイムアウトしました")
