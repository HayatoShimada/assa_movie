"""ASRモデルの選択とメタ情報。

2026-08-07の実測比較(BACKEND_DESIGN.md「検証済み」表)により、
既定は large-v3(精度優先・単語タイムスタンプ必須の要件による)。
"""

from dataclasses import dataclass

from backend.engines.asr.fasterwhisper import FasterWhisperEngine


@dataclass(frozen=True)
class ModelInfo:
    id: str
    label: str
    rtf: int          # 実時間比(RTX PRO 6000実測)
    word_timestamps: bool
    note: str = ""


MODELS: dict[str, ModelInfo] = {
    "large-v3": ModelInfo(
        id="large-v3",
        label="large-v3(精度優先・既定)",
        rtf=25,
        word_timestamps=True,
        note="方言や言い回しをそのまま保持します。75分の動画で約3分。",
    ),
    "large-v3-turbo": ModelInfo(
        id="large-v3-turbo",
        label="large-v3-turbo(速度優先)",
        rtf=111,
        word_timestamps=True,
        note="約4.5倍高速ですが、発話が標準語化される場合があります。",
    ),
}

DEFAULT_MODEL = "large-v3"


def build_engine(settings) -> FasterWhisperEngine:
    """設定からASRエンジンを組み立てる"""
    if settings.asr_model not in MODELS:
        raise ValueError(
            f"未知のASRモデル: {settings.asr_model}(選択肢: {', '.join(MODELS)})"
        )
    return FasterWhisperEngine(
        model_size=settings.asr_model,
        compute_type=settings.asr_compute_type,
        beam_size=settings.asr_beam_size,
        vad_filter=settings.asr_vad_filter,
    )
