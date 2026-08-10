"""M10: アクセラレータ検出(cuda / rocm / cpu)のテスト"""

from types import SimpleNamespace

import pytest

from backend.core.device import CUDA_RUNTIME_LIBS, detect_accel, missing_cuda_libs


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


# ---- CUDAランタイムの欠落検出(配布版Ubuntuの libcublas.so.12 クラッシュ対策) ----
def _loader_ok(lib):
    return object()


def _loader_fail(lib):
    raise OSError(f"{lib}: cannot open shared object file")


def test_missing_cuda_libs_全部読めれば空():
    assert missing_cuda_libs(loader=_loader_ok, search_roots=[]) == []


def test_missing_cuda_libs_どこにも無ければ全て列挙():
    assert missing_cuda_libs(loader=_loader_fail, search_roots=[]) == list(CUDA_RUNTIME_LIBS)


def test_missing_cuda_libs_pip配布のnvidiaパッケージも探す(tmp_path):
    """ctranslate2のwheelはpipのnvidia系パッケージをrpathで参照する。
    dlopenの通常経路に無くても、そこにあれば実行時には使える"""
    for lib in CUDA_RUNTIME_LIBS:
        d = tmp_path / lib.split(".")[0].removeprefix("lib") / "lib"
        d.mkdir(parents=True)
        (d / lib).write_bytes(b"")
    assert missing_cuda_libs(loader=_loader_fail, search_roots=[tmp_path]) == []


def test_missing_cuda_libs_片方だけ無い場合はそれだけ返す(tmp_path):
    d = tmp_path / "cublas" / "lib"
    d.mkdir(parents=True)
    (d / "libcublas.so.12").write_bytes(b"")
    assert missing_cuda_libs(loader=_loader_fail, search_roots=[tmp_path]) == ["libcudnn.so.9"]


def test_missing_cuda_libs_linux以外は常に空(monkeypatch):
    """.soの名前も配布形態もLinux前提。他OSで誤ってGPUを諦めない"""
    import backend.core.device as device

    monkeypatch.setattr(device.platform, "system", lambda: "Windows")
    assert missing_cuda_libs(loader=_loader_fail, search_roots=[]) == []
