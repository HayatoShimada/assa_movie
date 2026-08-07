"""M5: メディアファイル配信エンドポイントのテスト"""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    from backend.core import config

    monkeypatch.setattr(config.settings, "db_path", tmp_path / "m5.db")
    from backend.app import app

    with TestClient(app) as c:
        yield c


def test_media_file_served(client, tmp_path):
    pid = client.post("/api/projects", json={"name": "p"}).json()["id"]
    f = tmp_path / "a.wav"
    f.write_bytes(b"RIFF-DUMMY")
    mid = client.post(f"/api/projects/{pid}/media", json={"path": str(f)}).json()["id"]

    r = client.get(f"/api/media/{mid}/file")
    assert r.status_code == 200
    assert r.content == b"RIFF-DUMMY"

    meta = client.get(f"/api/media/{mid}").json()
    assert meta["id"] == mid and meta["path"] == str(f)


def test_media_file_404_when_deleted(client, tmp_path):
    pid = client.post("/api/projects", json={"name": "p"}).json()["id"]
    f = tmp_path / "b.wav"
    f.write_bytes(b"x")
    mid = client.post(f"/api/projects/{pid}/media", json={"path": str(f)}).json()["id"]
    f.unlink()  # 登録後にファイルが消えたケース
    assert client.get(f"/api/media/{mid}/file").status_code == 404


def test_media_file_404_unknown_media(client):
    assert client.get("/api/media/999/file").status_code == 404
