"""M31: Linux以外のOSでも正しく動くこと。

Mac/Windowsの実機はここに無いので、OS判定を注入して純関数として確かめる。
実際の動作確認はGitHub Actionsの各ランナーで行う(.github/workflows/release.yml)。
"""

import pytest

from backend.core import paths
from backend.pipeline.export import _pick_encoder

# 各OSのffmpegが列挙するエンコーダ(実際の `ffmpeg -encoders` の抜粋)
LINUX = "h264_nvenc h264_vaapi libx264"
MAC = "h264_videotoolbox libx264"
WINDOWS = "h264_nvenc h264_qsv h264_amf libx264"


# ---- エンコーダの選択 ----
def test_macはvideotoolboxを使う():
    """Apple SiliconのハードウェアエンコーダはVideoToolbox経由"""
    assert _pick_encoder(MAC, has_nvidia=False, has_dri=False, os_name="Darwin") == (
        "h264_videotoolbox"
    )


@pytest.mark.parametrize(
    "encoders,expected",
    [
        (WINDOWS, "h264_nvenc"),                    # NVIDIAが最優先
        ("h264_qsv h264_amf libx264", "h264_qsv"),  # Intel内蔵
        ("h264_amf libx264", "h264_amf"),           # AMD
        ("libx264", "libx264"),                     # ソフトウェアに落とす
    ],
)
def test_windowsは使えるものから選ぶ(encoders, expected):
    # WindowsにVAAPIは無いので has_dri は常にFalse
    assert _pick_encoder(encoders, has_nvidia=True, has_dri=False, os_name="Windows") == expected


def test_linuxの選択は今までどおり():
    """既存の挙動を変えない"""
    assert _pick_encoder(LINUX, has_nvidia=True, has_dri=True, os_name="Linux") == "h264_nvenc"
    assert _pick_encoder(LINUX, has_nvidia=False, has_dri=True, os_name="Linux") == "h264_vaapi"
    assert _pick_encoder(LINUX, has_nvidia=False, has_dri=False, os_name="Linux") == "libx264"


def test_列挙されていないものは選ばない():
    """ffmpegのビルドによっては入っていない。無いものを指定すると書き出しが落ちる"""
    assert _pick_encoder("libx264", has_nvidia=True, has_dri=True, os_name="Darwin") == "libx264"
    assert _pick_encoder("libx264", has_nvidia=True, has_dri=True, os_name="Windows") == "libx264"


def test_他OSのエンコーダを取り違えない():
    """MacでVAAPI、LinuxでVideoToolboxを選ばない(存在しないので落ちる)"""
    assert _pick_encoder("h264_vaapi libx264", False, True, os_name="Darwin") == "libx264"
    assert _pick_encoder("h264_videotoolbox libx264", False, True, os_name="Linux") == "libx264"


# ---- データの置き場所 ----
def test_macはApplication_Supportに置く(tmp_path, monkeypatch):
    """MacでXDGは使わない。OS標準の場所に置く"""
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    repo = tmp_path / "repo"
    repo.mkdir()
    got = paths.data_dir(home=tmp_path, repo=repo, os_name="Darwin")
    assert got == tmp_path / "Library/Application Support/kirinuki-studio"


def test_macのキャッシュと設定(tmp_path, monkeypatch):
    for var in ("XDG_CACHE_HOME", "XDG_CONFIG_HOME"):
        monkeypatch.delenv(var, raising=False)
    assert paths.cache_dir(home=tmp_path, os_name="Darwin") == (
        tmp_path / "Library/Caches/kirinuki-studio"
    )
    assert paths.config_dir(home=tmp_path, os_name="Darwin") == (
        tmp_path / "Library/Application Support/kirinuki-studio"
    )


def test_windowsはAPPDATAに置く(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))
    repo = tmp_path / "repo"
    repo.mkdir()
    assert paths.data_dir(home=tmp_path, repo=repo, os_name="Windows") == (
        tmp_path / "Roaming/kirinuki-studio"
    )
    # キャッシュ(消えても再取得できるもの)はLocalへ。Roamingは同期対象になりうる
    assert paths.cache_dir(home=tmp_path, os_name="Windows") == (
        tmp_path / "Local/kirinuki-studio/cache"
    )


def test_windowsでAPPDATAが無ければホーム配下に置く(tmp_path, monkeypatch):
    for var in ("APPDATA", "LOCALAPPDATA"):
        monkeypatch.delenv(var, raising=False)
    repo = tmp_path / "repo"
    repo.mkdir()
    got = paths.data_dir(home=tmp_path, repo=repo, os_name="Windows")
    assert tmp_path in got.parents


def test_linuxの置き場所は今までどおり(tmp_path, monkeypatch):
    for var in ("XDG_DATA_HOME", "XDG_CACHE_HOME", "XDG_CONFIG_HOME"):
        monkeypatch.delenv(var, raising=False)
    repo = tmp_path / "repo"
    repo.mkdir()
    assert paths.data_dir(home=tmp_path, repo=repo, os_name="Linux") == (
        tmp_path / ".local/share/kirinuki-studio"
    )


def test_既存データはOSによらず尊重する(tmp_path):
    """ソースから動かしていた環境は、どのOSでもそのまま使い続ける"""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "whisper.db").write_bytes(b"")
    for os_name in ("Linux", "Darwin", "Windows"):
        assert paths.data_dir(home=tmp_path, repo=repo, os_name=os_name) == repo


# ---- GPUの検出 ----
def test_Apple_Siliconはmetalとして扱う():
    """Apple SiliconはGPUメモリをCPUと共有する(ユニファイドメモリ)"""
    from backend.core import device

    info = device.parse_mac_gpu("Chipset Model: Apple M3 Max\n", total_ram_bytes=38654705664)
    assert info["accel"] == "metal"
    assert "M3 Max" in info["name"]
    # ユニファイドメモリなので、搭載RAMがそのままGPUから使える量になる
    assert info["vram_total_mb"] == 36864


def test_Intel_MacはGPU無し扱い():
    """Metalは使えるがユニファイドメモリではなく、扱いが別。まずは対象外にする"""
    from backend.core import device

    assert device.parse_mac_gpu("Chipset Model: Radeon Pro 5500M\n", total_ram_bytes=0) == {}


def test_読めない出力はGPU無し扱い():
    from backend.core import device

    assert device.parse_mac_gpu("", 0) == {}
    assert device.parse_mac_gpu("壊れた出力", 17179869184) == {}
