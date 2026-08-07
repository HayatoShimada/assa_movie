"""プロジェクトとメディアの登録API。"""

import shutil
import sqlite3
import subprocess
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from backend.api.deps import get_db
from backend.models.dto import Media, MediaCreate, Project, ProjectCreate

router = APIRouter(prefix="/api", tags=["projects"])


def probe_duration(path: Path) -> float | None:
    """ffprobeで再生時間を取得する(取れなければNone)"""
    if not shutil.which("ffprobe"):
        return None
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            capture_output=True, text=True, timeout=60,
        )
        return float(out.stdout.strip()) if out.returncode == 0 else None
    except (ValueError, subprocess.SubprocessError):
        return None


@router.post("/projects", response_model=Project)
def create_project(body: ProjectCreate, db: sqlite3.Connection = Depends(get_db)):
    cur = db.execute("INSERT INTO projects (name) VALUES (?)", (body.name,))
    db.commit()
    row = db.execute("SELECT * FROM projects WHERE id=?", (cur.lastrowid,)).fetchone()
    return Project(**dict(row))


@router.get("/projects", response_model=list[Project])
def list_projects(db: sqlite3.Connection = Depends(get_db)):
    rows = db.execute("SELECT * FROM projects ORDER BY id DESC").fetchall()
    return [Project(**dict(r)) for r in rows]


@router.post("/projects/{project_id}/media", response_model=Media)
def add_media(
    project_id: int, body: MediaCreate, db: sqlite3.Connection = Depends(get_db)
):
    if db.execute("SELECT 1 FROM projects WHERE id=?", (project_id,)).fetchone() is None:
        raise HTTPException(404, "プロジェクトが見つかりません")

    path = Path(body.path).expanduser()
    if not path.exists():
        raise HTTPException(400, f"ファイルが存在しません: {path}")

    cur = db.execute(
        "INSERT INTO media (project_id, path, duration) VALUES (?,?,?)",
        (project_id, str(path.resolve()), probe_duration(path)),
    )
    db.commit()
    row = db.execute("SELECT * FROM media WHERE id=?", (cur.lastrowid,)).fetchone()
    return Media(**dict(row))


@router.get("/projects/{project_id}/media", response_model=list[Media])
def list_media(project_id: int, db: sqlite3.Connection = Depends(get_db)):
    rows = db.execute(
        "SELECT * FROM media WHERE project_id=? ORDER BY id", (project_id,)
    ).fetchall()
    return [Media(**dict(r)) for r in rows]
