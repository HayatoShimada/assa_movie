"""faster-whisperエンジン(既定)。

既定モデルは large-v3。精度優先・単語タイムスタンプ必須の要件による
(2026-08-07の実測比較はBACKEND_DESIGN.md「検証済み」表を参照)。
"""

import numpy as np

from backend.engines.asr.base import ProgressFn, Segment, TranscribeResult, Word


class FasterWhisperEngine:
    name = "faster-whisper"

    def __init__(
        self,
        model_size: str = "large-v3",
        device: str = "cuda",
        # ★ Blackwell(RTX 50/RTX PRO 6000)ではint8がCUBLAS_STATUS_NOT_SUPPORTEDで
        #   クラッシュする既知の不具合があるため、必ず float16 を使用する
        compute_type: str = "float16",
        beam_size: int = 5,
        vad_filter: bool = True,
    ):
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self.beam_size = beam_size
        self.vad_filter = vad_filter
        self._model = None

    def load(self):
        if self._model is None:
            from faster_whisper import WhisperModel

            self._model = WhisperModel(
                self.model_size, device=self.device, compute_type=self.compute_type
            )
        return self._model

    def transcribe(
        self,
        audio: np.ndarray,
        language: str | None = None,
        progress: ProgressFn | None = None,
        initial_prompt: str | None = None,
    ) -> TranscribeResult:
        model = self.load()
        segments, info = model.transcribe(
            audio,
            language=language,
            beam_size=self.beam_size,
            vad_filter=self.vad_filter,
            word_timestamps=True,  # 話者割り当てと字幕同期の精度向上に必要
            initial_prompt=initial_prompt,
        )

        total = len(audio) / 16000
        out: list[Segment] = []
        for seg in segments:  # ジェネレータなので逐次消費して進捗を出す
            out.append(
                Segment(
                    start=seg.start,
                    end=seg.end,
                    text=seg.text.strip(),
                    words=[
                        Word(w.start, w.end, w.word, getattr(w, "probability", None))
                        for w in (seg.words or [])
                    ] or None,
                    confidence=getattr(seg, "avg_logprob", None),
                )
            )
            if progress and total:
                progress(min(seg.end / total, 1.0))

        return TranscribeResult(
            segments=out,
            language=info.language,
            language_probability=info.language_probability,
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
