"""M23: 声の高さ推定(numpy実装)のテスト。torch不要で動くこと。"""

import numpy as np
import pytest

from backend.pipeline.pitch import SAMPLE_RATE, estimate_f0, median_f0

def _tone(freq: float, seconds: float = 1.0, sr: int = SAMPLE_RATE) -> np.ndarray:
    """基本周波数freqの疑似音声(倍音入りの方が実声に近い)"""
    t = np.arange(int(seconds * sr)) / sr
    return (
        0.6 * np.sin(2 * np.pi * freq * t)
        + 0.3 * np.sin(2 * np.pi * 2 * freq * t)
        + 0.1 * np.sin(2 * np.pi * 3 * freq * t)
    ).astype(np.float32)


@pytest.mark.parametrize("freq", [90, 120, 150, 200, 260])
def test_estimate_f0_recovers_known_pitch(freq):
    """既知の周波数を±8%で当てられること(男女判定はこの精度で足りる)"""
    got = median_f0(_tone(freq))
    assert got is not None
    assert abs(got - freq) / freq < 0.08, f"{freq}Hz を {got}Hz と推定した"


def test_male_and_female_are_ordered():
    """男女判定は「どちらが低いか」だけ使うので、順序が保たれれば良い"""
    male, female = median_f0(_tone(110)), median_f0(_tone(220))
    assert male is not None and female is not None
    assert male < female


def test_silence_returns_none():
    assert median_f0(np.zeros(SAMPLE_RATE, dtype=np.float32)) is None


def test_noise_returns_none_or_ignores():
    rng = np.random.default_rng(0)
    noise = rng.normal(0, 0.05, SAMPLE_RATE).astype(np.float32)
    # 白色雑音に安定した基本周波数は無いので、Noneか極端な値にならないこと
    got = median_f0(noise)
    assert got is None or 60 <= got <= 400


def test_too_short_returns_none():
    assert median_f0(_tone(120, seconds=0.01)) is None


def test_estimate_f0_frames_are_within_range():
    f0 = estimate_f0(_tone(150, seconds=2.0))
    voiced = f0[f0 > 0]
    assert len(voiced) > 5
    assert voiced.min() >= 60 and voiced.max() <= 400
