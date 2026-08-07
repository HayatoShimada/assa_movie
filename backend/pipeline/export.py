"""ffmpegによるクリップ切り出しと字幕焼き込み。"""

import shutil
import subprocess
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def has_nvenc() -> bool:
    """NVENC(h264_nvenc)が使えるか"""
    if not shutil.which("ffmpeg"):
        return False
    try:
        out = subprocess.run(
            ["ffmpeg", "-hide_banner", "-encoders"],
            capture_output=True, text=True, timeout=30,
        )
        return "h264_nvenc" in out.stdout
    except subprocess.SubprocessError:
        return False


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
    use_nvenc: bool | None = None,
    cuts: list[tuple[float, float]] | None = None,
) -> list[str]:
    """切り出し+字幕焼き込み+中抜き(ジェットカット)のffmpegコマンドを組み立てる。

    - -ss を -i の前に置く高速シーク。ASS・cutsはクリップ相対時刻で指定する
    - 中抜きは trim+concat 方式(select式はffmpegのバージョンにより挙動が
      不安定なことを実測で確認したため使わない)。字幕は「カット前」に焼くので
      カット後もタイミングが正しく繋がる
    - 字幕焼き込みは再エンコード必須なので、コーデックはNVENC優先
    """
    if use_nvenc is None:
        use_nvenc = has_nvenc()
    duration = max(0.1, end - start)
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-progress", "pipe:1",
        "-ss", f"{start:.3f}", "-i", str(input_path),
        "-t", f"{duration:.3f}",
    ]

    ass_filter = f"ass='{_escape_filter_path(ass_path)}'" if ass_path else None
    keeps = keep_intervals(duration, cuts or []) if cuts else []

    if keeps and len(keeps) >= 1 and (len(keeps) > 1 or keeps != [(0.0, duration)]):
        # 中抜きあり: 字幕焼き込み → 残す区間をtrim → concat
        graph = []
        src_v = "[0:v]"
        if ass_filter:
            graph.append(f"[0:v]{ass_filter}[vsub]")
            src_v = "[vsub]"
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
        cmd += ["-filter_complex", ";".join(graph), "-map", "[vout]", "-map", "[aout]"]
    elif ass_filter:
        cmd += ["-vf", ass_filter]

    if use_nvenc:
        cmd += ["-c:v", "h264_nvenc", "-preset", "p4", "-cq", "23"]
    else:
        cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20"]
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
