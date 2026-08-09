import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--run-gpu", action="store_true", default=False,
        help="GPUを使う実行時間の長いテストも実行する",
    )


def pytest_configure(config):
    config.addinivalue_line("markers", "gpu: GPUを使うテスト(既定でスキップ)")
    config.addinivalue_line(
        "markers",
        "torch: 公式Whisper(torch依存)が要るテスト。"
        "配布物にtorchは入れないので、入っていない環境では自動でスキップする",
    )


# マーカー名 → 実際に import できるかを見るモジュール名
_TORCH_MODULES = ("torch", "whisper")


def pytest_collection_modifyitems(config, items):
    """torchマーカーの付いたテストは、依存が入っていなければスキップする。

    torch系は開発グループにしか無く(配布物に入れると11.5GB)、Windows機や
    CIの多くには入っていない。`-m "not torch"` を毎回指定させると忘れるので、
    実際に import できるかで判断する。
    """
    from importlib.util import find_spec

    missing = []
    for name in _TORCH_MODULES:
        try:
            if find_spec(name) is None:
                missing.append(name)
        except (ImportError, ValueError):
            missing.append(name)
    if not missing:
        return
    skip = pytest.mark.skip(reason=f"torch系が入っていない({', '.join(missing)})")
    for item in items:
        if "torch" in item.keywords:
            item.add_marker(skip)


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
    from backend.core.device import probe_gpu
    from backend.jobs import resolve_job
    from backend.pipeline.export import detect_encoder

    # LLMクライアントの差し替え。5ファイルが設定して誰も戻していなかった
    saved_factory = resolve_job._client_factory
    # 実機を1回だけ叩くキャッシュ。テスト間で共有すると注入が効かなくなる
    probe_gpu.cache_clear()
    detect_encoder.cache_clear()
    yield
    resolve_job.set_client_factory(saved_factory)
    probe_gpu.cache_clear()
    detect_encoder.cache_clear()


@pytest.fixture
def client(tmp_path):
    """一時DBのTestClient。DBパスはテストごとに独立する"""
    from backend.core.config import settings

    settings.db_path = tmp_path / "test.db"
    from backend.app import app
    from fastapi.testclient import TestClient

    with TestClient(app) as c:
        yield c
