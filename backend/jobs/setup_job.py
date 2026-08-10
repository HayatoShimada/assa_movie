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
from backend.engines.diarize.model_sources import (
    EMBEDDING_URL,
    SEGMENTATION_SHARE,
    SEGMENTATION_URL,
    TOTAL_SIZE_MB as DIARIZATION_SIZE_MB,
)
from backend.jobs.queue import register

WHISPERCPP_MODEL_URL = (
    "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3.bin"
)
WHISPERCPP_SIZE_MB = 3100


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


def fetch_whispercpp_model(progress) -> None:
    """whisper.cpp用のggmlモデル(3.1GB)を取得する。取得済みなら何もしない。

    完了してから所定の場所に置く。中途半端なファイルが残ると
    `is_available()` が「使える」と誤判定してしまう。
    """
    model = whispercpp.resolve_model()
    if model.is_file():
        progress(1.0)
        return

    model.parent.mkdir(parents=True, exist_ok=True)
    staging = model.with_suffix(model.suffix + ".part")
    try:
        download(WHISPERCPP_MODEL_URL, staging, progress)
        staging.replace(model)
        progress(1.0)
    finally:
        staging.unlink(missing_ok=True)


def status() -> dict:
    """セットアップの状態(設定タブのセットアップパネル用)"""
    from backend.core import hwprofile

    # この機体の確定構成でwhisper.cppモデルが必須か(GPU機は取得しないと文字起こし不可)
    model_required = hwprofile.resolve_spec(hwprofile.current()).needs_whispercpp_model
    return {
        "diarization": {
            "label": "話者分離モデル",
            # 同梱物も探す。配布版はモデルを積んでいるので取得は不要になる
            "ready": onnx.is_available(),
            "size_mb": DIARIZATION_SIZE_MB,
            "installable": True,
            "required": False,
            "note": "話者を自動で見分けます。無くても文字起こしはできます。",
        },
        "whispercpp": {
            "label": "文字起こしモデル(whisper.cpp)",
            "ready": whispercpp.is_available(),
            "size_mb": WHISPERCPP_SIZE_MB,
            # バイナリが無ければモデルだけ3.1GB落としても使えないので取得させない
            "installable": whispercpp.resolve_binary() is not None,
            "required": model_required,
            "note": _whispercpp_note(model_required),
        },
    }


def _whispercpp_note(required: bool) -> str:
    if whispercpp.resolve_binary() is None:
        return (
            "本体が見つかりません。`./dev.sh whispercpp` でビルドしてください。"
        )
    if required:
        return "この機体の文字起こしに必須です。取得しないと文字起こしを開始できません。"
    return "この機体(CPU実行)では使いません。"


@register("setup_diarization")
def run_setup_diarization(conn, media_id, params, progress) -> None:
    fetch_diarization_models(progress)


@register("setup_whispercpp")
def run_setup_whispercpp(conn, media_id, params, progress) -> None:
    fetch_whispercpp_model(progress)
