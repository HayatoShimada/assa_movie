"""話者分離(pyannote.audio 3.x)と、声の高さによる話者名の自動割り当て。

pyannoteのラベル(SPEAKER_00/01)はファイルごとに順序が変わるため、
男女2人の対談では基本周波数の中央値で「低い方=男性」と判定する方が確実。
"""

import os
from pathlib import Path

import numpy as np

SAMPLE_RATE = 16000
DEFAULT_MODEL = "pyannote/speaker-diarization-3.1"
# 2人のピッチ差がこれ未満なら判定が怪しいので警告する
PITCH_WARN_THRESHOLD_HZ = 30

Turn = tuple[float, float, str]


def load_hf_token(token_file: Path | None = None) -> str | None:
    token = os.environ.get("HF_TOKEN", "").strip()
    if token.startswith("hf_"):
        return token
    if token_file and token_file.exists():
        token = token_file.read_text(encoding="utf-8").strip()
        if token.startswith("hf_") and "\n" not in token:
            return token
    return None


def run_diarization(
    audio: np.ndarray,
    token: str,
    model: str = DEFAULT_MODEL,
    num_speakers: int | None = 2,
) -> list[Turn]:
    """(開始秒, 終了秒, 話者ラベル) のリストを返す"""
    import warnings

    import torch

    # torchcodec未対応の警告を抑制(音声はメモリ上で直接渡すため不要)
    warnings.filterwarnings("ignore", category=UserWarning, module=r"pyannote\.audio\.core\.io")
    from pyannote.audio import Pipeline

    # torch 2.6以降のweights_only=Trueデフォルトで、pyannote公式チェックポイントの
    # 読み込みに必要なクラスを許可リストに追加(モデル提供元を信頼している前提)
    from pyannote.audio.core.task import Problem, Resolution, Specifications

    torch.serialization.add_safe_globals(
        [torch.torch_version.TorchVersion, Specifications, Problem, Resolution]
    )

    try:
        pipeline = Pipeline.from_pretrained(model, token=token)
    except TypeError:
        # pyannote.audio 3.x は引数名が use_auth_token
        pipeline = Pipeline.from_pretrained(model, use_auth_token=token)
    # ROCmのHIPビルドもtorch上では"cuda"を名乗るのでこの判定で両対応になる
    # (ROCm固有のtorch設定は core/device.py apply_rocm_workarounds が起動時に適用済み)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    pipeline.to(device)

    inputs = {"waveform": torch.from_numpy(audio).unsqueeze(0), "sample_rate": SAMPLE_RATE}
    kwargs = {"num_speakers": num_speakers} if num_speakers is not None else {}
    try:
        result = pipeline(inputs, **kwargs)
    except RuntimeError:
        if device.type != "cuda":
            raise
        # ROCm初期環境でのMIOpenカーネル生成失敗等に備え、CPUで1回だけ再試行する
        print("⚠ GPUでの話者分離に失敗したため、CPUで再試行します。")
        pipeline.to(torch.device("cpu"))
        result = pipeline(inputs, **kwargs)

    # pyannote.audio 4.x はコンテナ型、3.x はAnnotationを直接返す
    annotation = getattr(result, "speaker_diarization", result)
    return [
        (turn.start, turn.end, label)
        for turn, _, label in annotation.itertracks(yield_label=True)
    ]


def estimate_pitch(audio: np.ndarray, turns: list[Turn], label: str) -> float | None:
    """指定話者の区間から声の基本周波数(Hz)の中央値を推定する"""
    import torch
    import torchaudio

    wave = torch.from_numpy(audio)
    chunks = []
    total = 0
    for start, end, turn_label in turns:
        if turn_label != label:
            continue
        seg = wave[int(start * SAMPLE_RATE):int(end * SAMPLE_RATE)]
        if len(seg) >= SAMPLE_RATE // 2:  # 0.5秒未満の断片は精度が低いので除く
            chunks.append(seg)
            total += len(seg)
        if total >= SAMPLE_RATE * 60:  # 60秒分あれば十分
            break
    if not chunks:
        return None
    x = torch.cat(chunks).unsqueeze(0)
    f0 = torchaudio.functional.detect_pitch_frequency(x, SAMPLE_RATE, freq_low=60, freq_high=400)
    f0 = f0[f0 > 0]
    if f0.numel() == 0:
        return None
    return float(f0.median())


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
