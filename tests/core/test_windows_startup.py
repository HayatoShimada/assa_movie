"""M32: Windowsで起動できること。

v0.9.2のWindows版は、インストールはできるのに起動できなかった。原因は2つで、
どちらも「実機で動かすまで気付けない」たぐいのものだった。

1. 日本語Windowsのcp932で「⚠」が出力できず、起動時のprintで落ちる
2. Tauriが配置するサイドカーは `.exe` 付きなのに、Rust側が拡張子なしで探していた

1はここで、2はRust側のテストで担保する(frontend/src-tauri/src/backend.rs)。
実機での通し確認は scripts/verify_windows.ps1。
"""

import io
from pathlib import Path

import pytest

from backend.core import ffmpeg as ffmpeg_mod
from backend.core.console import force_utf8
from backend.pipeline.export import _pick_encoder, build_export_cmd

# 起動時に実際に出力している記号(backend/app.py)。cp932に無い
WARN = "⚠"


def test_cp932では警告記号を出力できない():
    """前提の確認。この性質があるからUTF-8への付け替えが要る"""
    stream = io.TextIOWrapper(io.BytesIO(), encoding="cp932")
    with pytest.raises(UnicodeEncodeError):
        stream.write(f"{WARN} 書き出しには ffmpeg が必要です")
        stream.flush()


def test_付け替えるとcp932のストリームでも書ける():
    stream = io.TextIOWrapper(io.BytesIO(), encoding="cp932")
    assert stream.encoding == "cp932"

    force_utf8(stream)

    assert stream.encoding == "utf-8"
    # 例外が出ないこと自体がこのテストの主張
    stream.write(f"{WARN} 書き出しには ffmpeg が必要です")
    stream.flush()


def test_日本語も欠けずに往復する():
    buf = io.BytesIO()
    stream = io.TextIOWrapper(buf, encoding="cp932")
    force_utf8(stream)
    stream.write("環境: NVIDIA GeForce RTX 5090 (cuda, VRAM 32GB)")
    stream.flush()
    assert buf.getvalue().decode("utf-8") == "環境: NVIDIA GeForce RTX 5090 (cuda, VRAM 32GB)"


@pytest.mark.parametrize(
    "stream",
    [
        None,                      # 差し替えられていて存在しない
        io.StringIO(),             # reconfigureを持たない
        object(),                  # まったく別のもの
    ],
)
def test_付け替えられないストリームでも落ちない(stream):
    """ログの都合でアプリを止めない。pytestが差し替えたstdoutでも同じ"""
    force_utf8(stream)


def test_複数まとめて渡せる():
    out = io.TextIOWrapper(io.BytesIO(), encoding="cp932")
    err = io.TextIOWrapper(io.BytesIO(), encoding="cp932")
    force_utf8(out, err)
    assert out.encoding == "utf-8"
    assert err.encoding == "utf-8"


# ---- 同梱したffmpegの探索 ----
#
# Windows/macOSにffmpegは標準で入っていない。インストーラを配る以上、
# 利用者に別途入れてもらう前提は成り立たない(v0.9.2はffmpegが無いだけで
# 起動に失敗していた)。同梱物を見つけられることをここで担保する。

NOT_ON_PATH = lambda _name: None  # noqa: E731 (テスト内の短い差し替え)


def test_PATHにあるものを優先する(tmp_path):
    """自分でffmpegを入れている人はビルドやバージョンを選んでいる"""
    got = ffmpeg_mod.resolve(
        "ffmpeg", which=lambda _n: r"C:\tools\ffmpeg.exe", bundled=tmp_path, os_name="Windows"
    )
    assert got == r"C:\tools\ffmpeg.exe"


def test_PATHに無ければ同梱を使う(tmp_path):
    bundled = tmp_path / "bin"
    bundled.mkdir()
    (bundled / "ffmpeg.exe").write_bytes(b"")

    got = ffmpeg_mod.resolve("ffmpeg", which=NOT_ON_PATH, bundled=tmp_path, os_name="Windows")

    assert got == str(bundled / "ffmpeg.exe")


def test_ffprobeも同じ規則で探す(tmp_path):
    bundled = tmp_path / "bin"
    bundled.mkdir()
    (bundled / "ffprobe.exe").write_bytes(b"")
    got = ffmpeg_mod.resolve("ffprobe", which=NOT_ON_PATH, bundled=tmp_path, os_name="Windows")
    assert got == str(bundled / "ffprobe.exe")


def test_どちらにも無ければNone(tmp_path):
    assert ffmpeg_mod.resolve("ffmpeg", which=NOT_ON_PATH, bundled=tmp_path, os_name="Windows") is None


def test_Windows以外は拡張子を付けない(tmp_path):
    bundled = tmp_path / "bin"
    bundled.mkdir()
    (bundled / "ffmpeg").write_bytes(b"")
    for os_name in ("Linux", "Darwin"):
        got = ffmpeg_mod.resolve("ffmpeg", which=NOT_ON_PATH, bundled=tmp_path, os_name=os_name)
        assert got == str(bundled / "ffmpeg"), os_name


def test_見つからないときの案内はOSごとに変える():
    """Linuxの `apt install` をWindowsやmacOSに出しても意味がない"""
    assert "同梱" in ffmpeg_mod.missing_message("Windows")
    assert "brew" in ffmpeg_mod.missing_message("Darwin")
    assert "apt" in ffmpeg_mod.missing_message("Linux")


def test_同梱ビルドにlibx264が無くても書き出せる():
    """同梱するのはLGPLビルドでlibx264が入っていない。

    ハードウェアエンコーダが使えない機体でも、h264_mf(Windows標準)か
    libopenh264(BSD)に落ちて書き出しが成立すること。
    """
    lgpl = "libopenh264 h264_amf h264_mf h264_nvenc h264_qsv"
    assert _pick_encoder(lgpl, has_nvidia=True, has_dri=False, os_name="Windows") == "h264_nvenc"
    # NVIDIA以外・Intel以外・AMD以外の機体
    assert _pick_encoder("libopenh264 h264_mf", False, False, os_name="Windows") == "h264_mf"
    # MediaFoundationすら列挙されない場合の最後の砦
    assert _pick_encoder("libopenh264", False, False, os_name="Windows") == "libopenh264"


def test_NVIDIAが無いWindows機でnvencを選ばない():
    """ffmpegはNVIDIAが無くてもh264_nvencを列挙する。

    実測: ドライバが無い機体で選ぶと `Cannot load nvcuda.dll` で書き出しが落ちる。
    列挙されているかどうかではなく、ドライバの有無で判断する。
    """
    lgpl = "libopenh264 h264_mf h264_nvenc"
    assert _pick_encoder(lgpl, has_nvidia=False, has_dri=False, os_name="Windows") == "h264_mf"
    # ドライバがあるなら今までどおりnvencを使う
    assert _pick_encoder(lgpl, has_nvidia=True, has_dri=False, os_name="Windows") == "h264_nvenc"


@pytest.mark.parametrize(
    "encoder,must_contain",
    [
        ("h264_qsv", ["-global_quality"]),
        ("h264_amf", ["-rc", "cqp"]),
        ("h264_mf", []),           # 品質指定はドライバ任せ
        ("libopenh264", ["-b:v"]),  # CRF相当が無いのでビットレート指定
    ],
)
def test_選ばれたエンコーダをそのまま使う(encoder, must_contain):
    """libx264決め打ちだと、同梱ビルドに無いものを指定して書き出しが落ちる"""
    cmd = build_export_cmd(Path("in.mov"), Path("out.mp4"), 0, 10, encoder=encoder)

    assert cmd[cmd.index("-c:v") + 1] == encoder
    assert "libx264" not in cmd
    for arg in must_contain:
        assert arg in cmd, f"{encoder} に {arg} が無い"


def test_音声は内蔵AACで足りる():
    """外部のAACライブラリを足さずに済む = 同梱ビルドを小さくできる"""
    cmd = build_export_cmd(Path("in.mov"), Path("out.mp4"), 0, 10, encoder="h264_nvenc")
    assert cmd[cmd.index("-c:a") + 1] == "aac"
