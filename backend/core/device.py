"""GPUアクセラレータの検出と、ROCm固有の設定。

ROCm版torchはHIPがCUDA APIを名乗る(torch.cuda.is_available()がTrueになる)ため、
torch.version.hip の有無で cuda / rocm を見分ける。
"""

import json
import subprocess
import sys
from functools import lru_cache


def _torch(torch_module=None):
    """torchを返す(テスト差し替え口)。import不能ならNone"""
    if torch_module is not None:
        return torch_module
    try:
        import torch

        return torch
    except Exception:
        return None


def detect_accel(torch_module=None) -> str:
    """利用可能なアクセラレータを返す: 'cuda' | 'rocm' | 'cpu'"""
    t = _torch(torch_module)
    if t is None:
        return "cpu"
    try:
        if not t.cuda.is_available():
            return "cpu"
        return "rocm" if getattr(t.version, "hip", None) else "cuda"
    except Exception:
        return "cpu"


def gpu_info(torch_module=None) -> dict:
    """GPU名とVRAM量を返す: {name, vram_total_mb, vram_free_mb}。GPU無しは空dict"""
    t = _torch(torch_module)
    if t is None:
        return {}
    try:
        if not t.cuda.is_available():
            return {}
        free, total = t.cuda.mem_get_info()
        return {
            "name": t.cuda.get_device_name(0),
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
    t = _torch(torch_module)
    if t is None:
        return
    try:
        if not t.cuda.is_available():
            return
        _, total = t.cuda.mem_get_info()
        t.cuda.set_per_process_memory_fraction(min(1.0, budget_mb / (total / 1024**2)))
    except Exception:
        pass  # 上限設定の失敗で処理自体は止めない


@lru_cache(maxsize=1)
def probe_gpu() -> dict:
    """別プロセスでGPUを調べる: {accel, name, vram_total_mb, vram_free_mb}。

    torchの初期化は実測5秒かかり、その間GILを握るのでAPIプロセス内で行うと
    サーバー全体が固まる。表示用の情報なので子プロセスに逃がして本体を止めない
    (ASR・話者分離のジョブ内では既にtorchを読むので直接 detect_accel を使う)。
    """
    code = (
        "import json,torch\n"
        "d={'accel':'cpu','name':'','vram_total_mb':0,'vram_free_mb':0}\n"
        "if torch.cuda.is_available():\n"
        "    d['accel']='rocm' if getattr(torch.version,'hip',None) else 'cuda'\n"
        "    free,total=torch.cuda.mem_get_info()\n"
        "    d.update(name=torch.cuda.get_device_name(0),\n"
        "             vram_total_mb=int(total/1024**2), vram_free_mb=int(free/1024**2))\n"
        "print(json.dumps(d))"
    )
    try:
        out = subprocess.run(
            [sys.executable, "-c", code], capture_output=True, text=True, timeout=120
        )
        return json.loads(out.stdout.strip().splitlines()[-1])
    except Exception:
        # 子プロセスが使えない環境ではプロセス内で調べる(初回のみ遅い)
        return {"accel": detect_accel(), **gpu_info()}


def apply_rocm_workarounds(torch_module=None) -> None:
    """ROCm環境で必要なtorchの設定を1箇所で行う(プロセス起動時に1回)。

    torch(rocm wheel)同梱のMIOpenはDropoutカーネルの実行時コンパイルに失敗する
    (rocrandヘッダ不整合)。cudnn APIを無効化するとpyannoteのLSTMが通常のHIP
    カーネルで動く(RX 7900 XTX実測: CPU比 約2.8倍高速で結果は同一)。
    """
    t = _torch(torch_module)
    if t is None or detect_accel(t) != "rocm":
        return
    try:
        t.backends.cudnn.enabled = False
    except Exception:
        pass
