"""ASRエンジンの共通インターフェース。BACKEND_DESIGN.md「ASRエンジン抽象化」参照。"""

from dataclasses import dataclass, field
from typing import Callable, Protocol

import numpy as np


@dataclass
class Word:
    start: float
    end: float
    text: str
    # Whisperデコード時の単語確率。低い語は「聞き取りが曖昧」のシグナルとして
    # フィラー判定・字幕採用ジャッジに使う(量子化で捨てられる情報の回収)
    probability: float | None = None


@dataclass
class Segment:
    start: float
    end: float
    text: str
    words: list[Word] | None = None
    speaker: str | None = None
    confidence: float | None = None


@dataclass
class TranscribeResult:
    segments: list[Segment] = field(default_factory=list)
    language: str = ""
    language_probability: float = 0.0


ProgressFn = Callable[[float], None]


class ASREngine(Protocol):
    name: str

    def transcribe(
        self,
        audio: np.ndarray,
        language: str | None = None,
        progress: ProgressFn | None = None,
    ) -> TranscribeResult:
        ...

    def unload(self) -> None:
        """VRAMを解放する(ステージ直列実行のため)"""
        ...
