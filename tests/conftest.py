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


@pytest.fixture(autouse=True)
def _isolate_module_state():
    """モジュールに溜まる状態をテスト間で持ち越さない。

    どれも「単独では通るのに通しで落ちる/通ってしまう」の原因になる。
    テストの収集順はファイル名順(=マイルストーン番号順)なので、
    番号の若いテストが実機を叩いた結果を、後のテストが掴んでいた。
    """
    from backend.core import hwprofile
    from backend.core.device import probe_gpu
    from backend.jobs import resolve_job
    from backend.pipeline.export import detect_encoder

    # LLMクライアントの差し替え。5ファイルが設定して誰も戻していなかった
    saved_factory = resolve_job._client_factory
    # 実機を1回だけ叩くキャッシュ。テスト間で共有すると注入が効かなくなる
    probe_gpu.cache_clear()
    detect_encoder.cache_clear()
    hwprofile.set_current(None)
    yield
    resolve_job.set_client_factory(saved_factory)
    probe_gpu.cache_clear()
    detect_encoder.cache_clear()
    hwprofile.set_current(None)


@pytest.fixture(autouse=True)
def _fixed_hw_profile(monkeypatch):
    """実行環境の検出結果を固定する。

    開発機にGPUがあるかどうかでテストの結果が変わってはいけない。既定は
    CPU機(faster-whisper・追加モデル不要)。GPU機の挙動を見るテストは
    hwprofile.set_current() で明示的に差し替える。
    """
    from backend.core import hwprofile

    monkeypatch.setattr(
        hwprofile, "detect",
        lambda now, runner=None, os_name=None: hwprofile.HwProfile(
            os="linux", gpu="cpu", detected_at=now
        ),
    )


@pytest.fixture
def client(tmp_path):
    """一時DBのTestClient。DBパスはテストごとに独立する"""
    from backend.core.config import settings

    settings.db_path = tmp_path / "test.db"
    from backend.app import app
    from fastapi.testclient import TestClient

    with TestClient(app) as c:
        yield c
