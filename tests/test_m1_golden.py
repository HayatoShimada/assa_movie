"""M1受け入れ基準: transcribe.py の出力が移植前のgoldenとbyte一致すること。

GPU実行(約40秒)を伴うため、既定ではスキップする。実行するには:
    uv run pytest -m gpu --run-gpu
"""

import filecmp
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

GOLDEN = Path("tests/golden")


@pytest.mark.gpu
def test_transcribe_matches_golden(run_gpu, tmp_path):
    if not run_gpu:
        pytest.skip("GPUテストは --run-gpu 指定時のみ実行")

    wav = tmp_path / "smoke.wav"
    shutil.copy(GOLDEN / "smoke.wav", wav)

    result = subprocess.run(
        [sys.executable, "transcribe.py", str(wav), "ja"],
        capture_output=True, text=True, timeout=900,
    )
    assert result.returncode == 0, result.stderr

    assert filecmp.cmp(wav.with_suffix(".srt"), GOLDEN / "smoke.srt", shallow=False), \
        "SRTがgoldenと一致しません"
    assert filecmp.cmp(wav.with_suffix(".txt"), GOLDEN / "smoke.txt", shallow=False), \
        "TXTがgoldenと一致しません"
