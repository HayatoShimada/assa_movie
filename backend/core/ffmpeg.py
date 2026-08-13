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
from pathlib import Path
from typing import Callable

from backend.core.bundled import bundled_dir

# 同梱物の中での置き場所(tauri.windows.conf.json の resources と対応)
BUNDLED_SUBDIR = "bin"


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


def missing_message(os_name: str | None = None, appimage: bool | None = None) -> str:
    """ffmpegが見つからないときの案内。OSごとに入れ方が違う。

    AppImageを分けるのは、`.deb` の依存宣言(linux.deb.depends)がAppImageには
    効かないため。AppImageは依存を宣言する仕組みが無くffmpegも同梱していないので、
    未導入の利用者は書き出しで初めて失敗する。導入手順まで出す。
    """
    os_name = os_name or platform.system()
    if os_name == "Windows":
        return (
            "ffmpegが見つかりません。通常はアプリに同梱されています。"
            "インストールし直すか、公式サイトから導入してPATHを通してください"
        )
    if os_name == "Darwin":
        # brewを案内しない: Homebrewのffmpeg 9はlibassが外されていて、
        # 入れても字幕焼き込みが `ass` フィルタ不在で必ず失敗する(実測)
        return (
            "ffmpegが見つかりません。通常はアプリに同梱されています。"
            "アプリをインストールし直してください"
        )
    # AppImageは起動時に自身のパスを APPIMAGE 環境変数へ入れる
    if appimage is None:
        appimage = bool(os.environ.get("APPIMAGE"))
    if appimage:
        return (
            "ffmpegが見つかりません。AppImage版にはffmpegを同梱していないため、"
            "別途インストールが必要です:"
            " Debian/Ubuntu なら `sudo apt install ffmpeg`、"
            " Fedora なら `sudo dnf install ffmpeg`、"
            " Arch なら `sudo pacman -S ffmpeg`"
        )
    return "ffmpegが見つかりません。`sudo apt install ffmpeg` でインストールしてください"
