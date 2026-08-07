"""顔検出による縦型レイアウトの自動決定。

検出はOpenCVのHaarカスケード(同梱・ネットワーク不要)。mediapipeは
numpy<2固定でtorch 2.8系と衝突するため採用しない。検出そのものは薄いI/O層に
留め、クロップ計画の決定(make_face_plan)は純関数としてテストする。
"""

from pathlib import Path
from statistics import median

from backend.pipeline.layout import FacePlan

Box = tuple[int, int, int, int]  # (x, y, w, h)

# クリップ内でフレームを抜く位置(全体の10%〜90%の5点)
SAMPLE_FRACTIONS = (0.1, 0.3, 0.5, 0.7, 0.9)
# x中心の距離がこれを超えたら別人物のクラスタとみなす(画面幅比)
CLUSTER_GAP = 0.2
# クラスタとして信頼する最小検出数(誤検出の外れ値を捨てる)
MIN_CLUSTER_MEMBERS = 2


def sample_times(start: float, end: float) -> list[float]:
    """クリップ範囲からサンプリング時刻を作る(純関数)"""
    duration = max(0.0, end - start)
    return [start + duration * f for f in SAMPLE_FRACTIONS]


def sample_frames(path: Path, times: list[float]) -> list:
    """指定時刻のフレームを取り出す(I/O層。opencvはffmpeg同梱なので単体で動く)"""
    import cv2

    cap = cv2.VideoCapture(str(path))
    frames = []
    try:
        for t in times:
            cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
            ok, frame = cap.read()
            frames.append(frame if ok else None)
    finally:
        cap.release()
    return frames


def detect_faces(frame) -> list[Box]:
    """1フレームから顔ボックスを検出する(I/O層)"""
    import cv2

    if frame is None:
        return []
    cascade = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    )
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    min_size = max(40, frame.shape[0] // 10)  # 小さすぎる検出はノイズ
    faces = cascade.detectMultiScale(
        gray, scaleFactor=1.1, minNeighbors=5, minSize=(min_size, min_size)
    )
    return [tuple(int(v) for v in f) for f in faces]


def make_face_plan(samples: list[list[Box]], src_w: int, src_h: int) -> FacePlan:
    """サンプルフレームごとの顔ボックス群からクロップ計画を決める(純関数)。

    - 検出できたサンプルが半数未満なら 'none'(→ blur_padへフォールバック)
    - x中心を1次元クラスタリング(ギャップ>0.2で分割)し、
      少数派クラスタ(誤検出)を捨てる
    - 1クラスタ→'single'(中央値)、2クラスタ以上→'stack'(左右順の中央値2つ)
    """
    n = len(samples)
    detected = [boxes for boxes in samples if boxes]
    if n == 0 or len(detected) * 2 < n:
        return FacePlan(mode="none", centers=())

    centers = sorted(
        (x + w / 2) / src_w for boxes in samples for (x, _y, w, _h) in boxes
    )
    if not centers:
        return FacePlan(mode="none", centers=())

    clusters: list[list[float]] = [[centers[0]]]
    for c in centers[1:]:
        if c - clusters[-1][-1] > CLUSTER_GAP:
            clusters.append([c])
        else:
            clusters[-1].append(c)
    clusters = [cl for cl in clusters if len(cl) >= MIN_CLUSTER_MEMBERS]
    if not clusters:
        return FacePlan(mode="none", centers=())
    if len(clusters) == 1:
        return FacePlan(mode="single", centers=(median(clusters[0]),))

    # 検出数の多い2クラスタ=主要な2話者(左→右順)
    top2 = sorted(sorted(clusters, key=len, reverse=True)[:2], key=median)
    return FacePlan(mode="stack", centers=(median(top2[0]), median(top2[1])))
