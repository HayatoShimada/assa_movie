"""M10: アクセラレータ検出(cuda / rocm / cpu)のテスト"""

from types import SimpleNamespace

import pytest

from backend.core.device import detect_accel


def _fake_torch(cuda_available: bool, hip: str | None, cuda: str | None):
    return SimpleNamespace(
        cuda=SimpleNamespace(is_available=lambda: cuda_available),
        version=SimpleNamespace(hip=hip, cuda=cuda),
    )


@pytest.mark.parametrize(
    "torch_module, expected",
    [
        # NVIDIA CUDA環境
        (_fake_torch(True, None, "12.8"), "cuda"),
        # ROCm環境(HIPビルドはcudaを名乗るのでhip属性で見分ける)
        (_fake_torch(True, "6.4.43482", None), "rocm"),
        # GPUなし(CUDAビルドだがGPU不在=今回のcu128残留ケースも含む)
        (_fake_torch(False, None, "12.8"), "cpu"),
        (_fake_torch(False, None, None), "cpu"),
        # ROCmビルドだがGPUが見えない場合もCPU扱い
        (_fake_torch(False, "6.4.43482", None), "cpu"),
    ],
)
def test_detect_accel_table(torch_module, expected):
    assert detect_accel(torch_module) == expected


def test_detect_accel_without_torch():
    # torch自体が壊れている/未導入でもcpuに落ちる
    class Broken:
        def __getattr__(self, name):
            raise RuntimeError("torch壊れてる")

    assert detect_accel(Broken()) == "cpu"


def test_detect_accel_real_torch_returns_valid_value():
    # 実環境のtorchで呼んでも3値のどれかを返す(GPU有無に依存しない検証)
    assert detect_accel() in ("cuda", "rocm", "cpu")
