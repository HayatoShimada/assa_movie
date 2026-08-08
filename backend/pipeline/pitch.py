"""声の高さ(基本周波数)の推定。numpyだけで動く。

男女2人の対談で「低い方=男性」を決めるのに使う。
torchaudio.functional.detect_pitch_frequency を置き換えたもので、
話者分離をONNX化してtorchを外すため(docs/V1_PLAN.md M23)。

アルゴリズムはYIN(差分関数 + 累積平均正規化)。素の自己相関だと、ラグが伸びるほど
重なりが短くなって相関値も小さくなるため、実音声では短いラグ(=高い周波数)に偏る。

2026-08-08の実測(300秒の対談音声、話者ごとに60秒分の中央値):

|            | 男性   | 女性   | 差    |
|------------|--------|--------|-------|
| 本実装(YIN)| 149Hz  | 189Hz  | 40Hz  |
| torchaudio | 114Hz  | 143Hz  | 29Hz  |

絶対値は3割ほど違うが、フレーム単位ではどちらも±50Hz以上ばらつく推定で、
実音声の正解値は手元にない。ここで必要なのは「2人のどちらが低いか」だけで、
その判定は両者一致し、本実装の方が2人の差が開いて判定は安定する。
合成音での精度は tests/test_m23_pitch.py で±8%を保証している。
"""

import numpy as np

SAMPLE_RATE = 16000
# 人の声の基本周波数の範囲(男性は低め、女性は高め)
FREQ_LOW = 60
FREQ_HIGH = 400
FRAME_SEC = 0.05      # 差分を取る窓の長さ
HOP_SEC = 0.025       # 窓の間隔
# 正規化した差分がこれを下回った最初のラグを周期とみなす。
# 大域最小ではなく「最初」を採るのが、倍音を掴む誤り(オクターブエラー)を防ぐ肝
YIN_THRESHOLD = 0.15


def _frame_f0(seg: np.ndarray, sr: int, min_lag: int, max_lag: int) -> float:
    """1フレームの基本周波数(Hz)。推定できなければ0"""
    width = seg.size - max_lag
    head = seg[:width]
    energy = float(np.dot(head, head))
    if energy <= 1e-8:
        return 0.0

    # 差分関数 d(τ) = Σ(x[j] - x[j+τ])² を自己相関と累積和から組み立てる
    corr = np.correlate(seg, head, mode="valid")[:max_lag + 1]
    sq = np.concatenate(([0.0], np.cumsum(seg * seg)))
    shifted_energy = sq[width:width + max_lag + 1] - sq[:max_lag + 1]
    diff = energy + shifted_energy - 2 * corr

    # 累積平均で正規化(YIN)。これで窓長によるラグ方向の偏りが消える
    cumulative = np.cumsum(diff[1:])
    lags = np.arange(1, diff.size)
    norm = np.where(cumulative > 0, diff[1:] * lags / cumulative, 1.0)

    window = norm[min_lag - 1:max_lag]
    below = np.flatnonzero(window < YIN_THRESHOLD)
    if below.size:
        lag = int(below[0]) + min_lag
    else:
        lag = int(np.argmin(window)) + min_lag
        if window[lag - min_lag] > 0.5:  # どのラグも周期らしくない(無声・雑音)
            return 0.0

    # 放物線補間でラグを小数精度にする(整数ラグだと高い声ほど誤差が大きい)
    if min_lag < lag < max_lag:
        a, b, c = norm[lag - 2], norm[lag - 1], norm[lag]
        denom = a + c - 2 * b
        if denom != 0:
            lag += 0.5 * (a - c) / denom
    return sr / lag


def estimate_f0(
    audio: np.ndarray,
    sr: int = SAMPLE_RATE,
    freq_low: int = FREQ_LOW,
    freq_high: int = FREQ_HIGH,
) -> np.ndarray:
    """フレームごとの基本周波数(Hz)を返す。無声のフレームは0(純関数)"""
    width = int(FRAME_SEC * sr)
    hop = int(HOP_SEC * sr)
    min_lag = max(2, int(sr / freq_high))
    max_lag = int(sr / freq_low)
    # 差分にはラグの分だけ余分な後続サンプルが要る
    frame = width + max_lag
    if audio.size < frame:
        return np.zeros(0, dtype=np.float32)

    audio = audio.astype(np.float64)
    out = [
        _frame_f0(audio[start:start + frame], sr, min_lag, max_lag)
        for start in range(0, audio.size - frame + 1, hop)
    ]
    return np.array(out, dtype=np.float32)


def median_f0(audio: np.ndarray, sr: int = SAMPLE_RATE) -> float | None:
    """有声フレームの基本周波数の中央値。推定できなければNone"""
    f0 = estimate_f0(audio, sr)
    voiced = f0[f0 > 0]
    if voiced.size == 0:
        return None
    return float(np.median(voiced))
