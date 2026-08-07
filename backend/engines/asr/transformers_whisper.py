"""transformers版Whisperエンジン(ROCm向け)。

faster-whisper(CTranslate2)はROCm非対応のため、AMD GPUでは
PyTorch(HIP)で動くtransformersのWhisperを使う(DESIGN.md「制約」参照)。

制限(faster-whisperとの差分):
- initial_prompt 非対応(transformersのprompt_ids対応が不安定なため無視してログのみ)
- 進捗はセグメント単位で出せないため開始・完了の粗い通知のみ
"""

import logging

import numpy as np

from backend.core.device import detect_accel
from backend.engines.asr.base import ProgressFn, Segment, TranscribeResult, Word

logger = logging.getLogger(__name__)

SAMPLE_RATE = 16000
# この秒数以上の無音を挟んだらセグメントを分ける(字幕の切れ目として自然な値)
PAUSE_SPLIT_SEC = 0.8
# セグメント末尾として扱う文末記号(全角・半角)
SENTENCE_END = ("。", "?", "!", "?", "!")
# 句読点もポーズも無い発話が続く場合の強制分割(字幕1枚に収まる長さ)
MAX_SEGMENT_SEC = 8.0
MAX_SEGMENT_CHARS = 30
# パイプラインは単語タイムスタンプ用の注意重みを音声全体分GPUに貯め込むため、
# 長尺はこの秒数で分割して逐次処理する(ピークVRAMを一定に保つ+進捗が細かくなる)。
# 60秒=約2〜3チャンクはバッチ4でも24GBに収まることを実測済み
SLICE_SEC = 60


def chunks_to_words(chunks: list[dict]) -> list[Word]:
    """transformersのword timestamp出力({'text','timestamp':(s,e)})をWord列へ"""
    words: list[Word] = []
    for c in chunks:
        text = (c.get("text") or "").strip()
        if not text:
            continue
        start, end = c.get("timestamp") or (None, None)
        if start is None:
            continue
        if end is None:
            # 末尾チャンクはendがNoneになることがあるため、文字数から表示時間を推定
            end = start + max(0.1, 0.1 * len(text))
        words.append(Word(start=float(start), end=float(end), text=text))
    return words


def words_to_segments(words: list[Word]) -> list[Segment]:
    """Word列をポーズ・文末記号でセグメントに区切る(純関数)"""
    segments: list[Segment] = []
    current: list[Word] = []

    def flush():
        if current:
            segments.append(
                Segment(
                    start=current[0].start,
                    end=current[-1].end,
                    text="".join(w.text for w in current),
                    words=list(current),
                )
            )
            current.clear()

    for w in words:
        if current and w.start - current[-1].end >= PAUSE_SPLIT_SEC:
            flush()
        # 句読点もポーズも無いまま長くなったら、字幕1枚に収まる単位で切る
        if current and (
            w.end - current[0].start > MAX_SEGMENT_SEC
            or sum(len(x.text) for x in current) + len(w.text) > MAX_SEGMENT_CHARS
        ):
            flush()
        current.append(w)
        if w.text.endswith(SENTENCE_END):
            flush()
    flush()
    return segments


class TransformersWhisperEngine:
    name = "transformers-whisper"

    def __init__(
        self,
        model_id: str = "openai/whisper-large-v3",
        device: str = "cuda",
        pipeline_factory=None,  # テスト用の差し替え口
    ):
        self.model_id = model_id
        self.device = device
        self._pipeline_factory = pipeline_factory
        self._pipe = None

    def load(self):
        if self._pipe is None:
            if self._pipeline_factory is not None:
                self._pipe = self._pipeline_factory()
            else:
                import torch
                from transformers import (
                    AutoModelForSpeechSeq2Seq,
                    AutoProcessor,
                    pipeline,
                )

                dtype = torch.float16 if self.device != "cpu" else torch.float32
                model = AutoModelForSpeechSeq2Seq.from_pretrained(
                    self.model_id, dtype=dtype, low_cpu_mem_usage=True
                )
                if self.device != "cpu" and detect_accel() == "rocm":
                    # ROCm環境では通常メモリ→GPUの転送がIOMMU構成の影響で
                    # 1テンソルあたり0.5秒超かかることがあり、約1000テンソルの
                    # ロードが数分に達する(RX 7900 XTX実測: 9分→7秒)。
                    # page-lockedメモリ経由なら本来の帯域が出る
                    for p in model.parameters():
                        p.data = p.data.pin_memory()
                    for b in model.buffers():
                        b.data = b.data.pin_memory()
                model.to(self.device)
                processor = AutoProcessor.from_pretrained(self.model_id)
                self._pipe = pipeline(
                    "automatic-speech-recognition",
                    model=model,
                    tokenizer=processor.tokenizer,
                    feature_extractor=processor.feature_extractor,
                    device=self.device,
                )
        return self._pipe

    def transcribe(
        self,
        audio: np.ndarray,
        language: str | None = None,
        progress: ProgressFn | None = None,
        initial_prompt: str | None = None,
    ) -> TranscribeResult:
        if initial_prompt:
            logger.info("transformersエンジンはinitial_promptに未対応のため無視します")
        pipe = self.load()
        if progress:
            progress(0.02)
        generate_kwargs = {"task": "transcribe"}
        if language:
            generate_kwargs["language"] = language

        def run(piece):
            # batch_size>1はROCm実測で速度向上せずVRAMだけ消費(単語TSの注意重み保持が
            # バッチ分増えるため)。batch=1+60秒スライスが最速かつOOMしない
            return pipe(
                {"array": piece, "sampling_rate": SAMPLE_RATE},
                return_timestamps="word",
                chunk_length_s=30,
                ignore_warning=True,  # chunk_length_sの実験的警告(既知・許容)を抑制
                generate_kwargs=generate_kwargs,
            )

        step = SLICE_SEC * SAMPLE_RATE
        starts = list(range(0, max(1, len(audio)), step))
        words: list[Word] = []
        for i, start in enumerate(starts):
            out = run(audio[start:start + step])
            offset = start / SAMPLE_RATE
            for w in chunks_to_words(out.get("chunks") or []):
                words.append(Word(start=w.start + offset, end=w.end + offset, text=w.text))
            if progress:
                progress(0.02 + 0.98 * (i + 1) / len(starts))
        segments = words_to_segments(words)
        if progress:
            progress(1.0)
        return TranscribeResult(segments=segments, language=language or "")

    def unload(self) -> None:
        if self._pipe is not None:
            del self._pipe
            self._pipe = None
            try:
                import torch

                torch.cuda.empty_cache()
            except Exception:
                pass
