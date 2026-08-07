"""GPUアクセラレータの検出。

ROCm版torchはHIPがCUDA APIを名乗る(torch.cuda.is_available()がTrueになる)ため、
torch.version.hip の有無で cuda / rocm を見分ける。
"""


def gpu_info(torch_module=None) -> dict:
    """GPU名とVRAM量を返す: {name, vram_total_mb, vram_free_mb}。GPU無しは空dict"""
    if torch_module is None:
        try:
            import torch as torch_module
        except Exception:
            return {}
    try:
        if not torch_module.cuda.is_available():
            return {}
        free, total = torch_module.cuda.mem_get_info()
        return {
            "name": torch_module.cuda.get_device_name(0),
            "vram_total_mb": int(total / 1024**2),
            "vram_free_mb": int(free / 1024**2),
        }
    except Exception:
        return {}


def apply_vram_budget(budget_mb: int, torch_module=None) -> None:
    """torch系コンポーネント(transformers ASR・pyannote)のVRAM使用上限を設定する。

    0は無制限。faster-whisper(CTranslate2)とOllama(別プロセス)には効かないため、
    それらはUI側でVRAM目安を表示して選択を促す。
    """
    if budget_mb <= 0:
        return
    if torch_module is None:
        try:
            import torch as torch_module
        except Exception:
            return
    try:
        if not torch_module.cuda.is_available():
            return
        _, total = torch_module.cuda.mem_get_info()
        fraction = min(1.0, budget_mb / (total / 1024**2))
        torch_module.cuda.set_per_process_memory_fraction(fraction)
    except Exception:
        pass  # 上限設定の失敗で処理自体は止めない


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
