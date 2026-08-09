"""M33: 初回セットアップ(オンボーディング)。

「入れたらすぐ使える」ようにするため、初回起動時にウィザードを出す。
画面の中身はフロント側(frontend/src/components/setup/SetupWizard.tsx)にあり、
バックエンドが持つのは「もう済ませたか」の1つだけ。

済ませたかどうかは設定として保存する。専用のテーブルやファイルを増やすと、
3層設定(グローバル→プロジェクト→クリップ)の外に状態が漏れるため。
ただしプロジェクト単位で上書きできてはいけない(マシンの状態であって
プロジェクトの性質ではない)。
"""

import pytest

from backend.core.config import Settings
from backend.core.project_settings import MUTABLE_FIELDS, PROJECT_OVERRIDABLE


def test_初期値は未完了():
    """入れた直後はウィザードを出したい"""
    assert Settings().setup_completed is False


def test_UIから変更できる():
    """完了したことをアプリから記録できる必要がある"""
    assert "setup_completed" in MUTABLE_FIELDS


def test_プロジェクト単位では上書きできない():
    """マシンの状態であって、プロジェクトの性質ではない"""
    assert "setup_completed" not in PROJECT_OVERRIDABLE


def test_設定APIから読める(client):
    got = client.get("/api/settings").json()
    assert got["values"]["setup_completed"] is False


def test_完了を記録すると残る(client):
    r = client.patch("/api/settings", json={"setup_completed": True})
    assert r.status_code == 200
    assert r.json()["values"]["setup_completed"] is True
    # 読み直しても残っている(DBに保存されるので再起動しても消えない)
    assert client.get("/api/settings").json()["values"]["setup_completed"] is True


def test_やり直せる(client):
    """設定タブからウィザードを再実行できるようにするため、falseにも戻せる"""
    client.patch("/api/settings", json={"setup_completed": True})
    client.patch("/api/settings", json={"setup_completed": False})
    assert client.get("/api/settings").json()["values"]["setup_completed"] is False


@pytest.mark.parametrize(
    "endpoint",
    [
        "/api/settings",     # LLMプロバイダ・話者分離エンジンの選択肢と可否
        "/api/environment",  # GPU・VRAM・ffmpeg・Ollamaの稼働状況
        "/api/setup",        # 話者分離モデルが揃っているか
        "/api/keys",         # Gemini/Claudeのキー登録状況
    ],
)
def test_ウィザードが使うAPIは既にある(client, endpoint):
    """新しいエンドポイントを足さずに済んでいることの確認。

    足すと設定タブと二重実装になり、片方だけ直す事故が起きる。
    """
    assert client.get(endpoint).status_code == 200
