"""初回セットアップ: 話者分離モデルの取得。

インストール版のユーザーは `./dev.sh diarize-models` を叩けないので、
アプリの中から取得できるようにする。

whisper.cppはhipccでのビルドが要るためアプリからは入れられない。
状態だけ返して、手順を画面で案内する。
"""

import shutil
import tarfile
import tempfile
from pathlib import Path

import requests

from backend.engines.asr import whispercpp
from backend.engines.diarize import onnx
from backend.jobs.queue import register

SEGMENTATION_URL = (
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-segmentation-models/"
    "sherpa-onnx-pyannote-segmentation-3-0.tar.bz2"
)
EMBEDDING_URL = (
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models/"
    "3dspeaker_speech_eres2netv2_sv_zh-cn_16k-common.onnx"
)
DIARIZATION_SIZE_MB = 76
# 分離モデルの取得が全体の何割か(残りが埋め込みモデル。実サイズの比率に合わせる)
SEGMENTATION_SHARE = 0.1


def download(url: str, dest: Path, progress) -> None:
    """URLをdestに保存する。進捗は0〜1で通知する"""
    dest.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, stream=True, timeout=60) as resp:
        resp.raise_for_status()
        total = int(resp.headers.get("content-length", 0))
        done = 0
        with dest.open("wb") as f:
            for chunk in resp.iter_content(chunk_size=1024 * 256):
                f.write(chunk)
                done += len(chunk)
                if total:
                    progress(min(1.0, done / total))
    progress(1.0)


def extract_archive(archive: Path, dest_dir: Path) -> None:
    with tarfile.open(archive) as tar:
        tar.extractall(dest_dir, filter="data")


def fetch_diarization_models(progress) -> None:
    """話者分離モデル(計76MB)を取得する。取得済みなら何もしない。

    完了してから所定の場所に置く。中途半端なファイルが残ると
    `is_available()` が「使える」と誤判定してしまう。
    """
    if onnx.is_available(onnx.DEFAULT_SEGMENTATION, onnx.DEFAULT_EMBEDDING):
        progress(1.0)
        return

    models_dir = onnx.DEFAULT_SEGMENTATION.parent.parent
    models_dir.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix="ks-models-", dir=models_dir))
    try:
        archive = staging / "segmentation.tar.bz2"
        download(SEGMENTATION_URL, archive, lambda p: progress(p * SEGMENTATION_SHARE))
        extract_archive(archive, models_dir)

        download(
            EMBEDDING_URL,
            staging / "embedding.onnx",
            lambda p: progress(SEGMENTATION_SHARE + p * (1 - SEGMENTATION_SHARE)),
        )
        shutil.move(str(staging / "embedding.onnx"), onnx.DEFAULT_EMBEDDING)
        progress(1.0)
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def status() -> dict:
    """セットアップの状態(設定タブのセットアップパネル用)"""
    return {
        "diarization": {
            "label": "話者分離モデル",
            "ready": onnx.is_available(onnx.DEFAULT_SEGMENTATION, onnx.DEFAULT_EMBEDDING),
            "size_mb": DIARIZATION_SIZE_MB,
            "installable": True,
            "note": "話者を自動で見分けます。無くても文字起こしはできます。",
        },
        "whispercpp": {
            "label": "whisper.cpp(高速なASR)",
            "ready": whispercpp.is_available(),
            "size_mb": 3100,
            # hipccでのビルドが要るのでアプリからは入れられない
            "installable": False,
            "note": "AMD GPUで最速のASRです。`./dev.sh whispercpp` でビルドしてください。",
        },
    }


@register("setup_diarization")
def run_setup_diarization(conn, media_id, params, progress) -> None:
    fetch_diarization_models(progress)
