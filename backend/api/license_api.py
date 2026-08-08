"""ライセンスの状態取得と登録。

検証は完全にローカル(backend/core/license.py)。ネットワークは使わない。
"""

from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.core import license as lic
from backend.core import paths
from backend.core.license_key import PUBLIC_KEY

router = APIRouter(prefix="/api", tags=["license"])

KEY_FILENAME = "license.key"


def key_path() -> Path:
    """ライセンスキーの保存先。設定と同じ場所に置く"""
    return paths.config_dir() / KEY_FILENAME


class LicenseRegistration(BaseModel):
    key: str


def to_response(status: lic.LicenseStatus) -> dict:
    """画面に出すぶんだけ返す(キー本体は返さない)"""
    return {
        "status": status.status,
        "is_usable": status.is_usable,
        "edition": status.edition,
        "licensee": status.licensee,
        "issued": status.issued.isoformat() if status.issued else None,
        "expires": status.expires.isoformat() if status.expires else None,
        "seats": status.seats,
        "days_left": status.days_left,
        "expiring_soon": status.expiring_soon,
    }


def current_status() -> lic.LicenseStatus:
    return lic.verify(lic.load_key(key_path()), PUBLIC_KEY)


@router.get("/license")
def get_license() -> dict:
    return to_response(current_status())


@router.post("/license")
def register_license(body: LicenseRegistration) -> dict:
    status = lic.verify(body.key, PUBLIC_KEY)
    if not status.is_usable:
        # 既存の登録は壊さない(打ち間違いで使えなくなるのを防ぐ)
        raise HTTPException(400, _reject_message(status.status))
    lic.save_key(body.key, key_path())
    return to_response(status)


def _reject_message(status: str) -> str:
    return {
        "missing": "ライセンスキーが空です。",
        "expired": "ライセンスキーの有効期限が切れています。更新版のキーをご登録ください。",
    }.get(status, "ライセンスキーが正しくありません。全文をそのまま貼り付けてください。")
