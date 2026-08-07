"""音声デコード。全ASRエンジンに同じ16kHzモノラル配列を渡すための一元化層。

PyAVベースなので .mov/.mp4/.wav などコンテナ差異をエンジンから隠蔽する。
"""

from pathlib import Path

import numpy as np
from faster_whisper.audio import decode_audio

SAMPLE_RATE = 16000


def decode(path: str | Path, sampling_rate: int = SAMPLE_RATE) -> np.ndarray:
    """動画/音声ファイルをモノラルfloat32配列にデコードする"""
    return decode_audio(str(path), sampling_rate=sampling_rate)
