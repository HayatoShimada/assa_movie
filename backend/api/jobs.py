"""ジョブ投入と進捗(SSE)のAPI。"""

import sqlite3

from fastapi import APIRouter, Depends, HTTPException
from sse_starlette.sse import EventSourceResponse

from backend.api.deps import get_db, get_jobs
from backend.jobs.progress import job_events
from backend.jobs.queue import JobQueue
from backend.models.dto import Job, JobCreate

router = APIRouter(prefix="/api", tags=["jobs"])


@router.post("/media/{media_id}/jobs", response_model=Job)
def create_job(
    media_id: int,
    body: JobCreate,
    db: sqlite3.Connection = Depends(get_db),
    jobs: JobQueue = Depends(get_jobs),
):
    if db.execute("SELECT 1 FROM media WHERE id=?", (media_id,)).fetchone() is None:
        raise HTTPException(404, "メディアが見つかりません")
    try:
        job_id = jobs.enqueue(media_id, body.type, body.params)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return _to_job(jobs.get(job_id))


@router.post("/jobs/{job_id}/cancel", response_model=Job)
def cancel_job(job_id: int, jobs: JobQueue = Depends(get_jobs)):
    """実行中・待機中のジョブを中止する。

    文字起こしは数十分かかることがあるので、間違えて始めたときに
    待つしかない状態にしない。既に終わっているジョブは404にせず、
    現在の状態をそのまま返す(利用者の操作は「もう止まっている」で足りる)。
    """
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(404, "ジョブが見つかりません")
    jobs.cancel(job_id)
    return _to_job(jobs.get(job_id))


def _to_job(job: dict) -> Job:
    import json

    job = dict(job)
    job.pop("params_json", None)
    job["result"] = json.loads(job.pop("result_json", None) or "null")
    return Job(**job)


@router.get("/jobs/{job_id}", response_model=Job)
def get_job(job_id: int, jobs: JobQueue = Depends(get_jobs)):
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(404, "ジョブが見つかりません")
    return _to_job(job)


@router.get("/jobs/{job_id}/events")
async def job_progress_events(job_id: int, jobs: JobQueue = Depends(get_jobs)):
    if jobs.get(job_id) is None:
        raise HTTPException(404, "ジョブが見つかりません")
    return EventSourceResponse(job_events(jobs, job_id))
