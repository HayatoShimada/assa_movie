"""APIの入出力モデル。OpenAPI経由でフロントの型生成元になる。"""

from typing import Literal

from pydantic import BaseModel, Field

Orientation = Literal["landscape", "portrait"]


class ProjectCreate(BaseModel):
    name: str
    # テンプレート(縦→縦/横→縦/横→横/縦→横)は入力・出力の向きの組
    input_orientation: Orientation = "landscape"
    output_orientation: Orientation = "landscape"
    # グローバル設定との差分のみ(許可キーはPROJECT_OVERRIDABLE)
    settings: dict = Field(default_factory=dict)


class ProjectUpdate(BaseModel):
    name: str | None = None
    input_orientation: Orientation | None = None
    output_orientation: Orientation | None = None
    settings: dict | None = None  # 指定時は差し替え(部分マージではない)


class Project(BaseModel):
    id: int
    name: str
    input_orientation: Orientation = "landscape"
    output_orientation: Orientation = "landscape"
    settings: dict = Field(default_factory=dict)
    created_at: str


class MediaCreate(BaseModel):
    path: str = Field(description="動画/音声ファイルの絶対パスまたはプロジェクト相対パス")


class Media(BaseModel):
    id: int
    project_id: int
    path: str
    duration: float | None = None
    width: int | None = None
    height: int | None = None
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
