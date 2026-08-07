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


def build_export_cmd(
    input_path: Path,
    out_path: Path,
    start: float,
    end: float,
    ass_path: Path | None = None,
    use_nvenc: bool | None = None,
) -> list[str]:
    """切り出し+字幕焼き込みのffmpegコマンドを組み立てる。

    - -ss を -i の前に置く高速シーク。ASSはクリップ相対時刻で生成されている前提
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
    if ass_path is not None:
        # パスにコロン等が含まれてもよいようにエスケープする
        escaped = str(ass_path).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
        cmd += ["-vf", f"ass='{escaped}'"]
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
