"""APIの共通依存(DB接続・ジョブキュー)。"""

import sqlite3

from fastapi import Request

from backend.jobs.queue import JobQueue


def get_db(request: Request) -> sqlite3.Connection:
    return request.app.state.db


def get_jobs(request: Request) -> JobQueue:
    return request.app.state.jobs
