"""M25: Tauriのwebviewから叩けること(CORS)。

webviewのページは tauri://localhost(Windowsは http://tauri.localhost)で動くため、
Pythonバックエンド(127.0.0.1:ランダムポート)へのリクエストは常にクロスオリジンになる。
待ち受けはループバックのみなので、許可するのはこの用途のオリジンだけでよい。
"""

import pytest


def preflight(client, origin: str):
    return client.options(
        "/api/settings",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "PATCH",
            "Access-Control-Request-Headers": "content-type",
        },
    )


@pytest.mark.parametrize(
    "origin",
    [
        "tauri://localhost",       # Linux / macOS のwebview
        "http://tauri.localhost",  # Windows のwebview
        "http://localhost:5173",   # Vite開発サーバー
        "http://127.0.0.1:5173",
    ],
)
def test_webviewのオリジンを許可する(client, origin):
    res = preflight(client, origin)
    assert res.status_code == 200
    assert res.headers["access-control-allow-origin"] == origin


@pytest.mark.parametrize(
    "origin",
    [
        "http://evil.example.com",
        "https://kirinuki-studio.example.com",
        "http://localhost.evil.com",
    ],
)
def test_それ以外のオリジンは許可しない(client, origin):
    res = preflight(client, origin)
    assert "access-control-allow-origin" not in res.headers


def test_通常のGETにもオリジンが返る(client):
    res = client.get("/api/health", headers={"Origin": "tauri://localhost"})
    assert res.status_code == 200
    assert res.headers["access-control-allow-origin"] == "tauri://localhost"
