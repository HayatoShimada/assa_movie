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
    vram_fw_mb: int = 0  # faster-whisper(float16)でのVRAM目安
    vram_tf_mb: int = 0  # transformers(float16)でのVRAM目安
    note: str = ""

    def vram_mb(self, engine: str) -> int:
        """指定エンジンで動かしたときのVRAM目安(推奨判定と選択UIで共用)"""
        return self.vram_tf_mb if engine == "transformers" else self.vram_fw_mb


MODELS: dict[str, ModelInfo] = {
    "large-v3": ModelInfo(
        id="large-v3",
        label="large-v3(精度優先・既定)",
        rtf=25,
        word_timestamps=True,
        hf_id="openai/whisper-large-v3",
        vram_fw_mb=5000,
        vram_tf_mb=10000,
        note="方言や言い回しをそのまま保持します。75分の動画で約3分。",
    ),
    "large-v3-turbo": ModelInfo(
        id="large-v3-turbo",
        label="large-v3-turbo(速度優先)",
        rtf=111,
        word_timestamps=True,
        hf_id="openai/whisper-large-v3-turbo",
        vram_fw_mb=2500,
        vram_tf_mb=6500,
        note="約4.5倍高速ですが、発話が標準語化される場合があります。",
    ),
}

DEFAULT_MODEL = "large-v3"

ENGINES: dict[str, str] = {
    "auto": "自動(GPUに合わせて選択)",
    "faster_whisper": "faster-whisper(CUDA/CPU)",
    "transformers": "transformers Whisper(ROCm/CUDA)",
}


def resolve_engine(engine_id: str, accel: str) -> str:
    """`auto` を実際のエンジンに解決する(実行と推奨表示で同じ規則を使う)"""
    if engine_id != "auto":
        return engine_id
    # CTranslate2はROCm非対応なのでROCmではtransformers版を使う
    return "transformers" if accel == "rocm" else "faster_whisper"


def build_engine(settings) -> ASREngine:
    """設定からASRエンジンを組み立てる"""
    if settings.asr_model not in MODELS:
        raise ValueError(
            f"未知のASRモデル: {settings.asr_model}(選択肢: {', '.join(MODELS)})"
        )
    if settings.asr_engine not in ENGINES:
        raise ValueError(
            f"未知のASRエンジン: {settings.asr_engine}(選択肢: {', '.join(ENGINES)})"
        )

    accel = detect_accel()
    engine_id = resolve_engine(settings.asr_engine, accel)

    if engine_id == "transformers":
        return TransformersWhisperEngine(
            model_id=MODELS[settings.asr_model].hf_id,
            # ROCmのHIPはtorch上で"cuda"を名乗るのでそのまま渡す
            device="cuda" if accel in ("cuda", "rocm") else "cpu",
        )

    # CTranslate2はROCm非対応のため、rocm/cpuともCPU実行にフォールバック
    # (int8クラッシュはBlackwell GPU限定でCPUは安全)
    device, compute_type = (
        ("cuda", settings.asr_compute_type) if accel == "cuda" else ("cpu", "int8")
    )
    return FasterWhisperEngine(
        model_size=settings.asr_model,
        device=device,
        compute_type=compute_type,
        beam_size=settings.asr_beam_size,
        vad_filter=settings.asr_vad_filter,
    )
