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

ENGINES: dict[str, str] = {
    "auto": "自動",
    "onnx": "ONNX(高速・軽量・トークン不要)",
}

Turn = tuple[float, float, str]


def resolve_engine(engine_id: str) -> str | None:
    """`auto` を実際のエンジンに解決する。使えるものが無ければNone"""
    return "onnx" if onnx.is_available() else None


def run_diarization(audio, settings) -> tuple[list[Turn], str | None]:
    """設定に従って話者分離を実行し、(区間リスト, 使ったエンジン名) を返す。

    使えるエンジンが無ければ ([], None) を返す。話者分離は必須ではないので、
    ここで例外にせずジョブを続行させる。
    """
    engine_id = getattr(settings, "diarization_engine", "auto")
    if engine_id not in ENGINES:
        raise ValueError(
            f"未知の話者分離エンジン: {engine_id}(選択肢: {', '.join(ENGINES)})"
        )
    if resolve_engine(engine_id) == "onnx":
        return onnx.run_diarization(audio, num_speakers=settings.num_speakers), "onnx"
    return [], None
