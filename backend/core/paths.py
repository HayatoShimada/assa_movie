"""データ・キャッシュ・設定の置き場所。

インストールして使うアプリになったので、生成物をソースツリーに置かず
OS標準の場所(Linux は XDG Base Directory)に置く。

ただし**既存の環境は動かさない**。開発機やソースから動かしていたユーザーは
リポジトリ直下に `whisper.db` と `uploads/` を持っており、`media.path` には
その絶対パスが入っている。移すと既存の動画への参照が全部切れるので、
既にそこにデータがあるならそこを使い続ける(そちらの方が移行より安全)。

モデルキャッシュも同じ考え方。旧名(`~/.cache/whisper-local`)に数GBある環境で
新名を見にいくと、whisper.cppとONNX話者分離が「無い」と判定されて黙って
遅い実装に降格してしまう。
"""

import os
from pathlib import Path

APP_NAME = "kirinuki-studio"
DB_NAME = f"{APP_NAME}.db"
# 旧名。これらが残っている環境は移行せずそのまま使う
LEGACY_DB_NAME = "whisper.db"
LEGACY_CACHE_NAME = "whisper-local"
# 旧バージョンの環境変数接頭辞(現在は KS_)
LEGACY_ENV_PREFIX = "WL_"

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _xdg(env: str, home: Path, fallback: str) -> Path:
    base = os.environ.get(env, "").strip()
    return (Path(base) if base else home / fallback) / APP_NAME


def data_dir(home: Path | None = None, repo: Path | None = None) -> Path:
    """DB・アップロード動画・書き出しの置き場所"""
    repo = repo or PROJECT_ROOT
    if (repo / LEGACY_DB_NAME).exists():
        return repo
    return _xdg("XDG_DATA_HOME", home or Path.home(), ".local/share")


def db_path(home: Path | None = None, repo: Path | None = None) -> Path:
    directory = data_dir(home=home, repo=repo)
    legacy = directory / LEGACY_DB_NAME
    # 既存DBを使う環境ではファイル名も変えない(変えると空DBが新規作成される)
    return legacy if legacy.exists() else directory / DB_NAME


def cache_dir(home: Path | None = None) -> Path:
    """モデル・ビルド済みバイナリの置き場所(消えても再取得できるもの)"""
    home = home or Path.home()
    base = os.environ.get("XDG_CACHE_HOME", "").strip()
    root = Path(base) if base else home / ".cache"
    new = root / APP_NAME
    legacy = root / LEGACY_CACHE_NAME
    if not new.exists() and legacy.exists():
        return legacy
    return new


def config_dir(home: Path | None = None) -> Path:
    """APIトークン等の置き場所"""
    return _xdg("XDG_CONFIG_HOME", home or Path.home(), ".config")


def config_file(name: str, home: Path | None = None, repo: Path | None = None) -> Path:
    """APIトークン等のファイル。リポジトリ直下に既にあるならそれを使う"""
    legacy = (repo or PROJECT_ROOT) / name
    return legacy if legacy.exists() else config_dir(home=home) / name


def legacy_env_vars() -> list[str]:
    """設定されている旧接頭辞の環境変数。

    pydantic-settings は接頭辞の合わない変数を黙って無視するため、
    放置すると「設定したのに効かない」が一切表面化しない。起動時に警告する。
    """
    return sorted(v for v in os.environ if v.startswith(LEGACY_ENV_PREFIX))
