"""新しい版の確認と、ダウンロードページを開くAPI。"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.core import reveal as reveal_mod
from backend.core import update_check
from backend.core.project_settings import resolve_settings

router = APIRouter(prefix="/api", tags=["update"])


class UpdateStatus(BaseModel):
    current: str
    latest: str | None = None
    has_update: bool = False
    notes: str = ""
    checked: bool = False
    error: str = ""
    url: str


@router.get("/update", response_model=UpdateStatus)
def get_update(force: bool = False) -> UpdateStatus:
    """新しい版があるか。自動確認を切っているときは force=true(「今すぐ確認」)のときだけ通信する"""
    enabled = resolve_settings().update_check_enabled
    return UpdateStatus(**update_check.check(enabled=enabled, force=force).to_dict())


@router.post("/update/open")
def open_download_page() -> dict:
    """ダウンロードページを既定のブラウザで開く。

    webviewの中のリンクは外のブラウザで開かないので、バックエンドが開く。
    開くのは決まったページだけ(URLは受け取らない)。
    """
    try:
        reveal_mod.open_url(update_check.RELEASES_URL)
    except OSError as e:
        raise HTTPException(
            500, f"ブラウザを開けませんでした({e})。このページを開いてください: {update_check.RELEASES_URL}"
        )
    return {"url": update_check.RELEASES_URL}
