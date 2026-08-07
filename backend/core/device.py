"""GPUアクセラレータの検出。

ROCm版torchはHIPがCUDA APIを名乗る(torch.cuda.is_available()がTrueになる)ため、
torch.version.hip の有無で cuda / rocm を見分ける。
"""


def detect_accel(torch_module=None) -> str:
    """利用可能なアクセラレータを返す: 'cuda' | 'rocm' | 'cpu'

    torch_module はテスト用の差し替え口。省略時は実torchをimportする。
    """
    if torch_module is None:
        try:
            import torch as torch_module
        except Exception:
            return "cpu"
    try:
        if not torch_module.cuda.is_available():
            return "cpu"
        if getattr(torch_module.version, "hip", None):
            return "rocm"
        return "cuda"
    except Exception:
        return "cpu"
