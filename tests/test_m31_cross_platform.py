"""M24/M31: データ・キャッシュ・設定の置き場所と、OSごとのエンコーダ選択。

**OS判定は必ず `os_name=` で注入する。** 実行中のOSに任せると、Linuxで書いた
期待値がWindows/macOSで落ちる(M24が丸ごとそうなっていたので、ここへ統合した)。
Mac/Windowsの実機はここに無いので、純関数として確かめる。
実際の動作確認はGitHub Actionsの各ランナーで行う。
"""

import pytest

from backend.core import paths
from backend.pipeline.export import _pick_encoder


@pytest.fixture
def home(tmp_path, monkeypatch):
    """XDGの環境変数を外し、HOMEだけがある素の状態にする"""
    for var in ("XDG_DATA_HOME", "XDG_CACHE_HOME", "XDG_CONFIG_HOME"):
        monkeypatch.delenv(var, raising=False)
    return tmp_path


@pytest.fixture
def repo(tmp_path):
    """既存データの無いリポジトリ(=インストール版と同じ状態)"""
    path = tmp_path / "repo"
    path.mkdir()
    return path

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


def test_linuxの置き場所は今までどおり(home, repo):
    """既存データが無い環境ではXDGの標準の場所に置く(インストール版の想定)"""
    assert paths.data_dir(home=home, repo=repo, os_name="Linux") == (
        home / ".local/share/kirinuki-studio"
    )
    assert paths.cache_dir(home=home, os_name="Linux") == home / ".cache/kirinuki-studio"
    assert paths.config_dir(home=home, os_name="Linux") == home / ".config/kirinuki-studio"


def test_linuxはXDGの環境変数に従う(home, repo, tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "d"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "c"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "g"))
    assert paths.data_dir(home=home, repo=repo, os_name="Linux") == tmp_path / "d/kirinuki-studio"
    assert paths.cache_dir(home=home, os_name="Linux") == tmp_path / "c/kirinuki-studio"
    assert paths.config_dir(home=home, os_name="Linux") == tmp_path / "g/kirinuki-studio"


def test_旧名のモデルキャッシュがあれば使い続ける(home):
    """旧名のキャッシュ(数GB)を見失うと、whisper.cppとONNX話者分離が

    「無い」と判定されて黙って遅い実装に降格する。原因が利用者に分からない
    """
    legacy = home / ".cache/whisper-local"
    legacy.mkdir(parents=True)
    assert paths.cache_dir(home=home, os_name="Linux") == legacy


def test_新旧どちらもあれば新しい方を使う(home):
    (home / ".cache/whisper-local").mkdir(parents=True)
    (home / ".cache/kirinuki-studio").mkdir(parents=True)
    assert paths.cache_dir(home=home, os_name="Linux") == home / ".cache/kirinuki-studio"


def test_設定ファイルはリポジトリ直下にあればそれを使う(home, repo):
    assert paths.config_file("hf_token.txt", home=home, repo=repo, os_name="Linux") == (
        home / ".config/kirinuki-studio/hf_token.txt"
    )
    (repo / "hf_token.txt").write_text("hf_x")
    assert paths.config_file("hf_token.txt", home=home, repo=repo, os_name="Linux") == (
        repo / "hf_token.txt"
    )


def test_既存DBがあればファイル名も旧名のまま(home, repo, tmp_path):
    """改名すると隣に空のDBが生えて、過去のプロジェクトが全部消えたように見える"""
    (repo / "whisper.db").write_bytes(b"")
    assert paths.db_path(home=home, repo=repo, os_name="Linux") == repo / "whisper.db"

    fresh = tmp_path / "fresh"
    fresh.mkdir()
    assert paths.db_path(home=home, repo=fresh, os_name="Linux").name == "kirinuki-studio.db"


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


# ---- 旧バージョンの環境変数 ----
def test_旧接頭辞の環境変数を検出する(monkeypatch):
    """黙って無視されると設定ミスが表面化しないので、検出して伝える"""
    monkeypatch.setenv("WL_ASR_MODEL", "large-v3-turbo")
    monkeypatch.setenv("KS_ASR_LANGUAGE", "ja")
    assert paths.legacy_env_vars() == ["WL_ASR_MODEL"]


def test_旧接頭辞が無ければ空(monkeypatch):
    for var in list(paths.os.environ):
        if var.startswith("WL_"):
            monkeypatch.delenv(var)
    assert paths.legacy_env_vars() == []
