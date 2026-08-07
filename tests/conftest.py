import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--run-gpu", action="store_true", default=False,
        help="GPUを使う実行時間の長いテストも実行する",
    )


def pytest_configure(config):
    config.addinivalue_line("markers", "gpu: GPUを使うテスト(既定でスキップ)")


@pytest.fixture
def run_gpu(request) -> bool:
    return request.config.getoption("--run-gpu")


@pytest.fixture(autouse=True)
def _isolate_settings():
    """設定シングルトンをテスト間で持ち越さない。

    PATCH /api/settings は settings に直接setattrするため monkeypatch では戻らない。
    各テストの前後で値を退避・復元し、実行順で結果が変わらないようにする。
    """
    from backend.core.config import settings

    saved = settings.model_dump()
    yield
    for key, value in saved.items():
        setattr(settings, key, value)


@pytest.fixture
def client(tmp_path):
    """一時DBのTestClient。DBパスはテストごとに独立する"""
    from backend.core.config import settings

    settings.db_path = tmp_path / "test.db"
    from backend.app import app
    from fastapi.testclient import TestClient

    with TestClient(app) as c:
        yield c
