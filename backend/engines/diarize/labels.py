"""話者ラベル → 表示名の割り当て。話者分離エンジンに依存しない純粋な処理。

pyannoteもONNXも `SPEAKER_00/01` 形式のラベルを返すが、その番号はファイルごとに
順序が変わる。男女2人の対談では基本周波数の中央値で「低い方=男性」と判定する方が確実。

ピッチ推定は backend/pipeline/pitch.py(numpy実装)を使う。
torchaudioに依存しないので、torchを入れない構成でも動く(docs/V1_PLAN.md M23)。
"""

import numpy as np

from backend.pipeline.pitch import SAMPLE_RATE, median_f0

# 2人のピッチ差がこれ未満なら判定が怪しいので警告する
PITCH_WARN_THRESHOLD_HZ = 30
# 0.5秒未満の断片はピッチ推定の精度が低いので使わない
MIN_CHUNK_SEC = 0.5
# 60秒分あれば中央値は安定する(長尺で無駄に時間をかけない)
MAX_PITCH_SEC = 60

Turn = tuple[float, float, str]


def estimate_pitch(audio: np.ndarray, turns: list[Turn], label: str) -> float | None:
    """指定話者の区間から声の基本周波数(Hz)の中央値を推定する"""
    chunks = []
    total = 0
    for start, end, turn_label in turns:
        if turn_label != label:
            continue
        seg = audio[int(start * SAMPLE_RATE):int(end * SAMPLE_RATE)]
        if len(seg) >= SAMPLE_RATE * MIN_CHUNK_SEC:
            chunks.append(seg)
            total += len(seg)
        if total >= SAMPLE_RATE * MAX_PITCH_SEC:
            break
    if not chunks:
        return None
    return median_f0(np.concatenate(chunks))


def build_label_map(
    audio: np.ndarray,
    turns: list[Turn],
    male_name: str | None = None,
    female_name: str | None = None,
    speaker_names: dict[str, str] | None = None,
    log=print,
) -> dict[str, str]:
    """話者ラベル → 表示名の対応表を作る"""
    speakers = sorted({label for _, _, label in turns})
    if speaker_names:
        return {l: speaker_names.get(l, l) for l in speakers}

    # 男女2人の対談なら声の高さで自動判定
    if len(speakers) == 2 and male_name and female_name:
        pitches = {l: estimate_pitch(audio, turns, l) for l in speakers}
        if all(p is not None for p in pitches.values()):
            low, high = sorted(speakers, key=lambda l: pitches[l])
            log(
                f"声の高さで話者を判定: {low}={pitches[low]:.0f}Hz → {male_name}, "
                f"{high}={pitches[high]:.0f}Hz → {female_name}"
            )
            if abs(pitches[low] - pitches[high]) < PITCH_WARN_THRESHOLD_HZ:
                log("⚠ 2人の声の高さが近いため、判定が誤っている可能性があります。")
            return {low: male_name, high: female_name}
        log("⚠ ピッチ推定に失敗したため、話者1/話者2 表示にフォールバックします。")

    return {label: f"話者{i}" for i, label in enumerate(speakers, start=1)}


def assign_speaker(segment, turns: list[Turn]) -> str | None:
    """セグメントに、時間の重なりが最大の話者を割り当てる"""
    words = getattr(segment, "words", None) or []
    spans = [(w.start, w.end) for w in words] or [(segment.start, segment.end)]
    overlap_by_speaker: dict[str, float] = {}
    for start, end in spans:
        for t_start, t_end, label in turns:
            overlap = min(end, t_end) - max(start, t_start)
            if overlap > 0:
                overlap_by_speaker[label] = overlap_by_speaker.get(label, 0.0) + overlap
    if not overlap_by_speaker:
        return None
    return max(overlap_by_speaker, key=overlap_by_speaker.get)
