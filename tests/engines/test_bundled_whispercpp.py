"""M30: 同梱したwhisper.cppを見つけられること。

配布版はVulkanビルドを同梱する(ROCm不要・どのGPUでも動く)。
開発機で `./dev.sh whispercpp` を叩いた人はHIPビルドの方が13%速いので、
そちらを優先する(docs/verify_rocm.md の実測表)。
"""

import os
import platform

import pytest

from backend.core import bundled
from backend.engines.asr import whispercpp


@pytest.fixture
def dirs(tmp_path, monkeypatch):
    """同梱先とキャッシュを別々の一時ディレクトリにする"""
    bundled, cache = tmp_path / "app", tmp_path / "cache"
    monkeypatch.setattr(whispercpp, "bundled_dir", lambda: bundled)
    monkeypatch.setattr(whispercpp, "DEFAULT_HOME", cache)
    return bundled, cache


def place_binary(directory):
    path = directory / "bin" / whispercpp.BINARY_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\n", encoding="utf-8")
    path.chmod(0o755)
    return path


# ---- どのバイナリを選ぶか ----
def test_同梱バイナリを見つける(dirs):
    bundled, _ = dirs
    expected = place_binary(bundled)
    assert whispercpp.resolve_binary() == expected


def test_自分でビルドしたものを優先する(dirs):
    """HIPビルドの方が13%速い。明示的に用意した人の意図を尊重する"""
    bundled, cache = dirs
    place_binary(bundled)
    built = place_binary(cache)
    assert whispercpp.resolve_binary() == built


def test_どちらも無ければNone(dirs):
    assert whispercpp.resolve_binary() is None


@pytest.mark.skipif(
    platform.system() == "Windows",
    reason="Windowsに実行権限ビットが無く、chmodしてもX_OKは真のまま",
)
def test_実行権限が無いものは選ばない(dirs):
    """展開に失敗して権限が落ちたファイルを掴まない。

    .deb/.AppImage/.dmg で実際に起きうる。落ちていても例外にはならず、
    黙ってfaster-whisper(CPU)へ降格するだけなので気付けない
    """
    bundled, _ = dirs
    path = place_binary(bundled)
    path.chmod(0o644)
    assert whispercpp.resolve_binary() is None


def test_環境変数で上書きできる(dirs, tmp_path, monkeypatch):
    bundled, _ = dirs
    place_binary(bundled)
    override = place_binary(tmp_path / "elsewhere")
    monkeypatch.setattr(whispercpp, "DEFAULT_HOME", tmp_path / "elsewhere")
    assert whispercpp.resolve_binary() == override


# ---- 利用可否の判定 ----
def test_バイナリだけではまだ使えない(dirs):
    """モデル(3.1GB)は別途ダウンロードが要る"""
    bundled, _ = dirs
    place_binary(bundled)
    assert whispercpp.is_available() is False


def test_バイナリとモデルが揃えば使える(dirs):
    bundled, cache = dirs
    place_binary(bundled)
    model = cache / "models" / "ggml-large-v3.bin"
    model.parent.mkdir(parents=True, exist_ok=True)
    model.write_bytes(b"x")
    assert whispercpp.is_available() is True


def test_モデルだけでは使えない(dirs):
    _, cache = dirs
    model = cache / "models" / "ggml-large-v3.bin"
    model.parent.mkdir(parents=True, exist_ok=True)
    model.write_bytes(b"x")
    assert whispercpp.is_available() is False


# ---- 同梱先の決め方(backend/core/bundled.py) ----
def test_同梱先はTauriが教えてくれた場所(monkeypatch, tmp_path):
    """同梱物の場所はパッケージ形式で変わるので、シェルに教えてもらう"""
    monkeypatch.setenv("KS_RESOURCE_DIR", str(tmp_path / "usr/lib/KirinukiStudio"))
    assert bundled.bundled_dir() == tmp_path / "usr/lib/KirinukiStudio"


def test_教えられていなければ実行ファイルの隣を見る(monkeypatch, tmp_path):
    """開発中(uvicorn直起動)はTauriが居ないのでこちら"""
    monkeypatch.delenv("KS_RESOURCE_DIR", raising=False)
    exe = tmp_path / "usr" / "bin" / "kirinuki-studio-backend"
    exe.parent.mkdir(parents=True)
    exe.write_text("", encoding="utf-8")
    monkeypatch.setattr(bundled.sys, "executable", str(exe))
    assert bundled.bundled_dir() == exe.parent


def test_同梱物を探す3箇所が同じ実装を使う():
    """ffmpeg・whisper.cpp・話者分離モデルで同じコードが3つに分かれていた。

    テストやE2Eで差し替えるとき1つしか差し替えず、残り2つが本物を見ていた
    (e2e_server.py が実際にそうなっていた)
    """
    from backend.core import ffmpeg
    from backend.engines.diarize import onnx

    for module in (ffmpeg, whispercpp, onnx):
        assert module.bundled_dir is bundled.bundled_dir, module.__name__


# ---- エンジンが解決結果を使う ----
def test_エンジンは既定で解決したバイナリを使う(dirs):
    bundled, cache = dirs
    path = place_binary(bundled)
    model = cache / "models" / "ggml-large-v3.bin"
    model.parent.mkdir(parents=True, exist_ok=True)
    model.write_bytes(b"x")

    engine = whispercpp.WhisperCppEngine()
    assert engine.binary == path


def test_バイナリが無ければ理由が分かるエラーになる(dirs):
    engine = whispercpp.WhisperCppEngine()
    with pytest.raises(RuntimeError, match="whisper.cpp"):
        engine.load()


def test_実行権限の判定にos_accessを使っている(dirs):
    """symlinkやnoexecマウントでも実際に実行できるかで判断する"""
    bundled, _ = dirs
    path = place_binary(bundled)
    assert os.access(path, os.X_OK)
    assert whispercpp.resolve_binary() == path
