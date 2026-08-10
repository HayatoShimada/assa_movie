"""話者分離エンジンの選択。

2026-08-08の実測(300秒の対談音声 / RX 7900 XTX機):

| エンジン    | 実時間比 | 依存        | HFトークン |
|-------------|---------|-------------|-----------|
| onnx        |  10.7倍 | 76MBのONNX  | 不要      |
| pyannote    |   2.8倍 | torch 14GB  | 必要      |

話者割り当ての一致率は94.8%。ONNX版が速く・軽く・トークン不要なので、
**pyannoteは2026-08-09に削除した**(docs/V1_PLAN.md M23 / M41)。
配布物にtorchを入れていないため、pyannoteはインストール版では一度も動かず、
「選べるのに選ぶと落ちる」選択肢になっていた。
"""

from backend.engines.diarize import onnx

Turn = tuple[float, float, str]


def available() -> bool:
    """話者分離が使える状態か(モデルが揃っているか)。UIのready表示用"""
    return onnx.is_available()


def run_diarization(audio, settings, progress=None) -> tuple[list[Turn], str | None]:
    """話者分離を実行し、(区間リスト, 使ったエンジン名) を返す。

    モデルが無ければ ([], None) を返す。話者分離は必須ではないので、
    ここで例外にせずジョブを続行させる。
    progress には 0..1 の進捗が届く(長尺では数分かかるため表示に使う)。
    """
    if not onnx.is_available():
        return [], None
    turns = onnx.run_diarization(
        audio, num_speakers=settings.num_speakers, progress=progress
    )
    return turns, "onnx"
