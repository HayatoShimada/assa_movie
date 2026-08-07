"""FastAPIアプリ本体。"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from backend.api import assist as assist_api
from backend.api import edits as edits_api
from backend.api import jobs as jobs_api
from backend.api import projects as projects_api
from backend.api import questions as questions_api
from backend.api import settings_api
from backend.api import transcripts as transcripts_api
from backend.core.config import settings
from backend.jobs import export_job  # noqa: F401  ジョブハンドラの登録に必要
from backend.jobs import filler_job  # noqa: F401
from backend.jobs import judge_job  # noqa: F401
from backend.jobs import resolve_job  # noqa: F401
from backend.jobs import terms_job  # noqa: F401
from backend.jobs import transcribe_job  # noqa: F401
from backend.jobs.queue import JobQueue
from backend.models import schema


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.db = schema.init_db(settings.db_path)
    app.state.jobs = JobQueue(app.state.db)
    app.state.jobs.start()
    yield
    app.state.jobs.stop()
    app.state.db.close()


app = FastAPI(title="Attention Subtitle Separate Application", lifespan=lifespan)
app.include_router(projects_api.router)
app.include_router(jobs_api.router)
app.include_router(transcripts_api.router)
app.include_router(settings_api.router)
app.include_router(edits_api.router)
app.include_router(questions_api.router)
app.include_router(assist_api.router)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}
