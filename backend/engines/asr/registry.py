"""ASRモデル・エンジンの選択とメタ情報(プロファイル固定方式)。

2026-08-07の実測比較(BACKEND_DESIGN.md「検証済み」表)により、
既定モデルは large-v3(精度優先・単語タイムスタンプ必須の要件による)。

エンジンは実行時に検出しない(DESIGN.md 2026-08-10)。初回起動で確定した
ハードウェアプロファイル → 静的対応表(backend/core/hwprofile.resolve_spec)で決まる:
  GPU機(nvidia/radeon/apple)→ whisper.cpp(Linux/Windows=Vulkan、mac=Metal)
  CPU機・検証失敗機          → faster-whisper(CPU int8)
構成が壊れていた場合はフォールバックせず、直し方を含むエラーで止める
(黙ってCPUで数十分走るより、原因と回復手順を伝えるほうが親切という決定)。
"""

from dataclasses import dataclass

from backend.core import hwprofile
from backend.engines.asr.base import ASREngine
from backend.engines.asr.fasterwhisper import FasterWhisperEngine
from backend.engines.asr.whispercpp import WhisperCppEngine


@dataclass(frozen=True)
class ModelInfo:
    id: str
    label: str
    rtf: int          # 実時間比(RTX PRO 6000実測)
    word_timestamps: bool
    vram_mb: int = 0  # GPU実行時のVRAM目安
    note: str = ""


MODELS: dict[str, ModelInfo] = {
    "large-v3": ModelInfo(
        id="large-v3",
        label="large-v3(精度優先・既定)",
        rtf=25,
        word_timestamps=True,
        vram_mb=5000,
        note="方言や言い回しをそのまま保持します。75分の動画で約3分。",
    ),
    "large-v3-turbo": ModelInfo(
        id="large-v3-turbo",
        label="large-v3-turbo(速度優先)",
        rtf=111,
        word_timestamps=True,
        vram_mb=2500,
        note="約4.5倍高速ですが、発話が標準語化される場合があります。",
    ),
}

DEFAULT_MODEL = "large-v3"

# KS_ASR_ENGINE 環境変数で指定できる値(上級者向けの唯一の上書き手段。UIには出さない)
ENGINE_OVERRIDES = ("", "faster_whisper", "whispercpp")


def build_engine(settings) -> ASREngine:
    """確定済みプロファイルからASRエンジンを組み立てる(検出は行わない)"""
    if settings.asr_model not in MODELS:
        raise ValueError(
            f"未知のASRモデル: {settings.asr_model}(選択肢: {', '.join(MODELS)})"
        )
    if settings.asr_engine not in ENGINE_OVERRIDES:
        raise ValueError(
            f"未知のASRエンジン: {settings.asr_engine}"
            f"(KS_ASR_ENGINE で指定できるのは faster_whisper / whispercpp)"
        )

    spec = hwprofile.resolve_spec(hwprofile.current())
    engine_id = settings.asr_engine or spec.engine

    if engine_id == "whispercpp":
        _ensure_whispercpp_ready()
        return WhisperCppEngine(beam_size=settings.asr_beam_size)

    # faster-whisperは常にCPU int8(CUDA経路は2026-08-10に廃止。
    # int8クラッシュの実績はBlackwell GPU限定でCPUは安全)
    return FasterWhisperEngine(
        model_size=settings.asr_model,
        device="cpu",
        compute_type="int8",
        beam_size=settings.asr_beam_size,
        vad_filter=settings.asr_vad_filter,
    )


def _ensure_whispercpp_ready() -> None:
    """whisper.cppの構成が壊れていたら、直し方を含むエラーで止める"""
    from backend.engines.asr import whispercpp

    if whispercpp.resolve_binary() is None:
        raise RuntimeError(
            "whisper.cppの実行ファイルが見つかりません。"
            "設定タブの「実行環境」から再検出してください。"
        )
    if not whispercpp.resolve_model().is_file():
        raise RuntimeError(
            "whisper.cppのモデル(ggml-large-v3)が見つかりません。"
            "設定タブのセットアップから取得してください。"
        )
