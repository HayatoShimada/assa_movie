"""ffmpegによるクリップ切り出しと字幕焼き込み。

ffmpeg本体の場所は backend/core/ffmpeg.py が決める(配布版は同梱物を使う)。
"""

import platform
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path


from backend.core.ffmpeg import ffmpeg_path, ffprobe_path, missing_message

VAAPI_DEVICE = "/dev/dri/renderD128"

# エンコーダごとの品質指定。同じ「だいたいCRF 23相当」でも指定方法が全部違う。
#
# ここを libx264 決め打ちにしていたため、_pick_encoder が qsv/amf/mf/openh264 を
# 選んでも実際には libx264 で書き出そうとしていた。同梱するLGPLビルドに
# libx264 は入っていないので、選ばれた側をそのまま使う
ENCODER_QUALITY: dict[str, list[str]] = {
    "libx264": ["-preset", "veryfast", "-crf", "20"],
    "h264_nvenc": ["-preset", "p4", "-cq", "23"],
    "h264_vaapi": ["-qp", "23"],
    "h264_qsv": ["-global_quality", "23"],
    "h264_amf": ["-rc", "cqp", "-qp_i", "23", "-qp_p", "23"],
    # MediaFoundationは品質指定の受け付け方がドライバ依存なので既定に任せる
    "h264_mf": [],
    # openh264にはCRF相当が無く、ビットレート指定しかできない
    "libopenh264": ["-b:v", "6M"],
}
# 入れ方はOSごとに違う。Linuxの案内をWindows/macOSに出しても意味がない
FFMPEG_MISSING_MSG = missing_message()


def _pick_encoder(
    encoders_output: str,
    has_nvidia: bool,
    has_dri: bool,
    os_name: str | None = None,
) -> str:
    """ffmpegのエンコーダ一覧と実デバイスの有無からH264エンコーダを選ぶ(純関数)。

    ffmpegはNVIDIA機でなくてもh264_nvencを列挙するため、
    実デバイス(/dev/nvidia0 や nvidia-smi)の存在まで確認する。これはLinuxに
    限った話ではなく、Windowsでも同じだった(NVIDIA非搭載機で選ばれて書き出しが
    落ちる)。

    ハードウェアエンコーダはOSごとに別物なので、そのOSに無いものは候補にしない
    (指定すると書き出しが落ちる)。列挙されていないものも選ばない。
    """
    os_name = os_name or platform.system()
    if os_name == "Darwin":
        # Apple SiliconのハードウェアエンコーダはVideoToolbox経由
        candidates = ["h264_videotoolbox"]
    elif os_name == "Windows":
        # VAAPIはLinux専用。Windowsはベンダーごとに別のエンコーダ。
        # 同梱するのはLGPLビルドでlibx264が入っていないため、ハードウェアが
        # 使えない機体向けに h264_mf(Windows標準) と libopenh264(BSD) まで並べる
        candidates = ["h264_nvenc", "h264_qsv", "h264_amf", "h264_mf", "libopenh264"]
    else:
        candidates = ["h264_nvenc", "h264_vaapi"]

    for name in candidates:
        if name not in encoders_output:
            continue
        # nvencの列挙はOSを問わずあてにならない。NVIDIAが無いWindows機でも
        # h264_nvenc は一覧に出るが、実行すると nvcuda.dll が読めずに失敗する
        # (実測。BtbNの配布ビルドでも同じ)。ドライバの有無まで見る
        if name == "h264_nvenc" and not has_nvidia:
            continue
        # VAAPIはLinux専用。デバイスファイルの有無で判断する
        if os_name == "Linux" and name == "h264_vaapi" and not has_dri:
            continue
        return name
    return "libx264"


@lru_cache(maxsize=1)
def detect_encoder() -> str | None:
    """使うH264エンコーダを返す。ffmpeg自体が無ければNone"""
    exe = ffmpeg_path()
    if exe is None:
        return None
    try:
        out = subprocess.run(
            [exe, "-hide_banner", "-encoders"],
            capture_output=True, text=True, timeout=30,
        )
        encoders = out.stdout
    except subprocess.SubprocessError:
        encoders = ""
    has_nvidia = Path("/dev/nvidia0").exists() or bool(shutil.which("nvidia-smi"))
    return _pick_encoder(encoders, has_nvidia, Path(VAAPI_DEVICE).exists())


def probe_media(path: Path) -> tuple[float | None, int | None, int | None]:
    """(再生時間, 幅, 高さ)を返す。ffprobe優先、無ければOpenCVフォールバック"""
    probe = ffprobe_path()
    if probe:
        try:
            import json

            out = subprocess.run(
                [probe, "-v", "error", "-select_streams", "v:0",
                 "-show_entries", "stream=width,height",
                 "-show_entries", "format=duration", "-of", "json", str(path)],
                capture_output=True, text=True, timeout=60,
            )
            if out.returncode == 0:
                data = json.loads(out.stdout)
                stream = (data.get("streams") or [{}])[0]
                dur = data.get("format", {}).get("duration")
                return (
                    float(dur) if dur else None,
                    stream.get("width"), stream.get("height"),
                )
        except (ValueError, subprocess.SubprocessError):
            pass
    try:
        # opencvのwheelはffmpeg同梱なのでシステムffmpeg不在でも動く
        import cv2

        cap = cv2.VideoCapture(str(path))
        try:
            w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or None
            h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or None
            fps = cap.get(cv2.CAP_PROP_FPS)
            frames = cap.get(cv2.CAP_PROP_FRAME_COUNT)
            dur = frames / fps if fps and frames > 0 else None
            return dur, w, h
        finally:
            cap.release()
    except Exception:
        return None, None, None


def _escape_filter_path(path: Path) -> str:
    return str(path).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")


def keep_intervals(
    duration: float, cuts: list[tuple[float, float]], min_len: float = 0.1
) -> list[tuple[float, float]]:
    """中抜き区間の補集合(残す区間)を返す。重なり・順不同の cuts も整理する"""
    merged: list[tuple[float, float]] = []
    for s, e in sorted((max(0.0, s), min(duration, e)) for s, e in cuts if e > s):
        if merged and s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))
    keeps = []
    pos = 0.0
    for s, e in merged:
        if s - pos >= min_len:
            keeps.append((pos, s))
        pos = max(pos, e)
    if duration - pos >= min_len:
        keeps.append((pos, duration))
    return keeps


def build_export_cmd(
    input_path: Path,
    out_path: Path,
    start: float,
    end: float,
    ass_path: Path | None = None,
    encoder: str | None = None,
    cuts: list[tuple[float, float]] | None = None,
    layout_filter: str | None = None,
) -> list[str]:
    """切り出し+レイアウト変換+字幕焼き込み+中抜きのffmpegコマンドを組み立てる。

    - -ss を -i の前に置く高速シーク。ASS・cutsはクリップ相対時刻で指定する
    - フィルタは レイアウト変換 → 字幕 → trim+concat →(vaapi時)hwupload の順。
      字幕はレイアウト変換後に焼くのでASSのPlayResは出力解像度に合わせる
    - 中抜きは trim+concat 方式(select式はffmpegのバージョンにより挙動が
      不安定なことを実測で確認したため使わない)。字幕は「カット前」に焼くので
      カット後もタイミングが正しく繋がる
    - layout_filter は "[0:v]...[vlay]" 形式のグラフ断片(pipeline/layout.py参照)
    """
    if encoder is None:
        encoder = detect_encoder()
    if encoder is None:
        raise RuntimeError(FFMPEG_MISSING_MSG)
    duration = max(0.1, end - start)
    # detect_encoder が通っている = ffmpegは見つかっている
    cmd = [ffmpeg_path() or "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
           "-progress", "pipe:1"]
    if encoder == "h264_vaapi":
        cmd += ["-vaapi_device", VAAPI_DEVICE]
    cmd += ["-ss", f"{start:.3f}", "-i", str(input_path), "-t", f"{duration:.3f}"]

    ass_filter = f"ass='{_escape_filter_path(ass_path)}'" if ass_path else None
    keeps = keep_intervals(duration, cuts or []) if cuts else []
    has_cuts = bool(keeps) and keeps != [(0.0, duration)]
    hw_tail = "format=nv12,hwupload" if encoder == "h264_vaapi" else None

    if layout_filter or has_cuts:
        graph: list[str] = []
        src_v = "[0:v]"
        if layout_filter:
            graph.append(layout_filter)  # [0:v] を消費して [vlay] を出す契約
            src_v = "[vlay]"
        if ass_filter:
            graph.append(f"{src_v}{ass_filter}[vsub]")
            src_v = "[vsub]"
        map_a = "0:a"
        if has_cuts:
            n = len(keeps)
            if n > 1:
                graph.append(f"{src_v}split={n}" + "".join(f"[vin{i}]" for i in range(n)))
                graph.append(f"[0:a]asplit={n}" + "".join(f"[ain{i}]" for i in range(n)))
                v_srcs = [f"[vin{i}]" for i in range(n)]
                a_srcs = [f"[ain{i}]" for i in range(n)]
            else:
                v_srcs, a_srcs = [src_v], ["[0:a]"]
            for i, (s, e) in enumerate(keeps):
                graph.append(
                    f"{v_srcs[i]}trim=start={s:.3f}:end={e:.3f},setpts=PTS-STARTPTS[v{i}]"
                )
                graph.append(
                    f"{a_srcs[i]}atrim=start={s:.3f}:end={e:.3f},asetpts=PTS-STARTPTS[a{i}]"
                )
            pairs = "".join(f"[v{i}][a{i}]" for i in range(n))
            graph.append(f"{pairs}concat=n={n}:v=1:a=1[vout][aout]")
            src_v, map_a = "[vout]", "[aout]"
        if hw_tail:
            graph.append(f"{src_v}{hw_tail}[vhw]")
            src_v = "[vhw]"
        cmd += ["-filter_complex", ";".join(graph), "-map", src_v, "-map", map_a]
    else:
        vf = ",".join(f for f in (ass_filter, hw_tail) if f)
        if vf:
            cmd += ["-vf", vf]

    cmd += ["-c:v", encoder, *ENCODER_QUALITY.get(encoder, [])]
    # AACはffmpeg内蔵のエンコーダ。外部ライブラリを足さずに使える
    cmd += ["-c:a", "aac", "-b:a", "192k", str(out_path)]
    return cmd


def run_export(
    cmd: list[str],
    duration: float,
    progress=None,
    timeout: int = 3600,
) -> None:
    """ffmpegを実行し、-progress pipe:1 の out_time_ms から進捗を報告する"""
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            if progress and line.startswith("out_time_ms="):
                try:
                    ms = int(line.split("=")[1])
                    progress(min(0.99, (ms / 1_000_000) / duration))
                except ValueError:
                    pass
        proc.wait(timeout=timeout)
    finally:
        if proc.poll() is None:
            proc.kill()
    if proc.returncode != 0:
        err = proc.stderr.read() if proc.stderr else ""
        raise RuntimeError(f"ffmpegが失敗しました(exit {proc.returncode}): {err[-1500:]}")
