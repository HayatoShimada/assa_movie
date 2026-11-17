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
import platform
import re
from pathlib import Path

APP_NAME = "kirinuki-studio"
# 利用者の目に触れるフォルダ名(書き出し先)。画面に出るアプリ名と揃える
EXPORT_FOLDER_NAME = "KirinukiStudio"
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


def _win_dir(env: str, home: Path, fallback: str) -> Path:
    """Windowsの標準的な置き場所。環境変数が無ければホーム配下に落とす"""
    base = os.environ.get(env, "").strip()
    return (Path(base) if base else home / fallback) / APP_NAME


def data_dir(
    home: Path | None = None, repo: Path | None = None, os_name: str | None = None
) -> Path:
    """DB・アップロード動画・書き出しの置き場所"""
    repo = repo or PROJECT_ROOT
    if (repo / LEGACY_DB_NAME).exists():
        return repo
    home = home or Path.home()
    os_name = os_name or platform.system()
    if os_name == "Darwin":
        return home / "Library/Application Support" / APP_NAME
    if os_name == "Windows":
        return _win_dir("APPDATA", home, "AppData/Roaming")
    return _xdg("XDG_DATA_HOME", home, ".local/share")


def db_path(
    home: Path | None = None, repo: Path | None = None, os_name: str | None = None
) -> Path:
    directory = data_dir(home=home, repo=repo, os_name=os_name)
    legacy = directory / LEGACY_DB_NAME
    # 既存DBを使う環境ではファイル名も変えない(変えると空DBが新規作成される)
    return legacy if legacy.exists() else directory / DB_NAME


def cache_dir(home: Path | None = None, os_name: str | None = None) -> Path:
    """モデル・ビルド済みバイナリの置き場所(消えても再取得できるもの)"""
    home = home or Path.home()
    os_name = os_name or platform.system()
    if os_name == "Darwin":
        return home / "Library/Caches" / APP_NAME
    if os_name == "Windows":
        # 数GBのモデルを置くので、同期対象になりうるRoamingではなくLocalへ
        return _win_dir("LOCALAPPDATA", home, "AppData/Local") / "cache"

    base = os.environ.get("XDG_CACHE_HOME", "").strip()
    root = Path(base) if base else home / ".cache"
    new = root / APP_NAME
    legacy = root / LEGACY_CACHE_NAME
    if not new.exists() and legacy.exists():
        return legacy
    return new


def config_dir(home: Path | None = None, os_name: str | None = None) -> Path:
    """APIトークン等の置き場所"""
    home = home or Path.home()
    os_name = os_name or platform.system()
    if os_name == "Darwin":
        # Macは設定も Application Support にまとめるのが標準
        return home / "Library/Application Support" / APP_NAME
    if os_name == "Windows":
        return _win_dir("APPDATA", home, "AppData/Roaming")
    return _xdg("XDG_CONFIG_HOME", home, ".config")


def config_file(
    name: str,
    home: Path | None = None,
    repo: Path | None = None,
    os_name: str | None = None,
) -> Path:
    """APIトークン等のファイル。リポジトリ直下に既にあるならそれを使う"""
    legacy = (repo or PROJECT_ROOT) / name
    return legacy if legacy.exists() else config_dir(home=home, os_name=os_name) / name


def parse_user_dirs(text: str, home: Path) -> Path | None:
    """`~/.config/user-dirs.dirs` から動画フォルダを読む(純関数)。

    日本語環境のLinuxは `~/ビデオ` で、`~/Videos` は存在しない。
    書式は `XDG_VIDEOS_DIR="$HOME/ビデオ"`(xdg-user-dirs)。
    `$HOME/` を指すだけの行は「動画フォルダを使わない」設定なので無視する。
    """
    for line in text.splitlines():
        m = re.match(r'\s*XDG_VIDEOS_DIR\s*=\s*"(.*)"\s*$', line)
        if not m:
            continue
        value = m.group(1).rstrip("/")
        if value.startswith("$HOME"):
            rest = value[len("$HOME"):].lstrip("/")
            return home / rest if rest else None
        return Path(value) if value.startswith("/") else None
    return None


def videos_dir(
    home: Path | None = None,
    os_name: str | None = None,
    environ: dict[str, str] | None = None,
) -> Path:
    """利用者の動画フォルダ(Finder・エクスプローラーのサイドバーに出る場所)"""
    home = home or Path.home()
    os_name = os_name or platform.system()
    environ = os.environ if environ is None else environ
    if os_name == "Darwin":
        return home / "Movies"
    if os_name == "Windows":
        profile = environ.get("USERPROFILE", "").strip()
        return (Path(profile) if profile else home) / "Videos"
    config = environ.get("XDG_CONFIG_HOME", "").strip()
    user_dirs = (Path(config) if config else home / ".config") / "user-dirs.dirs"
    try:
        found = parse_user_dirs(user_dirs.read_text(encoding="utf-8"), home)
    except (OSError, UnicodeDecodeError):
        found = None
    return found or home / "Videos"


def default_export_dir(
    home: Path | None = None,
    os_name: str | None = None,
    environ: dict[str, str] | None = None,
) -> Path:
    """書き出し先の既定。動画フォルダの中の KirinukiStudio/。

    以前は元動画の隣の exports/ だった。ファイル選択で取り込んだ動画は
    アプリのデータフォルダ(macOSなら ~/Library/Application Support/…)に
    コピーされるので、書き出しもFinderから見えない場所に入り、
    「書き出したのにどこにも無い」になっていた(issue #3)。
    """
    return videos_dir(home=home, os_name=os_name, environ=environ) / EXPORT_FOLDER_NAME


def legacy_env_vars() -> list[str]:
    """設定されている旧接頭辞の環境変数。

    pydantic-settings は接頭辞の合わない変数を黙って無視するため、
    放置すると「設定したのに効かない」が一切表面化しない。起動時に警告する。
    """
    return sorted(v for v in os.environ if v.startswith(LEGACY_ENV_PREFIX))
