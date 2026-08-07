"""APIの入出力モデル。OpenAPI経由でフロントの型生成元になる。"""

from pydantic import BaseModel, Field


class ProjectCreate(BaseModel):
    name: str


class Project(BaseModel):
    id: int
    name: str
    created_at: str


class MediaCreate(BaseModel):
    path: str = Field(description="動画/音声ファイルの絶対パスまたはプロジェクト相対パス")


class Media(BaseModel):
    id: int
    project_id: int
    path: str
    duration: float | None = None
    status: str
    created_at: str


class JobCreate(BaseModel):
    type: str = Field(description="transcribe など")
    params: dict = Field(default_factory=dict)


class Job(BaseModel):
    id: int
    media_id: int | None
    type: str
    status: str
    progress: float
    error: str | None = None
    result: dict | None = None  # 書き出しジョブの出力パスなど
    created_at: str


class Word(BaseModel):
    start: float
    end: float
    text: str


class Segment(BaseModel):
    id: int
    media_id: int
    idx: int
    start: float
    end: float
    text: str
    original_text: str
    speaker: str | None = None
    is_aizuchi: bool = False
    edited_by_user: bool = False
    asr_confidence: float | None = None
    subtitle_show: str = "auto_show"
    words: list[Word] = Field(default_factory=list)


class SegmentUpdate(BaseModel):
    text: str | None = None
    speaker: str | None = None
    subtitle_show: str | None = None
