"""ASRモデル・エンジンの選択とメタ情報。

2026-08-07の実測比較(BACKEND_DESIGN.md「検証済み」表)により、
既定モデルは large-v3(精度優先・単語タイムスタンプ必須の要件による)。

エンジンはアクセラレータで自動選択する(asr_engine="auto"):
- CUDA  → faster-whisper(float16。Blackwellでint8はクラッシュ)
- ROCm  → whisper.cpp。無ければ公式Whisper(CTranslate2がROCm非対応のため)。
          公式Whisperもtorch依存で配布物には無いので、その場合はfaster-whisper(CPU)
- GPUはあるがCUDA/ROCmでない(AMDのWindows等)→ whisper.cpp(Vulkan)
- CPU   → faster-whisper(int8。int8クラッシュはBlackwell GPU限定でCPUは安全)
"""

from dataclasses import dataclass

from backend.core.device import detect_accel, missing_cuda_libs
from backend.engines.asr.base import ASREngine
from backend.engines.asr.fasterwhisper import FasterWhisperEngine
from backend.engines.asr.openai_whisper import OpenAIWhisperEngine
from backend.engines.asr.openai_whisper import is_available as openai_whisper_available
from backend.engines.asr.whispercpp import WhisperCppEngine
from backend.engines.asr.whispercpp import is_available as whispercpp_available


@dataclass(frozen=True)
class ModelInfo:
    id: str
    label: str
    rtf: int          # 実時間比(RTX PRO 6000実測)
    word_timestamps: bool
    vram_fw_mb: int = 0  # faster-whisper(float16)でのVRAM目安
    vram_tf_mb: int = 0  # 公式Whisper(PyTorch、float16)でのVRAM目安
    note: str = ""

    def vram_mb(self, engine: str) -> int:
        """指定エンジンで動かしたときのVRAM目安(推奨判定と選択UIで共用)"""
        # PyTorch実装は重みに加えて注意重み等を持つため目安が大きい。
        # whisper.cppはggml量子化なしでもfaster-whisper並に収まる
        return self.vram_tf_mb if engine == "openai_whisper" else self.vram_fw_mb


MODELS: dict[str, ModelInfo] = {
    "large-v3": ModelInfo(
        id="large-v3",
        label="large-v3(精度優先・既定)",
        rtf=25,
        word_timestamps=True,
        vram_fw_mb=5000,
        vram_tf_mb=10000,
        note="方言や言い回しをそのまま保持します。75分の動画で約3分。",
    ),
    "large-v3-turbo": ModelInfo(
        id="large-v3-turbo",
        label="large-v3-turbo(速度優先)",
        rtf=111,
        word_timestamps=True,
        vram_fw_mb=2500,
        vram_tf_mb=6500,
        note="約4.5倍高速ですが、発話が標準語化される場合があります。",
    ),
}

DEFAULT_MODEL = "large-v3"

ENGINES: dict[str, str] = {
    "auto": "自動(GPUに合わせて選択)",
    "faster_whisper": "faster-whisper(CUDA/CPU)",
    "whispercpp": "whisper.cpp(ROCm最速・要ビルド)",
    "openai_whisper": "公式Whisper(ROCm/CUDA)",
}


def resolve_engine(engine_id: str, accel: str, has_gpu: bool = False) -> str:
    """`auto` を実際のエンジンに解決する(実行と推奨表示で同じ規則を使う)。

    ROCmでは whisper.cpp が最速(公式版の約2.6倍)だが外部ビルドが要るので、
    用意されているときだけ使い、無ければ公式Whisperに落とす。
    CTranslate2(faster-whisper)はCUDA専用ビルドなのでROCmでは使えない。

    `has_gpu` は「CUDA/ROCmは無いがGPUは積んでいる」機体のためにある。
    典型はAMDのWindows機で、accelは"cpu"になるがVulkanは動く。同梱の
    whisper.cpp(Vulkanビルド)ならGPUに載せられる
    (RX 7900 XTX実測: 60秒の音声が faster-whisper CPU 52秒 → 4.8秒)。
    """
    if engine_id != "auto":
        return engine_id
    if accel == "rocm":
        if whispercpp_available():
            return "whispercpp"
        # 公式Whisperはtorch依存で配布物に入っていない。開発機でだけ選ぶ。
        # 配布版でここへ落とすとImportErrorで文字起こしが必ず失敗するので、
        # GPUは使えなくても動くfaster-whisper(CPU)にする
        return "openai_whisper" if openai_whisper_available() else "faster_whisper"
    if accel == "cuda":
        return "faster_whisper"  # CUDA版CTranslate2が最速
    # GPUはあるがCUDA/ROCmとして使えない。Vulkanなら賄える
    if has_gpu and whispercpp_available():
        return "whispercpp"
    return "faster_whisper"


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

    from backend.core.device import probe_gpu

    accel = detect_accel()
    missing = missing_cuda_libs() if accel == "cuda" else []
    if missing:
        # ドライバはある(nvidia-smiが通る)のにCUDAランタイムが無い機体がある
        # (配布版Ubuntuで実例: libcublas.so.12が無くモデル読み込みで必ず落ちる)。
        # 「GPUはあるがCUDA/ROCmとしては使えない」機体と同じ規則に落とし、
        # whisper.cpp(Vulkan)かCPUで動かす。クラッシュより遅い成功を選ぶ
        print(f"CUDAライブラリが見つかりません({', '.join(missing)})。GPUなしの規則でASRエンジンを選びます")
        accel = "cpu"
    # CUDA/ROCmが無くてもGPUが載っていればVulkanのwhisper.cppが使える
    engine_id = resolve_engine(
        settings.asr_engine, accel, has_gpu=bool(probe_gpu().get("name"))
    )

    if engine_id == "whispercpp":
        return WhisperCppEngine(beam_size=settings.asr_beam_size)

    # ROCmのHIPはtorch上で"cuda"を名乗るのでそのまま渡す
    torch_device = "cuda" if accel in ("cuda", "rocm") else "cpu"
    if engine_id == "openai_whisper":
        return OpenAIWhisperEngine(
            model_size=settings.asr_model,
            device=torch_device,
            beam_size=settings.asr_beam_size,
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
