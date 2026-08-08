"""M11: エンコーダ自動検出(nvenc / vaapi / libx264)のテスト。ffmpeg実行は不要。"""

from pathlib import Path

import pytest

from backend.pipeline.export import _pick_encoder, build_export_cmd


# ---- _pick_encoder: 純関数のテーブル駆動 ----

@pytest.mark.parametrize(
    "name, encoders_output, has_nvidia, has_dri, expected",
    [
        # NVIDIA機: nvenc優先
        ("NVIDIA機", "h264_nvenc\nh264_vaapi\nlibx264", True, False, "h264_nvenc"),
        # AMD機: ffmpegはnvencを「対応コーデック」として列挙するが
        # NVIDIAデバイスが無ければ使えないのでvaapiへ
        ("AMD機(nvenc列挙あり)", "h264_nvenc\nh264_vaapi\nlibx264", False, True, "h264_vaapi"),
        ("vaapiあるがDRIデバイス無し", "h264_vaapi\nlibx264", False, False, "libx264"),
        ("HWエンコーダ無し", "libx264", False, True, "libx264"),
        ("何も無い(最低限libx264で試みる)", "", False, False, "libx264"),
    ],
)
def test_pick_encoder_table(name, encoders_output, has_nvidia, has_dri, expected):
    # vaapi/libx264 はLinuxの話。os_nameを渡さないと実行機のOSで結果が変わり、
    # Windowsランナーで回したときだけ落ちる(他OSの表は test_m31_cross_platform.py)
    assert _pick_encoder(encoders_output, has_nvidia, has_dri, os_name="Linux") == expected, name


# ---- build_export_cmd のエンコーダ別出力 ----

def test_build_cmd_libx264():
    cmd = build_export_cmd(Path("in.mov"), Path("out.mp4"), 0, 10, encoder="libx264")
    assert "libx264" in cmd
    assert "-vaapi_device" not in cmd


def test_build_cmd_nvenc():
    cmd = build_export_cmd(Path("in.mov"), Path("out.mp4"), 0, 10, encoder="h264_nvenc")
    assert "h264_nvenc" in cmd


def test_build_cmd_vaapi_plain():
    # フィルタ無しでもnv12変換+hwuploadが必要
    cmd = build_export_cmd(Path("in.mov"), Path("out.mp4"), 0, 10, encoder="h264_vaapi")
    assert cmd.index("-vaapi_device") < cmd.index("-i")  # デバイス指定は入力より前
    assert "h264_vaapi" in cmd
    vf = cmd[cmd.index("-vf") + 1]
    assert vf == "format=nv12,hwupload"


def test_build_cmd_vaapi_with_subtitles(tmp_path):
    cmd = build_export_cmd(
        Path("in.mov"), Path("out.mp4"), 0, 10,
        ass_path=tmp_path / "sub.ass", encoder="h264_vaapi",
    )
    vf = cmd[cmd.index("-vf") + 1]
    # hwuploadはフィルタ列の最後(字幕焼き込みの後)
    assert vf.startswith("ass=") and vf.endswith("format=nv12,hwupload")


def test_build_cmd_vaapi_with_cuts():
    cmd = build_export_cmd(
        Path("in.mov"), Path("out.mp4"), 0, 10,
        cuts=[(2.0, 3.0)], encoder="h264_vaapi",
    )
    graph = cmd[cmd.index("-filter_complex") + 1]
    # concat後にhwuploadし、その出力をmapする
    assert "concat" in graph
    assert graph.rstrip().endswith("format=nv12,hwupload[vhw]")
    assert cmd[cmd.index("-map") + 1] == "[vhw]"


def test_build_cmd_without_ffmpeg_raises(monkeypatch):
    from backend.pipeline import export as export_mod

    monkeypatch.setattr(export_mod, "detect_encoder", lambda: None)
    with pytest.raises(RuntimeError, match="ffmpeg"):
        build_export_cmd(Path("in.mov"), Path("out.mp4"), 0, 10)


def test_build_cmd_layout_filter_before_subtitles(tmp_path):
    # M14の向き変換: layout → 字幕 → (cuts) の順で連結される
    cmd = build_export_cmd(
        Path("in.mov"), Path("out.mp4"), 0, 10,
        ass_path=tmp_path / "s.ass", encoder="libx264",
        layout_filter="[0:v]crop=608:1080:656:0,scale=1080:1920[vlay]",
    )
    graph = cmd[cmd.index("-filter_complex") + 1]
    assert graph.index("crop=") < graph.index("ass=")
    assert "[vlay]" in graph
