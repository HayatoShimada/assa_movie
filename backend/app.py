"""FastAPIアプリ本体。"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from backend.core.config import settings
from backend.models import schema


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.db = schema.init_db(settings.db_path)
    yield
    app.state.db.close()


app = FastAPI(title="Attention Subtitle Separate Application", lifespan=lifespan)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}
