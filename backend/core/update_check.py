"""新しい版が出ているかを確かめる(GitHubのリリースを見る)。

アプリに自動更新は無い。新しい版に気付けないまま古い版を使い続け、
既に直っている不具合を踏む人が出た(issue #3 は v2.0.0 で改善済みの内容を
v1.0.1 で報告していた)。起動時に1回だけ最新の版を尋ね、画面で知らせる。

送るのは「最新のリリースは?」という問い合わせだけで、利用者の情報は付けない。
設定(update_check_enabled)で切れる。失敗しても何も壊さない(知らせないだけ)。
判定と整形は純関数にして、通信は差し替えられるようにしてある。
"""

import os
import re
import tomllib
from dataclasses import asdict, dataclass
from typing import Callable

import requests

from backend.core import paths

REPO = "HayatoShimada/assa_movie"
API_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
# 利用者に開かせるページ。APIの応答に入っているURLは使わない
# (外から来た文字列をそのままブラウザに渡さないため)
RELEASES_URL = f"https://github.com/{REPO}/releases/latest"
TIMEOUT_SEC = 5
# 画面に出す変更点の長さの上限(リリースノート全文は長い)
NOTES_LIMIT = 1200


def parse_version(text: str) -> tuple[int, int, int] | None:
    """`v2.1.0` / `2.1.0` → (2, 1, 0)。正式版の形でなければ None(純関数)。

    `v2.1.0-rc1` のような試験版は正式版として扱わない(知らせない)。
    """
    m = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", (text or "").strip())
    return (int(m[1]), int(m[2]), int(m[3])) if m else None


def is_newer(latest: str, current: str) -> bool:
    """latest が current より新しいか(純関数)。どちらかが読めなければ False"""
    a, b = parse_version(latest), parse_version(current)
    return a is not None and b is not None and a > b


def trim_notes(body: str, limit: int = NOTES_LIMIT) -> str:
    """リリースノートを画面に出せる長さに切る(純関数)。行の途中では切らない"""
    body = (body or "").replace("\r\n", "\n").strip()
    if len(body) <= limit:
        return body
    kept: list[str] = []
    size = 0
    for line in body.split("\n"):
        if size + len(line) + 1 > limit:
            break
        kept.append(line)
        size += len(line) + 1
    return "\n".join(kept).rstrip() + "\n…"


@dataclass
class UpdateInfo:
    # いま動いている版
    current: str
    # 確認できた最新の版(未確認・失敗なら None)
    latest: str | None = None
    has_update: bool = False
    # 最新版の変更点(リリースノートの冒頭)
    notes: str = ""
    # 確認したか(設定で切っている・まだ確認していないなら False)
    checked: bool = False
    # 確認に失敗した理由(利用者向け。成功・未確認なら空)
    error: str = ""
    # ダウンロードページ(固定)
    url: str = RELEASES_URL

    def to_dict(self) -> dict:
        return asdict(self)


def evaluate(current: str, payload: dict) -> UpdateInfo:
    """GitHubの「最新のリリース」の応答から、知らせる内容を決める(純関数)"""
    tag = str(payload.get("tag_name") or "")
    if payload.get("draft") or payload.get("prerelease") or parse_version(tag) is None:
        return UpdateInfo(current=current, checked=True)
    newer = is_newer(tag, current)
    return UpdateInfo(
        current=current,
        latest=tag.lstrip("v"),
        has_update=newer,
        notes=trim_notes(str(payload.get("body") or "")) if newer else "",
        checked=True,
    )


def current_version(environ: dict[str, str] | None = None) -> str:
    """いま動いている版。

    配布版はTauriシェルが `KS_APP_VERSION` で教える(インストーラの版そのもの)。
    開発中(./dev.sh)はシェルが無いので pyproject.toml から読む。
    """
    environ = os.environ if environ is None else environ
    version = environ.get("KS_APP_VERSION", "").strip()
    if version:
        return version
    try:
        with (paths.PROJECT_ROOT / "pyproject.toml").open("rb") as f:
            return str(tomllib.load(f)["project"]["version"])
    except (OSError, KeyError, tomllib.TOMLDecodeError):
        return "0.0.0"


def fetch_latest() -> dict:
    """GitHubに最新のリリースを尋ねる。利用者を識別する情報は送らない"""
    # requests は証明書の束(certifi)を自分で持つ。配布版のPythonはOSの証明書を
    # 見つけられないことがあるので、AI・モデル取得と同じ経路を使う
    response = requests.get(
        API_URL,
        headers={"Accept": "application/vnd.github+json", "User-Agent": "KirinukiStudio"},
        timeout=TIMEOUT_SEC,
    )
    response.raise_for_status()
    return response.json()


# プロセスの中で1回確認したら覚えておく(画面を開くたびに問い合わせない)
_cached: UpdateInfo | None = None


def check(
    enabled: bool = True,
    force: bool = False,
    fetch: Callable[[], dict] | None = None,
    current: str | None = None,
) -> UpdateInfo:
    """最新版の確認。enabled=False なら通信しない(forceは「今すぐ確認」ボタン用)"""
    global _cached
    current = current or current_version()
    if not enabled and not force:
        return UpdateInfo(current=current)
    if _cached is not None and not force:
        return _cached
    try:
        info = evaluate(current, (fetch or fetch_latest)())
    except (requests.RequestException, OSError, ValueError) as e:
        # オフラインでも普通に使えるアプリなので、失敗は静かに扱う。
        # 覚えない(次に画面を開いたとき・「今すぐ確認」でもう一度試す)
        return UpdateInfo(
            current=current, checked=True,
            error=f"最新版を確認できませんでした(インターネットに接続できないか、GitHubが応答しません: {e})",
        )
    _cached = info
    return info


def reset_cache() -> None:
    global _cached
    _cached = None
