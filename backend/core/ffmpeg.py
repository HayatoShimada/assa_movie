"""ffmpeg / ffprobe の実行パスを1箇所で決める。

Linuxは `.deb` の依存で入るが、WindowsとmacOSには標準で入っていない。
「利用者が別途インストールする」方式はインストーラを配っている以上ちぐはぐで、
実際v0.9.2のWindows版はffmpegが無いせいで起動すらできなかった。だから同梱する。

探索は **PATH → 同梱** の順。自分でffmpegを入れている人はビルドやバージョンを
選んでいるので、その意図を優先する(whisper-cliと同じ考え方。
backend/engines/asr/whispercpp.py)。

同梱物の場所は自分で組み立てない。パッケージ形式で変わる(.debなら
/usr/lib/KirinukiStudio、AppImageなら展開先、Windowsならインストール先)ので、
Tauriシェルが KS_RESOURCE_DIR で教えてくれた場所を使う。
"""

import os
import platform
import shutil
import sys
from pathlib import Path
from typing import Callable

# 同梱物の中での置き場所(tauri.windows.conf.json の resources と対応)
BUNDLED_SUBDIR = "bin"


def bundled_dir() -> Path:
    """同梱物の置き場所。開発中は実行ファイルの隣を見る"""
    resource_dir = os.environ.get("KS_RESOURCE_DIR", "").strip()
    return Path(resource_dir) if resource_dir else Path(sys.executable).parent


def exe_name(name: str, os_name: str | None = None) -> str:
    """Windowsの実行ファイルには .exe が付く"""
    os_name = os_name or platform.system()
    return f"{name}.exe" if os_name == "Windows" else name


def resolve(
    name: str,
    which: Callable[[str], str | None] | None = None,
    bundled: Path | None = None,
    os_name: str | None = None,
) -> str | None:
    """`ffmpeg` / `ffprobe` の実行パスを返す。どこにも無ければ None。

    依存を注入できるようにしてあるのは、OSを跨いだ判定をテーブル駆動で
    確かめるため(tests/test_m32_windows_startup.py)。
    """
    which = shutil.which if which is None else which
    found = which(name)
    if found:
        return found
    base = bundled_dir() if bundled is None else bundled
    candidate = base / BUNDLED_SUBDIR / exe_name(name, os_name)
    return str(candidate) if candidate.is_file() else None


def ffmpeg_path() -> str | None:
    return resolve("ffmpeg")


def ffprobe_path() -> str | None:
    return resolve("ffprobe")


def missing_message(os_name: str | None = None) -> str:
    """ffmpegが見つからないときの案内。OSごとに入れ方が違う"""
    os_name = os_name or platform.system()
    if os_name == "Windows":
        return (
            "ffmpegが見つかりません。通常はアプリに同梱されています。"
            "インストールし直すか、公式サイトから導入してPATHを通してください"
        )
    if os_name == "Darwin":
        return "ffmpegが見つかりません。`brew install ffmpeg` でインストールしてください"
    return "ffmpegが見つかりません。`sudo apt install ffmpeg` でインストールしてください"
