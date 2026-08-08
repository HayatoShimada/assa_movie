"""M24: データ・キャッシュ・設定の置き場所の解決(純関数)"""

from pathlib import Path

import pytest

from backend.core import paths


@pytest.fixture
def home(tmp_path, monkeypatch):
    """XDGの環境変数を外し、HOMEだけがある素の状態にする"""
    for var in ("XDG_DATA_HOME", "XDG_CACHE_HOME", "XDG_CONFIG_HOME"):
        monkeypatch.delenv(var, raising=False)
    return tmp_path


def test_new_install_uses_xdg_locations(home, tmp_path):
    """既存データが無い環境ではOS標準の場所に置く(インストール版の想定)"""
    repo = tmp_path / "repo"
    repo.mkdir()
    assert paths.data_dir(home=home, repo=repo) == home / ".local/share/kirinuki-studio"
    assert paths.cache_dir(home=home) == home / ".cache/kirinuki-studio"
    assert paths.config_dir(home=home) == home / ".config/kirinuki-studio"


def test_xdg_env_vars_win(home, tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "d"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "c"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "g"))
    repo = tmp_path / "repo"
    repo.mkdir()
    assert paths.data_dir(home=home, repo=repo) == tmp_path / "d/kirinuki-studio"
    assert paths.cache_dir(home=home) == tmp_path / "c/kirinuki-studio"
    assert paths.config_dir(home=home) == tmp_path / "g/kirinuki-studio"


def test_existing_repo_data_keeps_being_used(home, tmp_path):
    """ソースから動かしていた頃のDBがあれば、そのまま使い続ける。

    media.path に絶対パスが入っているため、uploads を移すと既存の動画への
    参照が全部切れる。移すより「そこを使い続ける」方が安全。
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "whisper.db").write_bytes(b"")
    assert paths.data_dir(home=home, repo=repo) == repo


def test_db_path_matches_the_directory_it_lives_in(home, tmp_path):
    """既存データを使うときはファイル名も旧名のまま(改名すると空DBが生える)"""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "whisper.db").write_bytes(b"")
    assert paths.db_path(home=home, repo=repo) == repo / "whisper.db"

    fresh = tmp_path / "fresh"
    fresh.mkdir()
    assert paths.db_path(home=home, repo=fresh).name == "kirinuki-studio.db"


def test_cache_dir_keeps_using_the_old_model_cache(home):
    """旧名のモデルキャッシュ(数GB)があれば使い続ける。

    見失うとwhisper.cppとONNX話者分離が黙って遅い実装に降格するだけで、
    ユーザーには原因が分からない。
    """
    legacy = home / ".cache/whisper-local"
    legacy.mkdir(parents=True)
    assert paths.cache_dir(home=home) == legacy


def test_cache_dir_prefers_new_name_when_both_exist(home):
    (home / ".cache/whisper-local").mkdir(parents=True)
    (home / ".cache/kirinuki-studio").mkdir(parents=True)
    assert paths.cache_dir(home=home) == home / ".cache/kirinuki-studio"


def test_config_file_prefers_the_existing_one_in_the_repo(home, tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    assert paths.config_file("hf_token.txt", home=home, repo=repo) == (
        home / ".config/kirinuki-studio/hf_token.txt"
    )
    (repo / "hf_token.txt").write_text("hf_x")
    assert paths.config_file("hf_token.txt", home=home, repo=repo) == repo / "hf_token.txt"


def test_legacy_env_vars_are_reported(monkeypatch):
    """旧接頭辞は黙って無視されると設定ミスが表面化しないので、検出して伝える"""
    monkeypatch.setenv("WL_ASR_MODEL", "large-v3-turbo")
    monkeypatch.setenv("KS_ASR_LANGUAGE", "ja")
    assert paths.legacy_env_vars() == ["WL_ASR_MODEL"]


def test_no_legacy_env_vars(monkeypatch):
    for var in list(paths.os.environ):
        if var.startswith("WL_"):
            monkeypatch.delenv(var)
    assert paths.legacy_env_vars() == []
