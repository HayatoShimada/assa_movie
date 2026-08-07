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
            self._progress[job_id] = round(p, 4)

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

                self._update(job_id, status="running", progress=0.0)
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
                    self._update(
                        job_id, status="failed",
                        error=f"{type(e).__name__}: {e}\n{traceback.format_exc()[-2000:]}",
                    )
                finally:
                    with self.lock:
                        self._progress.pop(job_id, None)
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
