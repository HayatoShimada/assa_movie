"""GPUアクセラレータの検出と、ROCm固有の設定。

検出はベンダーのCLI(nvidia-smi / rocm-smi)を第一手にする。torchに聞くと
初期化に実測5秒かかるうえ、配布物からtorchを外すとROCm機でも "cpu" と判定され、
whisper.cppがあるのに遅いエンジンが黙って選ばれてしまう(rocm-smiは実測55ms)。

torchが要るのはASRエンジン側だけなので、そこでは従来どおり
torch.version.hip の有無で cuda / rocm を見分ける
(ROCm版torchはHIPがCUDA APIを名乗るため)。
"""

import json
import platform
import shutil
import subprocess
import sys
from functools import lru_cache

EMPTY_GPU = {"accel": "cpu", "name": "", "vram_total_mb": 0, "vram_free_mb": 0}
CLI_TIMEOUT = 5


def _torch(torch_module=None):
    """torchを返す(テスト差し替え口)。import不能ならNone"""
    if torch_module is not None:
        return torch_module
    try:
        import torch

        return torch
    except Exception:
        return None


def _run(cmd: list[str]) -> str:
    """外部コマンドの標準出力。失敗したら空文字(テスト差し替え口)"""
    if not shutil.which(cmd[0]):
        return ""
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=CLI_TIMEOUT)
        return out.stdout if out.returncode == 0 else ""
    except (subprocess.SubprocessError, OSError):
        return ""


def parse_nvidia_smi(output: str) -> dict:
    """`nvidia-smi --query-gpu=name,memory.total,memory.free` の出力を読む(純関数)"""
    line = next((l for l in output.splitlines() if l.strip()), "")
    parts = [p.strip() for p in line.split(",")]
    if len(parts) != 3:
        return {}
    try:
        total, free = int(parts[1]), int(parts[2])
    except ValueError:
        return {}
    return {
        "accel": "cuda",
        "name": parts[0],
        "vram_total_mb": total,
        "vram_free_mb": free,
    }


def parse_rocm_smi(memory_json: str, name_json: str) -> dict:
    """`rocm-smi --showmeminfo vram --json` と `--showproductname --json` を読む(純関数)。

    rocm-smiは合計と使用中しか出さないので、空きは引き算で求める。
    """
    try:
        cards = json.loads(memory_json)
        card = next(iter(cards.values()))
        total = int(card["VRAM Total Memory (B)"])
        used = int(card.get("VRAM Total Used Memory (B)", 0))
    except (json.JSONDecodeError, StopIteration, KeyError, ValueError, TypeError, AttributeError):
        return {}
    if total <= 0:
        return {}

    name = "AMD GPU"
    try:
        card = next(iter(json.loads(name_json).values()))
        name = card.get("Card series") or card.get("Card model") or name
    except (json.JSONDecodeError, StopIteration, ValueError, TypeError, AttributeError):
        pass  # 名前が取れなくても検出そのものは成立させる

    return {
        "accel": "rocm",
        "name": name,
        "vram_total_mb": int(total / 1024**2),
        "vram_free_mb": int((total - used) / 1024**2),
    }


def parse_mac_gpu(chipset_output: str, total_ram_bytes: int) -> dict:
    """macOSのGPU情報を読む(純関数)。

    Apple Siliconはユニファイドメモリなので、搭載RAMがそのままGPUから使える量。
    Intel MacのdGPUは扱いが違うため、ここでは対象にしない。
    """
    line = next(
        (l for l in chipset_output.splitlines() if "Chipset Model:" in l), ""
    )
    name = line.split(":", 1)[1].strip() if ":" in line else ""
    if not name.startswith("Apple ") or total_ram_bytes <= 0:
        return {}
    total_mb = int(total_ram_bytes / 1024**2)
    return {
        "accel": "metal",
        "name": name,
        "vram_total_mb": total_mb,
        "vram_free_mb": total_mb,
    }


def probe_gpu_mac() -> dict:
    """macOSのGPUを調べる。Apple Silicon以外は空dict"""
    try:
        ram = int(_run(["sysctl", "-n", "hw.memsize"]).strip() or 0)
    except ValueError:
        return {}
    return parse_mac_gpu(_run(["system_profiler", "SPDisplaysDataType"]), ram)


def probe_gpu_cli() -> dict:
    """ベンダーCLIからGPUを調べる。見つからなければ空dict"""
    if platform.system() == "Darwin":
        return probe_gpu_mac()
    nvidia = parse_nvidia_smi(
        _run(["nvidia-smi", "--query-gpu=name,memory.total,memory.free",
              "--format=csv,noheader,nounits"])
    )
    if nvidia:
        return nvidia
    return parse_rocm_smi(
        _run(["rocm-smi", "--showmeminfo", "vram", "--json"]),
        _run(["rocm-smi", "--showproductname", "--json"]),
    )


def detect_accel(torch_module=None) -> str:
    """利用可能なアクセラレータを返す: 'cuda' | 'rocm' | 'cpu'"""
    if torch_module is None:
        # 通常経路。torchが無くても正しく判定できる
        return probe_gpu()["accel"]
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
    """GPUを調べる: {accel, name, vram_total_mb, vram_free_mb}。

    まずベンダーCLI(実測55ms)。無い環境だけtorchに聞く。
    """
    return probe_gpu_cli() or _probe_gpu_torch() or dict(EMPTY_GPU)


def _probe_gpu_torch() -> dict:
    """torchに聞く(CLIが無い環境向けの保険)。

    torchの初期化は実測5秒かかり、その間GILを握るのでAPIプロセス内で行うと
    サーバー全体が固まる。子プロセスに逃がして本体を止めない。
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
        info = json.loads(out.stdout.strip().splitlines()[-1])
        return info if info.get("accel") != "cpu" else {}
    except Exception:
        return {}


def apply_rocm_workarounds(torch_module=None) -> None:
    """ROCm環境で必要なtorchの設定を1箇所で行う(プロセス起動時に1回)。

    torch(rocm wheel)同梱のMIOpenはDropoutカーネルの実行時コンパイルに失敗する
    (rocrandヘッダ不整合)。cudnn APIを無効化するとpyannoteのLSTMが通常のHIP
    カーネルで動く(RX 7900 XTX実測: CPU比 約2.8倍高速で結果は同一)。
    """
    t = _torch(torch_module)
    if t is None or detect_accel(torch_module=t) != "rocm":
        return
    try:
        t.backends.cudnn.enabled = False
    except Exception:
        pass
