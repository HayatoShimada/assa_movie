"""GPU搭載情報の検出(ハードウェアプロファイル確定時に1回だけ使う)。

検出はベンダーのCLI(nvidia-smi / rocm-smi / system_profiler)を第一手にする
(rocm-smiは実測55ms)。CLIが無い環境ではOSに聞く(Windowsはレジストリ)。
nvidia-smiはドライバ同梱物、rocm-smiはLinux専用なので、AMDのWindows機には
どちらも存在せず、CLIだけに頼ると「GPUなし」と誤判定する。ただしOSから分かるのは
搭載の有無だけで、accelは"cpu"のまま(GPUクラスの分類は hwprofile.classify が
アダプタ名から行う)。

結果の解釈(OS×GPUクラスへの分類・エンジン選択)は backend/core/hwprofile.py が
持つ。ここは情報を取るだけ。torchへの問い合わせは2026-08-10に削除した
(配布物にtorchが無く、CLI+レジストリで全クラスを判定できるため)。
"""

import json
import platform
import shutil
import subprocess
from functools import lru_cache

from backend.core.console import SUBPROCESS_TEXT

EMPTY_GPU = {"accel": "cpu", "name": "", "vram_total_mb": 0, "vram_free_mb": 0}
CLI_TIMEOUT = 5


def _run(cmd: list[str]) -> str:
    """外部コマンドの標準出力。失敗したら空文字(テスト差し替え口)"""
    if not shutil.which(cmd[0]):
        return ""
    try:
        out = subprocess.run(
            cmd, capture_output=True, timeout=CLI_TIMEOUT, **SUBPROCESS_TEXT
        )
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


# 表示アダプタのクラスGUID(Windows)。ここ配下に各アダプタが 0000, 0001... で並ぶ
WINDOWS_DISPLAY_CLASS = r"SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}"
# GPUとして数えないもの(リモートデスクトップ等で出てくる)
WINDOWS_SOFTWARE_ADAPTERS = ("microsoft basic display", "microsoft remote display", "rdpdd")


def parse_windows_adapters(entries: list[dict]) -> dict:
    """レジストリから読んだ表示アダプタの一覧から、主GPUを選ぶ(純関数)。

    VRAMは64bitの qwMemorySize を使う。32bitの MemorySize は4GBで頭打ちになり、
    24GBのカードが4GBに見える(実機で確認)。

    accelは "cpu" のまま返す。ここで分かるのは「積んでいること」だけで、
    計算に使えるかどうか(CUDA/ROCmが入っているか)は別の話だから。
    """
    best: dict = {}
    for entry in entries:
        name = str(entry.get("DriverDesc") or "").strip()
        if not name or any(s in name.lower() for s in WINDOWS_SOFTWARE_ADAPTERS):
            continue
        size = entry.get("HardwareInformation.qwMemorySize")
        if not size:
            size = entry.get("HardwareInformation.MemorySize") or 0
        try:
            vram_mb = int(int(size) / 1024**2)
        except (TypeError, ValueError):
            vram_mb = 0
        # 内蔵と外付けが両方見えることがある。VRAMの大きいほうを主GPUとみなす
        if not best or vram_mb > best["vram_total_mb"]:
            best = {"accel": "cpu", "name": name, "vram_total_mb": vram_mb, "vram_free_mb": 0}
    return best


def probe_gpu_windows() -> dict:
    """Windowsの表示アダプタをレジストリから読む。

    ベンダーCLIに頼らない。nvidia-smiはドライバ同梱物、rocm-smiはLinux専用で、
    AMDのWindows機ではどちらも存在しない。レジストリなら外部プロセスを
    起こさずに済むので速い。
    """
    if platform.system() != "Windows":
        return {}
    try:
        import winreg
    except ImportError:
        return {}

    entries: list[dict] = []
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, WINDOWS_DISPLAY_CLASS) as root:
            for index in range(64):  # 実際は数個。暴走しないよう上限を置く
                try:
                    subkey = winreg.EnumKey(root, index)
                except OSError:
                    break
                if not subkey.isdigit():
                    continue
                try:
                    with winreg.OpenKey(root, subkey) as key:
                        values = {}
                        for i in range(winreg.QueryInfoKey(key)[1]):
                            try:
                                vname, vdata, _ = winreg.EnumValue(key, i)
                            except OSError:
                                break
                            values[vname] = vdata
                        entries.append(values)
                except OSError:
                    continue
    except OSError:
        return {}
    return parse_windows_adapters(entries)


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


def probe_gpu_cli(os_name: str | None = None) -> dict:
    """ベンダーCLIからGPUを調べる。見つからなければ空dict。

    os_name を渡せるのは、macOSだけ経路が違う(system_profiler)ため。
    実行中のOSに任せるとNVIDIA/AMDの判定テストがmacOSで意味を失う
    """
    if (os_name or platform.system()) == "Darwin":
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


@lru_cache(maxsize=1)
def probe_gpu() -> dict:
    """GPUを調べる: {accel, name, vram_total_mb, vram_free_mb}。

    まずベンダーCLI(実測55ms)。無ければOSに聞く。

    OS問い合わせで分かるのは「積んでいること」だけなので accel は "cpu" の
    ままになる(GPUクラスの分類は hwprofile.classify がアダプタ名で行う)。
    それでも名前を出す価値はある: RX 7900 XTX を積んだWindows機に
    「GPUなし」と言うのは、事実として誤りだった。
    """
    return probe_gpu_cli() or probe_gpu_windows() or dict(EMPTY_GPU)
