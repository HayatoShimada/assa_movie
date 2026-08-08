"""whisper.cpp(hipBLAS)エンジン。ROCmで最も速い。

RX 7900 XTX実測で実時間比11.6倍(公式Whisperの約2.6倍)。
`--output-json-full` を使うと、セグメントごとに全トークンを
`{text, offsets, p}` で返すので、句読点・単語タイムスタンプ・単語確率が
一度に揃う(`-ml` を付けると句読点が落ちるので付けない)。

セグメント分割は whisper.cpp 側が粗い(20秒超もある)ため、
トークン列から `words_to_segments`(ポーズ・句読点・最大長)で切り直す。

バイナリとggml版モデルは別途用意する: `./dev.sh whispercpp`
"""

import json
import logging
import os
import subprocess
import tempfile
import wave
from pathlib import Path

import numpy as np

from backend.engines.asr.base import ProgressFn, Segment, TranscribeResult, Word
from backend.core.paths import cache_dir
from backend.engines.asr.transformers_whisper import words_to_segments

logger = logging.getLogger(__name__)

SAMPLE_RATE = 16000
# 置き場所は backend/core/paths.py が決める(旧名のキャッシュがあればそれを使う)
DEFAULT_HOME = Path(os.environ.get("KS_WHISPERCPP_HOME") or cache_dir())
DEFAULT_BINARY = DEFAULT_HOME / "bin/whisper-cli"
DEFAULT_MODEL = DEFAULT_HOME / "models/ggml-large-v3.bin"
# 長さ0のトークン(句読点など)に与える最小表示時間(秒)
MIN_TOKEN_DURATION = 0.02


def is_available(binary: Path = DEFAULT_BINARY, model: Path = DEFAULT_MODEL) -> bool:
    """実行可能なバイナリとモデルが揃っているか"""
    return binary.is_file() and os.access(binary, os.X_OK) and model.is_file()


def parse_full_json(payload: dict) -> list[Word]:
    """`--output-json-full` の出力からWord列を作る(純関数)。

    特殊トークン([_BEG_] や <|...|>)は字幕に出さない。
    長さ0のトークンには最小の表示時間を与える(1割ほど混ざる)。
    """
    words: list[Word] = []
    for seg in payload.get("transcription") or []:
        for tok in seg.get("tokens") or []:
            text = tok.get("text") or ""
            if not text or text.startswith("[_") or text.startswith("<|"):
                continue
            offsets = tok.get("offsets") or {}
            start = float(offsets.get("from", 0)) / 1000
            end = float(offsets.get("to", 0)) / 1000
            words.append(
                Word(
                    start=start,
                    end=max(end, start + MIN_TOKEN_DURATION),
                    text=text,
                    probability=tok.get("p"),
                )
            )
    return words


def build_command(
    binary: Path,
    model: Path,
    audio_path: Path,
    out_base: Path,
    language: str | None = None,
    beam_size: int = 5,
    initial_prompt: str | None = None,
) -> list[str]:
    """whisper-cliのコマンドを組み立てる(純関数)"""
    cmd = [
        str(binary),
        "-m", str(model),
        "-f", str(audio_path),
        # トークンのタイムスタンプと確率はこのオプションで有効になる
        "-ojf",
        "-of", str(out_base),
        "-bs", str(beam_size),
        "--no-prints",
    ]
    if language:
        cmd += ["-l", language]
    if initial_prompt:
        cmd += ["--prompt", initial_prompt]
    return cmd


class WhisperCppEngine:
    name = "whisper.cpp"

    def __init__(
        self,
        binary: Path = DEFAULT_BINARY,
        model: Path = DEFAULT_MODEL,
        beam_size: int = 5,
        runner=None,  # テスト用の差し替え口
    ):
        self.binary = Path(binary)
        self.model = Path(model)
        self.beam_size = beam_size
        self._runner = runner

    def load(self):
        """CLIは実行のたびにモデルを読むので、ここでは存在確認だけ行う"""
        if self._runner is None and not is_available(self.binary, self.model):
            raise RuntimeError(
                f"whisper.cppが見つかりません({self.binary} / {self.model})。"
                "`./dev.sh whispercpp` で用意してください"
            )
        return self

    def _run(self, cmd: list[str], out_base: Path) -> None:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=7200)
        if proc.returncode != 0:
            raise RuntimeError(
                f"whisper.cppが失敗しました(exit {proc.returncode}): {proc.stderr[-1500:]}"
            )

    def transcribe(
        self,
        audio: np.ndarray,
        language: str | None = None,
        progress: ProgressFn | None = None,
        initial_prompt: str | None = None,
    ) -> TranscribeResult:
        self.load()
        if progress:
            progress(0.02)
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            audio_path = tmp_dir / "audio.wav"
            _write_wav(audio_path, audio)
            out_base = tmp_dir / "out"
            cmd = build_command(
                self.binary, self.model, audio_path, out_base,
                language=language, beam_size=self.beam_size, initial_prompt=initial_prompt,
            )
            run = self._runner or self._run
            run(cmd, out_base)
            payload = json.loads(out_base.with_suffix(".json").read_text(encoding="utf-8"))

        words = parse_full_json(payload)
        segments: list[Segment] = words_to_segments(words)
        if progress:
            progress(1.0)
        return TranscribeResult(segments=segments, language=language or "")

    def unload(self) -> None:
        """CLIは実行ごとに終了するので保持しているものは無い"""


def _write_wav(path: Path, audio: np.ndarray) -> None:
    """16kHzモノラルのWAVに書き出す(CLIはファイルしか受け取らないため)"""
    pcm = np.clip(audio, -1.0, 1.0)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes((pcm * 32767).astype("<i2").tobytes())
