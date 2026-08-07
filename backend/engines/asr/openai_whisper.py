"""公式Whisper(openai-whisper)エンジン。ROCm向けの本命。

faster-whisper(CTranslate2)はCUDA専用ビルドのためAMD GPUでは初期化に失敗する。
公式実装はPyTorchで動くのでROCmでもGPUを使え、faster-whisperと同じ情報
(単語タイムスタンプ・単語確率・initial_prompt・長尺の分割)が揃う。

transformers版との違い: あちらは単語確率が取れず initial_prompt も渡せない。
出力形状はfaster-whisperとほぼ同じなので、CUDA機とROCm機で挙動が揃う。
"""

import numpy as np

from backend.core.device import detect_accel
from backend.engines.asr.base import ProgressFn, Segment, TranscribeResult, Word

SAMPLE_RATE = 16000


def to_segments(raw_segments: list[dict]) -> list[Segment]:
    """whisperのtranscribe結果(dict)を共通のSegment/Wordへ写す(純関数)"""
    out: list[Segment] = []
    for seg in raw_segments:
        words = [
            Word(
                start=float(w["start"]),
                end=float(w["end"]),
                text=str(w.get("word", "")),
                probability=w.get("probability"),
            )
            for w in (seg.get("words") or [])
            if w.get("start") is not None and w.get("end") is not None
        ]
        out.append(
            Segment(
                start=float(seg["start"]),
                end=float(seg["end"]),
                text=str(seg.get("text", "")).strip(),
                words=words or None,
                confidence=seg.get("avg_logprob"),
            )
        )
    return out


class OpenAIWhisperEngine:
    name = "openai-whisper"

    def __init__(
        self,
        model_size: str = "large-v3",
        device: str = "cuda",
        beam_size: int = 5,
        model_factory=None,  # テスト用の差し替え口
    ):
        self.model_size = model_size
        self.device = device
        self.beam_size = beam_size
        self._model_factory = model_factory
        self._model = None

    def load(self):
        if self._model is None:
            if self._model_factory is not None:
                self._model = self._model_factory()
                return self._model
            import whisper

            if self.device != "cpu" and detect_accel() == "rocm":
                # ROCmでは通常メモリ→GPUの転送が極端に遅い環境があるため、
                # CPUに読んでからpage-locked経由で送る(core/device.pyのコメント参照)。
                # 重みはfloat32のままにする(whisperのLayerNormが入力をfloat化して
                # 重みと突き合わせるため、half()にすると型不一致で落ちる)
                model = whisper.load_model(self.model_size, device="cpu")
                for p in model.parameters():
                    p.data = p.data.pin_memory()
                for b in model.buffers():
                    b.data = b.data.pin_memory()
                self._model = model.to(self.device)
            else:
                self._model = whisper.load_model(self.model_size, device=self.device)
        return self._model

    def transcribe(
        self,
        audio: np.ndarray,
        language: str | None = None,
        progress: ProgressFn | None = None,
        initial_prompt: str | None = None,
    ) -> TranscribeResult:
        model = self.load()
        if progress:
            progress(0.02)  # モデルロード後すぐ動き出したことを知らせる
        result = model.transcribe(
            audio,
            language=language,
            beam_size=self.beam_size,
            word_timestamps=True,  # 話者割り当て・字幕同期・フィラー判定に必要
            initial_prompt=initial_prompt,
            fp16=self.device != "cpu",
            verbose=None,
        )
        if progress:
            progress(1.0)
        return TranscribeResult(
            segments=to_segments(result.get("segments") or []),
            language=str(result.get("language") or language or ""),
        )

    def unload(self) -> None:
        if self._model is not None:
            del self._model
            self._model = None
            try:
                import torch

                torch.cuda.empty_cache()
            except Exception:
                pass
