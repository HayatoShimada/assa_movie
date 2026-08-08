"""話者分離エンジンの選択。

2026-08-08の実測(300秒の対談音声 / RX 7900 XTX機):

| エンジン    | 実時間比 | 依存        | HFトークン |
|-------------|---------|-------------|-----------|
| onnx        |  10.7倍 | 76MBのONNX  | 不要      |
| pyannote    |   2.8倍 | torch 14GB  | 必要      |

話者割り当ての一致率は94.8%。ONNX版が速く・軽く・トークン不要なので既定にする
(docs/V1_PLAN.md M23)。pyannoteは比較用・既存環境の互換のために残す。
"""

from backend.engines.diarize import onnx, pyannote

ENGINES: dict[str, str] = {
    "auto": "自動(ONNX優先)",
    "onnx": "ONNX(高速・軽量・既定)",
    "pyannote": "pyannote(torch・要HFトークン)",
}

Turn = tuple[float, float, str]


def resolve_engine(engine_id: str, has_token: bool = False) -> str | None:
    """`auto` を実際のエンジンに解決する。使えるものが無ければNone。

    ONNXモデルが未取得なら、HFトークンがある環境に限りpyannoteへ落とす。
    """
    # pyannoteはトークンだけでなくtorchも要る。配布版はtorchを同梱していないので、
    # トークンがあっても動かない。見た目だけ選べる状態にしない
    pyannote_ready = has_token and pyannote.is_available()
    if engine_id == "onnx":
        return "onnx" if onnx.is_available() else None
    if engine_id == "pyannote":
        return "pyannote" if pyannote_ready else None
    if onnx.is_available():
        return "onnx"
    return "pyannote" if pyannote_ready else None


def run_diarization(audio, settings, token: str | None = None) -> tuple[list[Turn], str | None]:
    """設定に従って話者分離を実行し、(区間リスト, 使ったエンジン名) を返す。

    使えるエンジンが無ければ ([], None) を返す。話者分離は必須ではないので、
    ここで例外にせずジョブを続行させる。
    """
    engine_id = getattr(settings, "diarization_engine", "auto")
    if engine_id not in ENGINES:
        raise ValueError(
            f"未知の話者分離エンジン: {engine_id}(選択肢: {', '.join(ENGINES)})"
        )
    engine = resolve_engine(engine_id, has_token=bool(token))
    if engine == "onnx":
        return onnx.run_diarization(audio, num_speakers=settings.num_speakers), "onnx"
    if engine == "pyannote":
        turns = pyannote.run_diarization(
            audio, token, model=settings.diarization_model, num_speakers=settings.num_speakers
        )
        return turns, "pyannote"
    return [], None
