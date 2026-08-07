"""プロジェクトとメディアの登録API。"""

import shutil
import sqlite3
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from backend.api.deps import get_db
from backend.core.config import settings
from backend.core.project_settings import PROJECT_OVERRIDABLE
from backend.models.dto import Media, MediaCreate, Project, ProjectCreate, ProjectUpdate

router = APIRouter(prefix="/api", tags=["projects"])


def _validate_project_settings(values: dict) -> str:
    """許可キーのみ受け付け、JSON文字列にして返す"""
    unknown = sorted(set(values) - PROJECT_OVERRIDABLE)
    if unknown:
        raise HTTPException(400, f"プロジェクト設定にできない項目です: {', '.join(unknown)}")
    import json

    return json.dumps(values, ensure_ascii=False)


def _to_project(row) -> Project:
    import json

    d = dict(row)
    d["settings"] = json.loads(d.pop("settings_json", None) or "{}")
    return Project(**d)


from backend.pipeline.export import probe_media


@router.post("/projects", response_model=Project)
def create_project(body: ProjectCreate, db: sqlite3.Connection = Depends(get_db)):
    cur = db.execute(
        "INSERT INTO projects (name, input_orientation, output_orientation, settings_json)"
        " VALUES (?,?,?,?)",
        (body.name, body.input_orientation, body.output_orientation,
         _validate_project_settings(body.settings)),
    )
    db.commit()
    row = db.execute("SELECT * FROM projects WHERE id=?", (cur.lastrowid,)).fetchone()
    return _to_project(row)


@router.get("/projects", response_model=list[Project])
def list_projects(db: sqlite3.Connection = Depends(get_db)):
    rows = db.execute("SELECT * FROM projects ORDER BY id DESC").fetchall()
    return [_to_project(r) for r in rows]


@router.get("/projects/{project_id}", response_model=Project)
def get_project(project_id: int, db: sqlite3.Connection = Depends(get_db)):
    row = db.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "プロジェクトが見つかりません")
    return _to_project(row)


@router.patch("/projects/{project_id}", response_model=Project)
def update_project(
    project_id: int, body: ProjectUpdate, db: sqlite3.Connection = Depends(get_db)
):
    row = db.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "プロジェクトが見つかりません")
    updates: list[tuple[str, object]] = []
    if body.name is not None:
        updates.append(("name", body.name))
    if body.input_orientation is not None:
        updates.append(("input_orientation", body.input_orientation))
    if body.output_orientation is not None:
        updates.append(("output_orientation", body.output_orientation))
    if body.settings is not None:
        updates.append(("settings_json", _validate_project_settings(body.settings)))
    if updates:
        sets = ", ".join(f"{k}=?" for k, _ in updates)
        db.execute(
            f"UPDATE projects SET {sets} WHERE id=?",
            (*[v for _, v in updates], project_id),
        )
        db.commit()
    return _to_project(
        db.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
    )


@router.delete("/projects/{project_id}")
def delete_project(project_id: int, db: sqlite3.Connection = Depends(get_db)):
    """プロジェクトを削除する(メディア・セグメント等はFKのCASCADEで連鎖削除)"""
    if db.execute("SELECT 1 FROM projects WHERE id=?", (project_id,)).fetchone() is None:
        raise HTTPException(404, "プロジェクトが見つかりません")
    db.execute("DELETE FROM projects WHERE id=?", (project_id,))
    db.commit()
    # アップロードされた実ファイルも掃除する(外部パス登録のメディアは消さない)
    upload_dir = settings.db_path.parent / "uploads" / f"project_{project_id}"
    if upload_dir.exists():
        shutil.rmtree(upload_dir, ignore_errors=True)
    return {"deleted": project_id}


@router.post("/projects/{project_id}/media", response_model=Media)
def add_media(
    project_id: int, body: MediaCreate, db: sqlite3.Connection = Depends(get_db)
):
    if db.execute("SELECT 1 FROM projects WHERE id=?", (project_id,)).fetchone() is None:
        raise HTTPException(404, "プロジェクトが見つかりません")

    path = Path(body.path).expanduser()
    if not path.exists():
        raise HTTPException(400, f"ファイルが存在しません: {path}")

    duration, width, height = probe_media(path)
    cur = db.execute(
        "INSERT INTO media (project_id, path, duration, width, height) VALUES (?,?,?,?,?)",
        (project_id, str(path.resolve()), duration, width, height),
    )
    db.commit()
    row = db.execute("SELECT * FROM media WHERE id=?", (cur.lastrowid,)).fetchone()
    return Media(**dict(row))


@router.post("/projects/{project_id}/media/upload", response_model=Media)
async def upload_media(
    project_id: int,
    file: UploadFile = File(...),
    db: sqlite3.Connection = Depends(get_db),
):
    if db.execute("SELECT 1 FROM projects WHERE id=?", (project_id,)).fetchone() is None:
        raise HTTPException(404, "プロジェクトが見つかりません")

    filename = Path(file.filename or "uploaded_media").name
    upload_dir = settings.db_path.parent / "uploads" / f"project_{project_id}"
    upload_dir.mkdir(parents=True, exist_ok=True)
    saved_path = upload_dir / f"{uuid.uuid4().hex}_{filename}"

    with saved_path.open("wb") as f:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            f.write(chunk)
    await file.close()

    duration, width, height = probe_media(saved_path)
    cur = db.execute(
        "INSERT INTO media (project_id, path, duration, width, height) VALUES (?,?,?,?,?)",
        (project_id, str(saved_path.resolve()), duration, width, height),
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


@router.get("/media/{media_id}", response_model=Media)
def get_media(media_id: int, db: sqlite3.Connection = Depends(get_db)):
    row = db.execute("SELECT * FROM media WHERE id=?", (media_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "メディアが見つかりません")
    return Media(**dict(row))


class Brief(BaseModel):
    theme: str = ""    # 動画全体の主題
    people: str = ""   # 登場人物の紹介
    notes: str = ""    # 固有名詞・補足(用語集に入れるほどでない文脈情報)


@router.get("/media/{media_id}/brief", response_model=Brief)
def get_brief(media_id: int, db: sqlite3.Connection = Depends(get_db)):
    row = db.execute("SELECT brief_json FROM media WHERE id=?", (media_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "メディアが見つかりません")
    import json

    return Brief(**json.loads(row["brief_json"] or "{}"))


@router.patch("/media/{media_id}/brief", response_model=Brief)
def update_brief(media_id: int, body: Brief, db: sqlite3.Connection = Depends(get_db)):
    """動画の主題・登場人物・固有名詞紹介。切り抜き・指示語解決・固有名詞スキャンの
    全LLMプロンプトに注入される(BACKEND_DESIGN.md「ユーザー指示の注入」)"""
    if db.execute("SELECT 1 FROM media WHERE id=?", (media_id,)).fetchone() is None:
        raise HTTPException(404, "メディアが見つかりません")
    import json

    db.execute(
        "UPDATE media SET brief_json=? WHERE id=?",
        (json.dumps(body.model_dump(), ensure_ascii=False), media_id),
    )
    db.commit()
    return body


@router.get("/media/{media_id}/file")
def get_media_file(media_id: int, db: sqlite3.Connection = Depends(get_db)):
    """動画プレビュー用にメディアファイル本体を返す(Range対応はFileResponse任せ)"""
    row = db.execute("SELECT path FROM media WHERE id=?", (media_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "メディアが見つかりません")
    path = Path(row["path"])
    if not path.exists():
        raise HTTPException(404, f"ファイルが存在しません: {path}")
    return FileResponse(path)
