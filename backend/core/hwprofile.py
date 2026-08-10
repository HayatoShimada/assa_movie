"""ハードウェアプロファイル: 初回起動時に1回検出して固定する実行環境。

設計(DESIGN.md 2026-08-10):
- エンジン選択は実行時の自動判定をやめ、検出済みプロファイル
  (OS: linux/windows/mac × GPU: nvidia/radeon/apple/cpu)から
  コード内の静的対応表(resolve_spec)で決定的に決める。
- DBに保存するのは検出結果(このモジュールのHwProfile)だけ。対応表は
  コードが持つため、アプリ更新で構成が変わっても自動で追従する
  (v0.9.5の「エンジン名の固定保存」事故を構造的に防ぐ)。
- GPU機はOS・ベンダーに関わらず whisper.cpp(Linux/Windows=Vulkan、mac=Metal)。
  CPU機は faster-whisper int8(モデルDL不要で必ず動く)。
"""

import json
import platform
import sqlite3
import subprocess
from dataclasses import asdict, dataclass, fields
from datetime import datetime

from backend.core.console import SUBPROCESS_TEXT

OS_NAMES = {"Linux": "linux", "Windows": "windows", "Darwin": "mac"}

# app_settings テーブル上の保存キー。MUTABLE_FIELDS には入れない
# (書き込み経路を初回検出と再検出APIだけに限定するため)
PROFILE_KEY = "hw_profile"

# Windowsレジストリ経由ではaccelが取れない(名前しか無い)ため、名前で分類する
NVIDIA_HINTS = ("nvidia", "geforce", "rtx", "quadro")
RADEON_HINTS = ("amd", "radeon")

VERIFY_TIMEOUT = 10


@dataclass(frozen=True)
class HwProfile:
    os: str                 # "linux" | "windows" | "mac"
    gpu: str                # "nvidia" | "radeon" | "apple" | "cpu"
    gpu_name: str = ""
    vram_total_mb: int = 0
    # 同梱whisper-cliが起動できたか(GPU機のみ有意。Vulkanローダ欠落等を検出)
    whispercpp_ok: bool = False
    detected_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "HwProfile":
        """保存済みJSONから復元する。未知キーは無視し、欠損は既定値で埋める
        (フィールドを増減しても旧DBが読めるように)"""
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known})


@dataclass(frozen=True)
class EngineSpec:
    engine: str                   # "faster_whisper" | "whispercpp"
    device: str                   # "cpu" | "vulkan" | "metal"
    compute_type: str             # "int8" | ""(whispercppに量子化指定の概念は無い)
    needs_whispercpp_model: bool  # ggml-large-v3.bin(3.1GB)の取得がセットアップ必須か
    label: str                    # UI表示用


def classify(probe: dict, os_name: str | None = None) -> tuple[str, str]:
    """probe_gpu()の結果を (os, gpuクラス) に分類する(純関数)。

    accelが取れる環境(nvidia-smi/rocm-smi/system_profiler)はそれで確定。
    Windows+AMDはレジストリ由来でaccel="cpu"のままなので、アダプタ名で判定する。
    """
    os_key = OS_NAMES.get(os_name or platform.system(), "linux")
    accel = probe.get("accel", "cpu")
    name = (probe.get("name") or "").lower()
    if accel == "cuda":
        gpu = "nvidia"
    elif accel == "rocm":
        gpu = "radeon"
    elif accel == "metal":
        gpu = "apple"
    elif any(h in name for h in NVIDIA_HINTS):
        gpu = "nvidia"
    elif any(h in name for h in RADEON_HINTS):
        gpu = "radeon"
    else:
        gpu = "cpu"
    return os_key, gpu


def resolve_spec(profile: HwProfile) -> EngineSpec:
    """プロファイル → エンジン構成の静的対応表。

    | os            | gpu                  | 構成                       |
    |---------------|----------------------|----------------------------|
    | linux/windows | nvidia/radeon        | whisper.cpp (Vulkan)       |
    | mac           | apple                | whisper.cpp (Metal)        |
    | 全OS          | cpu / 検証失敗       | faster-whisper (CPU int8)  |

    whispercpp_ok=False(バイナリが無い・起動できない)の機体は検出時点で
    cpu行に確定する。これは検出の一部であり、実行時フォールバックではない。
    """
    if profile.gpu == "cpu" or not profile.whispercpp_ok:
        return EngineSpec(
            engine="faster_whisper",
            device="cpu",
            compute_type="int8",  # CPUのint8は安全(クラッシュ実績はBlackwell GPU限定)
            needs_whispercpp_model=False,
            label="faster-whisper(CPU・int8)",
        )
    device = "metal" if profile.os == "mac" else "vulkan"
    return EngineSpec(
        engine="whispercpp",
        device=device,
        compute_type="",
        needs_whispercpp_model=True,
        label=f"whisper.cpp({'Metal' if device == 'metal' else 'Vulkan'})",
    )


def _run_returncode(cmd: list[str], timeout: float) -> int:
    """ヘルプ表示の実行結果。起動できていれば0を返す。

    共有ライブラリを解決できないバイナリはローダーが落とすので、ここで分かる。
    使い方を表示しているなら終了コードが0でなくても「起動できた」とみなす
    (CLIによって -h の終了コードが違う)。
    """
    done = subprocess.run(cmd, capture_output=True, timeout=timeout, **SUBPROCESS_TEXT)
    if done.returncode == 0:
        return 0
    printed = f"{done.stdout or ''}{done.stderr or ''}".lower()
    return 0 if "usage" in printed else done.returncode


def verify_whispercpp(runner=None) -> bool:
    """同梱(または自前ビルドの)whisper-cliが実際に起動できるかを確かめる。

    ファイルの存在だけでは「使える」保証にならない(CUDAライブラリで同じ誤判定を
    して落ちた実例がある)。動的リンクの解決失敗などをここで見抜く。
    runnerはテスト差し替え口。
    """
    from backend.engines.asr import whispercpp

    binary = whispercpp.resolve_binary()
    if binary is None:
        return False
    run = runner if runner is not None else _run_returncode
    try:
        return run([str(binary), "-h"], VERIFY_TIMEOUT) == 0
    except Exception:
        return False


# プロセス内の現在値。lifespanのensure_profileが確定し、build_engineが参照する
_current: HwProfile | None = None


def set_current(profile: HwProfile | None) -> None:
    global _current
    _current = profile


def current() -> HwProfile:
    """確定済みのプロファイル。

    アプリ起動時(lifespan)に ensure_profile が設定する。CLIスクリプト等の
    DBを介さない経路では、その場で検出してプロセス内にだけ保持する。
    """
    global _current
    if _current is None:
        _current = detect(now=_now())
    return _current


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def load_profile(conn: sqlite3.Connection) -> HwProfile | None:
    row = conn.execute(
        "SELECT value_json FROM app_settings WHERE key=?", (PROFILE_KEY,)
    ).fetchone()
    if row is None:
        return None
    try:
        return HwProfile.from_dict(json.loads(row["value_json"]))
    except (json.JSONDecodeError, TypeError):
        return None  # 壊れた保存値で起動不能にしない(検出し直す)


def save_profile(conn: sqlite3.Connection, profile: HwProfile) -> None:
    conn.execute(
        "INSERT INTO app_settings (key, value_json) VALUES (?, ?)"
        " ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json",
        (PROFILE_KEY, json.dumps(profile.to_dict(), ensure_ascii=False)),
    )
    conn.commit()


def ensure_profile(conn: sqlite3.Connection, detector=None) -> HwProfile:
    """保存済みプロファイルを読む。無ければ検出して保存する(初回起動の1回だけ)。

    「最初に認識した環境で固定」— 起動のたびに検出し直さない。
    環境が変わったときの追従は redetect(再検出API)だけが行う。
    """
    profile = load_profile(conn)
    if profile is None:
        profile = (detector or (lambda: detect(now=_now())))()
        save_profile(conn, profile)
    set_current(profile)
    return profile


def redetect(conn: sqlite3.Connection, detector=None) -> HwProfile:
    """明示操作(POST /api/environment/redetect)による再検出・上書き保存"""
    from backend.core import device

    device.probe_gpu.cache_clear()  # GPU増設・ドライバ導入後の変化を拾う
    profile = (detector or (lambda: detect(now=_now())))()
    save_profile(conn, profile)
    set_current(profile)
    return profile


def detect(now: str, runner=None, os_name: str | None = None) -> HwProfile:
    """環境を検出してプロファイルを組み立てる(初回起動と「再検出」からのみ呼ぶ)。

    どんな失敗でも例外にせずcpuプロファイルへ落とす。cpu行(faster-whisper int8)
    は全OSで必ず動く終端なので、検出失敗でアプリが使えなくなることはない。
    """
    from backend.core import device

    try:
        probe = device.probe_gpu()
    except Exception:
        probe = {}
    os_key, gpu = classify(probe, os_name)
    # cpu機の構成にwhisper-cliは関係ないので検証しない(起動を速く保つ)
    whisper_ok = gpu != "cpu" and verify_whispercpp(runner=runner)
    return HwProfile(
        os=os_key,
        gpu=gpu,
        gpu_name=probe.get("name", "") or "",
        vram_total_mb=int(probe.get("vram_total_mb", 0) or 0),
        whispercpp_ok=whisper_ok,
        detected_at=now,
    )
