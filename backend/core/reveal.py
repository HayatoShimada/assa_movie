"""書き出したファイル・フォルダをOSのファイラーで見せる(と、更新のページをブラウザで開く)。

デスクトップ版(Tauri)とブラウザで動かす開発版の両方で同じように動かすため、
フロント(WebView)ではなくバックエンドが開く。どのパスを開いてよいかは
呼び出し側(backend/api/jobs.py)が書き出し先に限って確かめる。
任意のパスを受け取るAPIからは呼ばないこと。
"""

import os
import platform
import subprocess
import sys
from pathlib import Path, PurePath


def reveal_command(path: PurePath, os_name: str) -> list[str] | str:
    """ファイルを見せるコマンド(純関数)。

    - macOS: `open -R` でFinderに表示して選択する
    - Windows: `explorer /select,"..."` で選択する。空白を含むパスは
      引用符がこの形で付いていないとexplorerが解釈できないため文字列で組む
    - Linux: xdg-open はファイルを選択できないのでフォルダを開く
      (ファイルを渡すと既定の動画プレイヤーで再生されてしまう)
    """
    if os_name == "Darwin":
        return ["open", "-R", str(path)]
    if os_name == "Windows":
        return f'explorer /select,"{path}"'
    return ["xdg-open", str(path.parent)]


def open_folder_command(path: PurePath, os_name: str) -> list[str]:
    """フォルダそのものを開くコマンド(純関数)。書き出す前の「書き出し先を開く」用"""
    if os_name == "Darwin":
        return ["open", str(path)]
    if os_name == "Windows":
        return ["explorer", str(path)]
    return ["xdg-open", str(path)]


def open_url_command(url: str, os_name: str) -> list[str]:
    """URLを既定のブラウザで開くコマンド(純関数)。

    Tauriのwebviewはリンクを外のブラウザで開かないので、ファイラーと同じく
    バックエンドが開く。Windowsは `start` がcmdの内部コマンドなので、
    URLの関連付けを直接呼べる rundll32 を使う(シェルを経由しない)。
    """
    if os_name == "Darwin":
        return ["open", url]
    if os_name == "Windows":
        return ["rundll32", "url.dll,FileProtocolHandler", url]
    return ["xdg-open", url]


def launch_env(environ: dict[str, str], *, frozen: bool) -> dict[str, str]:
    """外部のGUIアプリへ渡す環境変数(純関数)。

    PyInstallerで固めた配布版は、自分の同梱ライブラリを LD_LIBRARY_PATH に
    入れて起動する(元の値は LD_LIBRARY_PATH_ORIG に退避される)。そのまま
    xdg-open に渡すと、ファイラーが同梱の古いライブラリを読んで起動に失敗する。
    """
    env = dict(environ)
    if not frozen:
        return env
    original = env.get("LD_LIBRARY_PATH_ORIG")
    if original is not None:
        env["LD_LIBRARY_PATH"] = original
    else:
        env.pop("LD_LIBRARY_PATH", None)
    return env


def reveal(path: Path, os_name: str | None = None) -> None:
    """ファイラーを起動する。終わりを待たない(ファイラーは開いたまま残る)"""
    _launch(reveal_command(path, os_name or platform.system()))


def open_folder(path: Path, os_name: str | None = None) -> None:
    """フォルダをファイラーで開く"""
    _launch(open_folder_command(path, os_name or platform.system()))


def open_url(url: str, os_name: str | None = None) -> None:
    """URLを既定のブラウザで開く。呼び出し側は決まったURLだけを渡すこと"""
    _launch(open_url_command(url, os_name or platform.system()))


def _launch(cmd: list[str] | str) -> None:
    # 出力は読まない(バイトのまま捨てる)。GUIアプリなので待たない
    subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        env=launch_env(dict(os.environ), frozen=bool(getattr(sys, "frozen", False))),
    )
