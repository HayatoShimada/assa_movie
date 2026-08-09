"""話者分離(pyannote.audio 3.x / torch)。

GPUを使う代わりにtorchが要るため、既定はONNX版(onnx.py)。
HFトークンがある環境で `diarization_engine=pyannote` を選んだときに使う。
話者名の割り当ては labels.py(エンジン非依存)。
"""

import os
from pathlib import Path

import numpy as np

from backend.core import keyfile

SAMPLE_RATE = 16000
DEFAULT_MODEL = "pyannote/speaker-diarization-3.1"

Turn = tuple[float, float, str]


def is_available() -> bool:
    """torch と pyannote.audio が入っているか。

    配布物にはtorchを入れていない(11.5GBあるため)ので、インストール版では常にFalse。
    HFトークンだけを見て「使える」と表示すると、選んだ瞬間に ImportError で落ちる。
    importはしない(torchのimportは実測5秒かかる)。入っているかだけを見る。
    """
    from importlib.util import find_spec

    try:
        return find_spec("torch") is not None and find_spec("pyannote.audio") is not None
    except (ImportError, ValueError):
        return False


def load_hf_token(token_file: Path | None = None) -> str | None:
    token = os.environ.get("HF_TOKEN", "").strip()
    if token.startswith("hf_"):
        return token
    token = keyfile.read(token_file)
    if token and token.startswith("hf_") and "\n" not in token:
        return token
    return None


def run_diarization(
    audio: np.ndarray,
    token: str,
    model: str = DEFAULT_MODEL,
    num_speakers: int | None = 2,
) -> list[Turn]:
    """(開始秒, 終了秒, 話者ラベル) のリストを返す"""
    import warnings

    import torch

    # torchcodec未対応の警告を抑制(音声はメモリ上で直接渡すため不要)
    warnings.filterwarnings("ignore", category=UserWarning, module=r"pyannote\.audio\.core\.io")
    from pyannote.audio import Pipeline

    # torch 2.6以降のweights_only=Trueデフォルトで、pyannote公式チェックポイントの
    # 読み込みに必要なクラスを許可リストに追加(モデル提供元を信頼している前提)
    from pyannote.audio.core.task import Problem, Resolution, Specifications

    torch.serialization.add_safe_globals(
        [torch.torch_version.TorchVersion, Specifications, Problem, Resolution]
    )

    try:
        pipeline = Pipeline.from_pretrained(model, token=token)
    except TypeError:
        # pyannote.audio 3.x は引数名が use_auth_token
        pipeline = Pipeline.from_pretrained(model, use_auth_token=token)
    # ROCmのHIPビルドもtorch上では"cuda"を名乗るのでこの判定で両対応になる
    # (ROCm固有のtorch設定は core/device.py apply_rocm_workarounds が起動時に適用済み)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    pipeline.to(device)

    inputs = {"waveform": torch.from_numpy(audio).unsqueeze(0), "sample_rate": SAMPLE_RATE}
    kwargs = {"num_speakers": num_speakers} if num_speakers is not None else {}
    try:
        result = pipeline(inputs, **kwargs)
    except RuntimeError:
        if device.type != "cuda":
            raise
        # ROCm初期環境でのMIOpenカーネル生成失敗等に備え、CPUで1回だけ再試行する
        print("⚠ GPUでの話者分離に失敗したため、CPUで再試行します。")
        pipeline.to(torch.device("cpu"))
        result = pipeline(inputs, **kwargs)

    # pyannote.audio 4.x はコンテナ型、3.x はAnnotationを直接返す
    annotation = getattr(result, "speaker_diarization", result)
    return [
        (turn.start, turn.end, label)
        for turn, _, label in annotation.itertracks(yield_label=True)
    ]
