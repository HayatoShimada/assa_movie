"""M34: WindowsでGPUが「無し」と表示される問題。

RX 7900 XTX を積んだWindows機で「GPUなし(CPUで動きます)」と出ていた。
検出をベンダーCLI(nvidia-smi / rocm-smi)だけに頼っていたためで、

- nvidia-smi はドライバ同梱物。NVIDIA機以外には無い
- rocm-smi は ROCm スタックの一部で Linux 専用。AMDのWindowsドライバには無い

どちらも「同梱すれば解決する」たぐいのものではない。OSは表示アダプタを
知っているので、そちらに聞く(Windowsはレジストリ)。

ただし**見えることと使えることは別**。AMDのWindows機はROCmが無く、
CTranslate2もCUDA専用なので、文字起こしはCPUで動く。表示用のGPU情報と、
計算に使えるかどうかは分けて扱う。
"""

import pytest

from backend.core.device import parse_windows_adapters

# 実機(RX 7900 XTX)のレジストリから読んだ実際の値
RADEON = {
    "DriverDesc": "AMD Radeon RX 7900 XTX",
    "HardwareInformation.qwMemorySize": 25753026560,
    # 32bitの方は溢れて4GB相当になる。こちらを使ってはいけない
    "HardwareInformation.MemorySize": 4293918720,
}
GEFORCE = {
    "DriverDesc": "NVIDIA GeForce RTX 4090",
    "HardwareInformation.qwMemorySize": 25757220864,
}
BASIC = {"DriverDesc": "Microsoft Basic Display Adapter"}


def test_搭載GPUの名前とVRAMを読む():
    got = parse_windows_adapters([RADEON])
    assert got["name"] == "AMD Radeon RX 7900 XTX"
    assert got["vram_total_mb"] == 24560  # 25753026560 / 1024^2
    # 計算に使えるとは限らない。判断材料を持たないので cpu のまま
    assert got["accel"] == "cpu"


def test_64bitの値を使う():
    """32bitのMemorySizeは4GBで頭打ちになる(実機で確認)"""
    got = parse_windows_adapters([RADEON])
    assert got["vram_total_mb"] > 20000, "溢れた値を読んでいる"


def test_qwMemorySizeが無ければ32bitの値で代替する():
    got = parse_windows_adapters([{"DriverDesc": "Intel UHD Graphics", "HardwareInformation.MemorySize": 1073741824}])
    assert got["name"] == "Intel UHD Graphics"
    assert got["vram_total_mb"] == 1024


def test_ソフトウェアアダプタは無視する():
    """リモートデスクトップ等で出てくる。GPUとして扱うと誤解を招く"""
    assert parse_windows_adapters([BASIC]) == {}


def test_実GPUがあればソフトウェアアダプタより優先する():
    got = parse_windows_adapters([BASIC, RADEON])
    assert got["name"] == "AMD Radeon RX 7900 XTX"


def test_VRAMが多いものを主GPUとみなす():
    """内蔵と外付けが両方見えることがある。外付けを選びたい"""
    igpu = {"DriverDesc": "AMD Radeon Graphics", "HardwareInformation.qwMemorySize": 536870912}
    got = parse_windows_adapters([igpu, GEFORCE])
    assert got["name"] == "NVIDIA GeForce RTX 4090"


def test_何も無ければ空():
    assert parse_windows_adapters([]) == {}
    assert parse_windows_adapters([{"DriverDesc": ""}]) == {}


@pytest.mark.parametrize("entry", [
    {"DriverDesc": "AMD Radeon RX 7900 XTX"},                                  # VRAM不明
    {"DriverDesc": "AMD Radeon RX 7900 XTX", "HardwareInformation.qwMemorySize": 0},
])
def test_VRAMが読めなくても名前は出す(entry):
    """「GPUなし」と言い切るよりは、名前だけでも出したほうが親切"""
    got = parse_windows_adapters([entry])
    assert got["name"] == "AMD Radeon RX 7900 XTX"
    assert got["vram_total_mb"] == 0
