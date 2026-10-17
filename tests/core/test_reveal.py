"""書き出し先をOSのファイラーで開く(backend/core/reveal.py)。

デスクトップ版(Tauri)でもブラウザ開発版でも同じ動きにするため、
フロントではなくバックエンドが開く。開けるのは書き出し先だけ(API側で制限)。
"""

from pathlib import Path

import pytest

from backend.core import reveal


@pytest.mark.parametrize(
    "os_name, expected",
    [
        # Linuxのxdg-openはファイルを選択状態にできないのでフォルダを開く
        ("Linux", ["xdg-open", "/data/exports"]),
        # macOSは open -R でFinderに表示して選択する
        ("Darwin", ["open", "-R", "/data/exports/対談_0s-10s_clip1.mp4"]),
    ],
)
def test_reveal_command_unix(os_name, expected):
    target = Path("/data/exports/対談_0s-10s_clip1.mp4")
    assert reveal.reveal_command(target, os_name) == expected


def test_reveal_command_windowsはexplorerで選択状態にする():
    target = Path(r"C:\Users\山田\AppData\Roaming\kirinuki-studio\exports\対談 1_0s-10s.mp4")
    cmd = reveal.reveal_command(target, "Windows")
    # 空白を含むパスは /select,"..." の形でないとexplorerが解釈できない
    assert cmd == f'explorer /select,"{target}"'


@pytest.mark.parametrize(
    "name, environ, frozen, expected",
    [
        ("開発版はそのまま", {"LD_LIBRARY_PATH": "/opt/x"}, False, {"LD_LIBRARY_PATH": "/opt/x"}),
        ("配布版は起動前の値に戻す",
         {"LD_LIBRARY_PATH": "/tmp/_MEI", "LD_LIBRARY_PATH_ORIG": "/opt/x"}, True,
         {"LD_LIBRARY_PATH": "/opt/x", "LD_LIBRARY_PATH_ORIG": "/opt/x"}),
        ("配布版で元が無ければ消す", {"LD_LIBRARY_PATH": "/tmp/_MEI", "HOME": "/h"}, True,
         {"HOME": "/h"}),
    ],
)
def test_launch_env(name, environ, frozen, expected):
    """PyInstallerは自分のライブラリを LD_LIBRARY_PATH に入れる。そのまま
    xdg-open に渡すとファイラーが同梱ライブラリを読んで起動に失敗する"""
    assert reveal.launch_env(environ, frozen=frozen) == expected, name


def test_reveal_はコマンドを起動するだけで待たない(monkeypatch, tmp_path):
    calls = []

    class FakePopen:
        def __init__(self, cmd, **kwargs):
            calls.append((cmd, kwargs))

    monkeypatch.setattr(reveal.subprocess, "Popen", FakePopen)
    target = tmp_path / "exports" / "a.mp4"
    target.parent.mkdir()
    target.write_bytes(b"x")
    reveal.reveal(target, os_name="Linux")
    assert calls[0][0] == ["xdg-open", str(target.parent)]
    assert calls[0][1]["stdout"] is reveal.subprocess.DEVNULL
