"""APIの共通依存(DB接続・ジョブキュー)。

FastAPIはリクエストをスレッドプールで並行処理するため、単一のSQLite接続を
使い回すと並行アクセスでクラッシュする(SystemError)。リクエストごとに
専用接続を開き、共有接続(app.state.db)はJobQueueの台帳専用にする。
"""

import sqlite3
from collections.abc import Iterator

from fastapi import Request

from backend.core.config import settings
from backend.jobs.queue import JobQueue
from backend.models import schema


def get_db(request: Request) -> Iterator[sqlite3.Connection]:
    conn = schema.connect(settings.db_path)
    try:
        yield conn
    finally:
        conn.close()


def get_jobs(request: Request) -> JobQueue:
    return request.app.state.jobs
