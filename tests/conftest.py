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
