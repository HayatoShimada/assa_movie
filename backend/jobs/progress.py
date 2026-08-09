"""ジョブ進捗のSSE配信。DBを1秒ポーリングして変化があれば送る。"""

import asyncio
import json
from typing import AsyncIterator

from backend.jobs.queue import JobQueue

POLL_INTERVAL = 1.0


async def job_events(jobs: JobQueue, job_id: int) -> AsyncIterator[dict]:
    """進捗イベントを yield する。終端状態になったら終了する。"""
    last: tuple | None = None
    while True:
        job = jobs.get(job_id)
        if job is None:
            yield {"event": "error", "data": json.dumps({"error": "job not found"})}
            return

        current = (job["status"], job["progress"])
        if current != last:
            last = current
            yield {
                "event": "progress",
                "data": json.dumps(
                    {
                        "job_id": job_id,
                        "status": job["status"],
                        "progress": job["progress"],
                        "error": job["error"],
                    },
                    ensure_ascii=False,
                ),
            }

        if job["status"] in ("completed", "failed", "cancelled"):
            return
        await asyncio.sleep(POLL_INTERVAL)
