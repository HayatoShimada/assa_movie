"""クラウドLLMのAPIキーの登録。

キーはこの端末の設定ディレクトリに保存する。登録時に有効性の疎通確認のため
提供元のAPIへ1回だけ送り、それ以外にはどこにも送らない。
画面には「設定済みかどうか」と末尾4文字しか返さない(全文を出す必要が無い)。
"""

from dataclasses import dataclass
from pathlib import Path

import requests
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.core import paths
from backend.core.config import settings
from backend.engines.llm import claude, gemini

router = APIRouter(prefix="/api", tags=["keys"])

# 末尾この文字数だけ画面に出す(どのキーを入れたか見分けられれば足りる)
HINT_CHARS = 4


@dataclass(frozen=True)
class KeySpec:
    label: str
    filename: str
    env_var: str
    # 空文字なら接頭辞は見ない(Geminiは AIza〜/AQ.〜 など仕様変更で変わるため、
    # 形式ではなく登録時の疎通確認で判定する)
    prefix: str
    # 環境変数にも入っていないか調べる関数(プロバイダごとの読み方に合わせる)
    loader: object


PROVIDERS: dict[str, KeySpec] = {
    "claude": KeySpec(
        label="Claude (Anthropic)",
        filename="claude_api_key.txt",
        env_var="ANTHROPIC_API_KEY",
        prefix=claude.KEY_PREFIX,
        loader=claude.load_api_key,
    ),
    "gemini": KeySpec(
        label="Gemini (Google)",
        filename="gemini_api_key.txt",
        env_var="GEMINI_API_KEY",
        prefix="",
        loader=gemini.load_api_key,
    ),
}

# 登録時の疎通確認。テスト・E2Eではここを差し替えて実ネットワークに出ない
VERIFIERS: dict[str, object] = {
    "claude": claude.verify_api_key,
    "gemini": gemini.verify_api_key,
}


class KeyRegistration(BaseModel):
    key: str


def key_path(provider: str) -> Path:
    """保存先。既にリポジトリ直下にあるファイルはそのまま使う(paths.config_file の規則)"""
    return paths.config_file(PROVIDERS[provider].filename)


def _spec(provider: str) -> KeySpec:
    if provider not in PROVIDERS:
        raise HTTPException(404, f"未対応のプロバイダです: {provider}")
    return PROVIDERS[provider]


def _status(provider: str) -> dict:
    spec = PROVIDERS[provider]
    path = key_path(provider)
    key = spec.loader(path)
    if not key:
        return {"label": spec.label, "configured": False, "source": None, "hint": None}
    # 環境変数はファイルより優先されるので、どちらが効いているかを伝える
    import os

    source = "環境変数" if os.environ.get(spec.env_var, "").strip() else "この端末に保存"
    return {
        "label": spec.label,
        "configured": True,
        "source": source,
        "hint": f"…{key[-HINT_CHARS:]}",
    }


def provider_ready(provider: str) -> bool:
    """そのプロバイダのAPIキーが使える状態か(設定タブの選択可否に使う)"""
    if provider not in PROVIDERS:
        return False
    return bool(PROVIDERS[provider].loader(key_path(provider)))


@router.get("/keys")
def list_keys() -> dict:
    return {provider: _status(provider) for provider in PROVIDERS}


@router.put("/keys/{provider}")
def register_key(provider: str, body: KeyRegistration) -> dict:
    spec = _spec(provider)
    key = body.key.strip()
    # 説明文ごと貼り付けたケース。読み込み側(loader)が単一行しか受けないので先に弾く
    if not key or any(ch.isspace() for ch in key):
        raise HTTPException(400, "APIキーだけを1行で貼り付けてください(空白や改行は含めない)。")
    if spec.prefix and not key.startswith(spec.prefix):
        # 既存の登録は壊さない(打ち間違いで使えなくなるのを防ぐ)
        raise HTTPException(
            400, f"{spec.label} のAPIキーは「{spec.prefix}」で始まります。全文を貼り付けてください。"
        )
    # 形式が合っていても使えないキーはあるので、保存前に実際にAPIへ接続して確かめる
    try:
        error = VERIFIERS[provider](key)
    except requests.RequestException:
        raise HTTPException(
            502, f"{spec.label} に接続できませんでした。ネットワークを確認して、もう一度お試しください。"
        )
    if error:
        raise HTTPException(400, error)
    path = key_path(provider)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(key + "\n", encoding="utf-8")
    path.chmod(0o600)  # 他ユーザーから読めないようにする
    _refresh_settings(provider, path)
    return list_keys()


@router.delete("/keys/{provider}")
def delete_key(provider: str) -> dict:
    _spec(provider)
    key_path(provider).unlink(missing_ok=True)
    return list_keys()


def _refresh_settings(provider: str, path: Path) -> None:
    """設定singletonの参照先を、いま書いたファイルに合わせる。

    paths.config_file は「既にあればそこ」を返すため、初回登録の前後で
    保存先が変わりうる(設定ディレクトリ側に新規作成される)。
    """
    setattr(settings, f"{provider}_key_file", path)
