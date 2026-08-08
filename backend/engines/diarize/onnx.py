"""話者分離(sherpa-onnx)。CPUだけで動き、torchを必要としない。

実測(RX 7900 XTX機 / 300秒の対談音声):
  - sherpa-onnx (CPU 16スレッド): 実時間比 10.7倍
  - pyannote (torch/GPU):         実時間比  2.8倍
  - 話者割り当ての一致率: 94.8%
モデルは76MBで、torch(14GB)を丸ごと外せる(docs/V1_PLAN.md M23)。

モデルは `./dev.sh diarize-models` で取得する。
"""

import os
from pathlib import Path

import numpy as np

from backend.core.paths import cache_dir

SAMPLE_RATE = 16000
# 置き場所は backend/core/paths.py が決める(whisper.cppと同じディレクトリ)
DEFAULT_HOME = Path(os.environ.get("KS_MODELS_HOME") or cache_dir())
DEFAULT_SEGMENTATION = DEFAULT_HOME / "models/sherpa-onnx-pyannote-segmentation-3-0/model.onnx"
DEFAULT_EMBEDDING = DEFAULT_HOME / "models/speaker-embedding.onnx"

# 短すぎる発話・間は区切らない(相槌で細切れになるのを防ぐ)
MIN_DURATION_ON = 0.3
MIN_DURATION_OFF = 0.5

Turn = tuple[float, float, str]


def is_available(
    segmentation: Path = DEFAULT_SEGMENTATION, embedding: Path = DEFAULT_EMBEDDING
) -> bool:
    """必要なモデルが揃っているか"""
    return segmentation.is_file() and embedding.is_file()


def to_turns(segments) -> list[Turn]:
    """sherpa-onnxの結果を (開始, 終了, ラベル) に変換する(純関数)。

    ラベルはpyannoteと同じ `SPEAKER_00` 形式にそろえる。
    既存の話者名割り当て(build_label_map)がそのまま使えるようにするため。
    """
    return sorted(
        (float(s.start), float(s.end), f"SPEAKER_{int(s.speaker):02d}") for s in segments
    )


def _default_threads() -> int:
    """CPUコアを使い切る(実測: 4→5.9倍, 8→9.2倍, 16→10.7倍)"""
    return max(1, min(16, (os.cpu_count() or 4)))


def _build_diarizer(
    segmentation: Path,
    embedding: Path,
    num_speakers: int | None,
    num_threads: int,
):
    import sherpa_onnx

    return sherpa_onnx.OfflineSpeakerDiarization(
        sherpa_onnx.OfflineSpeakerDiarizationConfig(
            segmentation=sherpa_onnx.OfflineSpeakerSegmentationModelConfig(
                pyannote=sherpa_onnx.OfflineSpeakerSegmentationPyannoteModelConfig(
                    model=str(segmentation)
                ),
                num_threads=num_threads,
            ),
            embedding=sherpa_onnx.SpeakerEmbeddingExtractorConfig(
                model=str(embedding), num_threads=num_threads
            ),
            # 人数が分かっているならクラスタ数を固定した方が安定する
            clustering=sherpa_onnx.FastClusteringConfig(num_clusters=num_speakers or -1),
            min_duration_on=MIN_DURATION_ON,
            min_duration_off=MIN_DURATION_OFF,
        )
    )


def run_diarization(
    audio: np.ndarray,
    num_speakers: int | None = 2,
    segmentation: Path | None = None,
    embedding: Path | None = None,
) -> list[Turn]:
    """(開始秒, 終了秒, 話者ラベル) のリストを返す(pyannote版と同じ形)"""
    seg = segmentation or DEFAULT_SEGMENTATION
    emb = embedding or DEFAULT_EMBEDDING
    if not is_available(seg, emb):
        raise RuntimeError(
            f"話者分離モデルが見つかりません({seg} / {emb})。"
            "`./dev.sh diarize-models` で取得してください"
        )
    diarizer = _build_diarizer(
        segmentation=seg,
        embedding=emb,
        num_speakers=num_speakers,
        num_threads=_default_threads(),
    )
    return to_turns(diarizer.process(np.asarray(audio, dtype=np.float32)).sort_by_start_time())
