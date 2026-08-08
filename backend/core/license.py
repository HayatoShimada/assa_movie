"""ライセンスキーのオフライン検証(Ed25519)。

このアプリの価値は「データを外に出さないこと」なので、認証のためだけに
サーバー通信を発生させない。アプリは**公開鍵しか持たない**ため、
キーの偽造には発行側の秘密鍵が必要になる(docs/V1_PLAN.md「ライセンス方式の決定」)。

キーの形は `KS1.<ペイロード>.<署名>`。1行なのでコピペで渡せる。
署名対象はペイロードのbase64url文字列そのもの。JSONを正規化する必要がなくなり、
「送られてきた通りのバイト列」を検証できる。

割り切り:
- 失効(revoke)はできない → 有効期限付きのキーで実質的に対応する
- キーの共有は技術的に防げない → ハード制限はかけない
  (正規ユーザーがマシン更新で締め出される損失の方が大きい)
"""

import base64
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

PRODUCT = "kirinuki-studio"
FORMAT = "KS1"
# 期限切れ後もこの日数は使える。更新の行き違いで作業中のユーザーを締め出さないため
GRACE_DAYS = 30
# 残りこの日数を切ったら画面で知らせる
NOTICE_DAYS = 14

Status = str  # valid | grace | expired | invalid | missing


@dataclass(frozen=True)
class LicenseStatus:
    status: Status
    edition: str = ""
    licensee: str = ""
    issued: date | None = None
    expires: date | None = None
    seats: int = 0

    @property
    def is_usable(self) -> bool:
        """この状態でアプリを使ってよいか"""
        return self.status in ("valid", "grace")

    @property
    def days_left(self) -> int | None:
        """期限までの残り日数。無期限ならNone(検証時点の today からの差)"""
        return self._days_left

    @property
    def expiring_soon(self) -> bool:
        left = self.days_left
        return left is not None and left <= NOTICE_DAYS

    # 計算済みの残り日数(verifyが埋める)。dataclassの外に出さないための入れ物
    _days_left: int | None = None


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64decode(text: str) -> bytes:
    padded = text + "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(padded)


def public_key_to_text(key: Ed25519PublicKey) -> str:
    """公開鍵をアプリに埋め込める1行の文字列にする"""
    from cryptography.hazmat.primitives.serialization import (
        Encoding,
        PublicFormat,
    )

    return _b64encode(key.public_bytes(Encoding.Raw, PublicFormat.Raw))


def public_key_from_text(text: str) -> Ed25519PublicKey:
    return Ed25519PublicKey.from_public_bytes(_b64decode(text))


def sign_payload(payload: dict, private_key: Ed25519PrivateKey) -> str:
    """キーを1本発行する(発行側でのみ使う。アプリ本体は呼ばない)"""
    body = _b64encode(
        json.dumps(payload, separators=(",", ":"), sort_keys=True, ensure_ascii=False).encode()
    )
    signature = _b64encode(private_key.sign(body.encode("ascii")))
    return f"{FORMAT}.{body}.{signature}"


def _parse_date(value) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def verify(key: str | None, public_key_text: str, today: date | None = None) -> LicenseStatus:
    """キーを検証して状態を返す。例外は投げない(呼び出し側で分岐したいのは状態だから)"""
    if key is None or not key.strip():
        return LicenseStatus(status="missing")

    parts = key.strip().split(".")
    if len(parts) != 3 or parts[0] != FORMAT:
        return LicenseStatus(status="invalid")
    _, body, signature = parts

    try:
        public_key_from_text(public_key_text).verify(_b64decode(signature), body.encode("ascii"))
        payload = json.loads(_b64decode(body))
    except (InvalidSignature, ValueError, TypeError, json.JSONDecodeError):
        return LicenseStatus(status="invalid")

    # 他製品のキーを流用されないよう、製品名も署名の内側で確認する
    if not isinstance(payload, dict) or payload.get("p") != PRODUCT:
        return LicenseStatus(status="invalid")

    expires = _parse_date(payload.get("x"))
    today = today or date.today()
    if expires is None:
        status, days_left = "valid", None
    else:
        days_left = (expires - today).days
        if days_left >= 0:
            status = "valid"
        elif -days_left <= GRACE_DAYS:
            status = "grace"
        else:
            status = "expired"

    return LicenseStatus(
        status=status,
        edition=str(payload.get("e", "")),
        licensee=str(payload.get("l", "")),
        issued=_parse_date(payload.get("i")),
        expires=expires,
        seats=int(payload.get("s") or 0),
        _days_left=days_left,
    )


def load_key(path: Path) -> str | None:
    """保存されたキーを読む。コピペの空白・改行は落とす"""
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8").strip()
    return text or None


def save_key(key: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(key.strip() + "\n", encoding="utf-8")
