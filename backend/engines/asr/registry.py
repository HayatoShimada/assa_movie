"""ASRモデル・エンジンの選択とメタ情報。

2026-08-07の実測比較(BACKEND_DESIGN.md「検証済み」表)により、
既定モデルは large-v3(精度優先・単語タイムスタンプ必須の要件による)。

エンジンはアクセラレータで自動選択する(asr_engine="auto"):
- CUDA  → faster-whisper(float16。Blackwellでint8はクラッシュ)
- ROCm  → transformers版Whisper(CTranslate2がROCm非対応のため)
- CPU   → faster-whisper(int8。int8クラッシュはBlackwell GPU限定でCPUは安全)
"""

from dataclasses import dataclass

from backend.core.device import detect_accel
from backend.engines.asr.base import ASREngine
from backend.engines.asr.fasterwhisper import FasterWhisperEngine
from backend.engines.asr.transformers_whisper import TransformersWhisperEngine


@dataclass(frozen=True)
class ModelInfo:
    id: str
    label: str
    rtf: int          # 実時間比(RTX PRO 6000実測)
    word_timestamps: bool
    hf_id: str = ""   # transformersエンジンで使うHugging FaceのモデルID
    note: str = ""


MODELS: dict[str, ModelInfo] = {
    "large-v3": ModelInfo(
        id="large-v3",
        label="large-v3(精度優先・既定)",
        rtf=25,
        word_timestamps=True,
        hf_id="openai/whisper-large-v3",
        note="方言や言い回しをそのまま保持します。75分の動画で約3分。",
    ),
    "large-v3-turbo": ModelInfo(
        id="large-v3-turbo",
        label="large-v3-turbo(速度優先)",
        rtf=111,
        word_timestamps=True,
        hf_id="openai/whisper-large-v3-turbo",
        note="約4.5倍高速ですが、発話が標準語化される場合があります。",
    ),
}

DEFAULT_MODEL = "large-v3"

ENGINES: dict[str, str] = {
    "auto": "自動(GPUに合わせて選択)",
    "faster_whisper": "faster-whisper(CUDA/CPU)",
    "transformers": "transformers Whisper(ROCm/CUDA)",
}


def build_engine(settings) -> ASREngine:
    """設定からASRエンジンを組み立てる"""
    if settings.asr_model not in MODELS:
        raise ValueError(
            f"未知のASRモデル: {settings.asr_model}(選択肢: {', '.join(MODELS)})"
        )
    engine_id = getattr(settings, "asr_engine", "auto")
    if engine_id not in ENGINES:
        raise ValueError(
            f"未知のASRエンジン: {engine_id}(選択肢: {', '.join(ENGINES)})"
        )

    accel = detect_accel()
    if engine_id == "auto":
        engine_id = "transformers" if accel == "rocm" else "faster_whisper"

    if engine_id == "transformers":
        return TransformersWhisperEngine(
            model_id=MODELS[settings.asr_model].hf_id,
            # ROCmのHIPはtorch上で"cuda"を名乗るのでそのまま渡す
            device="cuda" if accel in ("cuda", "rocm") else "cpu",
        )

    if accel == "cuda":
        return FasterWhisperEngine(
            model_size=settings.asr_model,
            device="cuda",
            compute_type=settings.asr_compute_type,
            beam_size=settings.asr_beam_size,
            vad_filter=settings.asr_vad_filter,
        )
    # CTranslate2はROCm非対応のため、rocm/cpuともCPU実行にフォールバック
    return FasterWhisperEngine(
        model_size=settings.asr_model,
        device="cpu",
        compute_type="int8",
        beam_size=settings.asr_beam_size,
        vad_filter=settings.asr_vad_filter,
    )
