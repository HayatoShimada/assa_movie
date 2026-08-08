"""M35: 話者分離モデルとwhisper.cppを配布物に同梱する。

配布物には torch を入れていない(11.5GBあるため)。torchを使うpyannoteは
インストール版では動かず、ONNXが唯一使えるエンジンになる。にもかかわらず
モデルを同梱していなかったので、入れた直後は設定タブで全エンジンが
「未準備」になり、話者分離がまったく使えなかった。

同梱物の場所は自分で組み立てない。Tauriシェルが KS_RESOURCE_DIR で教えてくれる
(whispercpp.pyと同じ流儀)。自分で取得したものがあればそちらを優先する。
"""

import platform

import pytest

from backend.engines.asr import whispercpp
from backend.engines.diarize import onnx


@pytest.fixture
def bundled(tmp_path, monkeypatch):
    """同梱物のあるインストール環境を作る"""
    monkeypatch.setenv("KS_RESOURCE_DIR", str(tmp_path))
    return tmp_path


def _put(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x")
    return path


# ---- 話者分離モデル ----
def test_同梱モデルを見つける(bundled, tmp_path, monkeypatch):
    """入れた直後から話者分離が使えること"""
    # 利用者は何も取得していない
    monkeypatch.setattr(onnx, "DEFAULT_SEGMENTATION", tmp_path / "none/seg.onnx")
    monkeypatch.setattr(onnx, "DEFAULT_EMBEDDING", tmp_path / "none/emb.onnx")
    _put(bundled / onnx.SEGMENTATION_REL)
    _put(bundled / onnx.EMBEDDING_REL)

    assert onnx.is_available() is True
    assert onnx.resolve_segmentation() == bundled / onnx.SEGMENTATION_REL


def test_自分で取得したものを優先する(bundled, tmp_path, monkeypatch):
    """入れ替えたい人の意図を尊重する(whisper-cliと同じ考え方)"""
    downloaded_seg = _put(tmp_path / "mine/seg.onnx")
    downloaded_emb = _put(tmp_path / "mine/emb.onnx")
    monkeypatch.setattr(onnx, "DEFAULT_SEGMENTATION", downloaded_seg)
    monkeypatch.setattr(onnx, "DEFAULT_EMBEDDING", downloaded_emb)
    _put(bundled / onnx.SEGMENTATION_REL)

    assert onnx.resolve_segmentation() == downloaded_seg


def test_どちらも無ければ使えない(bundled, tmp_path, monkeypatch):
    monkeypatch.setattr(onnx, "DEFAULT_SEGMENTATION", tmp_path / "none/seg.onnx")
    monkeypatch.setattr(onnx, "DEFAULT_EMBEDDING", tmp_path / "none/emb.onnx")
    assert onnx.is_available() is False


def test_セットアップ画面は同梱を数に入れる(bundled, tmp_path, monkeypatch):
    """同梱してあるのに「未取得」と出したらダウンロードを促してしまう"""
    from backend.jobs import setup_job

    monkeypatch.setattr(onnx, "DEFAULT_SEGMENTATION", tmp_path / "none/seg.onnx")
    monkeypatch.setattr(onnx, "DEFAULT_EMBEDDING", tmp_path / "none/emb.onnx")
    _put(bundled / onnx.SEGMENTATION_REL)
    _put(bundled / onnx.EMBEDDING_REL)

    assert setup_job.status()["diarization"]["ready"] is True


# ---- pyannoteは配布版では選べない ----
def test_torchが無ければpyannoteは選べない(monkeypatch):
    """トークンだけ見て「使える」と出すと、選んだ瞬間にImportErrorで落ちる。

    配布物にtorchは入っていない(11.5GBあるため)ので、インストール版では
    常にこの状態になる。
    """
    from backend.engines.diarize import pyannote, registry

    monkeypatch.setattr(pyannote, "is_available", lambda: False)
    monkeypatch.setattr(onnx, "is_available", lambda *a, **k: False)

    assert registry.resolve_engine("pyannote", has_token=True) is None
    assert registry.resolve_engine("auto", has_token=True) is None


def test_torchがあればpyannoteを選べる(monkeypatch):
    """ソースから動かす開発環境では従来どおり使える"""
    from backend.engines.diarize import pyannote, registry

    monkeypatch.setattr(pyannote, "is_available", lambda: True)
    monkeypatch.setattr(onnx, "is_available", lambda *a, **k: False)

    assert registry.resolve_engine("pyannote", has_token=True) == "pyannote"
    assert registry.resolve_engine("auto", has_token=True) == "pyannote"


def test_ONNXがあればトークン無しでも動く(monkeypatch):
    """同梱モデルがある配布版の状態"""
    from backend.engines.diarize import registry

    monkeypatch.setattr(onnx, "is_available", lambda *a, **k: True)
    assert registry.resolve_engine("auto", has_token=False) == "onnx"


# ---- whisper.cpp ----
def test_Windowsのwhisper_cliは拡張子付きで探す():
    """.exe を付けずに探すと、同梱してあっても見つからず遅いエンジンに落ちる"""
    expected = "whisper-cli.exe" if platform.system() == "Windows" else "whisper-cli"
    assert whispercpp.BINARY_NAME == expected


def test_同梱whisper_cliを見つける(bundled):
    _put(bundled / "bin" / whispercpp.BINARY_NAME)
    got = whispercpp.resolve_binary()
    assert got is not None
    assert got.name == whispercpp.BINARY_NAME
