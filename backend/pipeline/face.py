"""顔検出による縦型レイアウトの自動決定。

検出はOpenCVのHaarカスケード(同梱・ネットワーク不要)。mediapipeは
numpy<2固定でtorch 2.8系と衝突するため採用しない。検出そのものは薄いI/O層に
留め、クロップ計画の決定(make_face_plan)は純関数としてテストする。
"""

import os
from pathlib import Path
from statistics import median

from backend.pipeline.layout import FacePlan

# torch(ROCm wheel)が旧HSAランタイムを先にロードした状態でOpenCVが
# システムROCmのOpenCLを遅延ロードすると、シンボル不整合でプロセスごと落ちる
# (symbol lookup error: libamdocl64.so)。顔検出はCPUで十分なのでOpenCLを無効化する。
# cv2のimportより前に設定する必要がある
os.environ.setdefault("OPENCV_OPENCL_RUNTIME", "disabled")

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


def _merge_boxes(boxes: list[Box]) -> list[Box]:
    """重なりの大きいボックスを統合する(同じ顔の正面/横顔の二重検出対策)"""
    merged: list[Box] = []
    for box in sorted(boxes, key=lambda b: b[2] * b[3], reverse=True):
        x, y, w, h = box
        overlaps = False
        for mx, my, mw, mh in merged:
            ix = min(x + w, mx + mw) - max(x, mx)
            iy = min(y + h, my + mh) - max(y, my)
            if ix > 0 and iy > 0 and ix * iy > 0.3 * min(w * h, mw * mh):
                overlaps = True
                break
        if not overlaps:
            merged.append(box)
    return merged


def detect_faces(frame) -> list[Box]:
    """1フレームから顔ボックスを検出する(I/O層)。

    対談では話者が互いに向き合って横顔になることが多いため、
    正面カスケードに加えて横顔カスケード(左右両向き)も併用する。
    """
    import cv2

    if frame is None:
        return []
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    # 引きの映像でも顔は画面高さの1/24程度はある想定。小さすぎる検出はノイズ
    min_size = max(40, frame.shape[0] // 24)
    frontal = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    )
    profile = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_profileface.xml"
    )

    def run(cascade, image) -> list[Box]:
        found = cascade.detectMultiScale(
            image, scaleFactor=1.1, minNeighbors=5, minSize=(min_size, min_size)
        )
        return [tuple(int(v) for v in f) for f in found]

    boxes = run(frontal, gray) + run(profile, gray)
    # profilefaceは左向きのみ対応のため、反転画像で右向きも検出する
    width = gray.shape[1]
    boxes += [
        (width - x - w, y, w, h) for x, y, w, h in run(profile, cv2.flip(gray, 1))
    ]
    return _merge_boxes(boxes)


def make_face_plan(samples: list[list[Box]], src_w: int, src_h: int) -> FacePlan:
    """サンプルフレームごとの顔ボックス群からクロップ計画を決める(純関数)。

    - 検出できたサンプルが半数未満なら 'none'(→ blur_padへフォールバック)
    - x中心を1次元クラスタリング(ギャップ>0.2で分割)し、
      少数派クラスタ(誤検出)を捨てる
    - 1クラスタ→'single'(中央値)、2クラスタ以上→'stack'(左右順の中央値2つ)
    - y中心も併せて返す(縦方向のクロップ位置決めに使う)
    """
    n = len(samples)
    detected = [boxes for boxes in samples if boxes]
    if n == 0 or len(detected) * 2 < n:
        return FacePlan(mode="none", centers=())

    points = sorted(
        ((x + w / 2) / src_w, (y + h / 2) / src_h)
        for boxes in samples
        for (x, y, w, h) in boxes
    )
    if not points:
        return FacePlan(mode="none", centers=())

    clusters: list[list[tuple[float, float]]] = [[points[0]]]
    for p in points[1:]:
        if p[0] - clusters[-1][-1][0] > CLUSTER_GAP:
            clusters.append([p])
        else:
            clusters[-1].append(p)
    clusters = [cl for cl in clusters if len(cl) >= MIN_CLUSTER_MEMBERS]
    if not clusters:
        return FacePlan(mode="none", centers=())

    def cx(cl):
        return median(p[0] for p in cl)

    def cy(cl):
        return median(p[1] for p in cl)

    if len(clusters) == 1:
        cl = clusters[0]
        return FacePlan(mode="single", centers=(cx(cl),), centers_y=(cy(cl),))

    # 検出数の多い2クラスタ=主要な2話者(左→右順)
    top2 = sorted(sorted(clusters, key=len, reverse=True)[:2], key=cx)
    return FacePlan(
        mode="stack",
        centers=(cx(top2[0]), cx(top2[1])),
        centers_y=(cy(top2[0]), cy(top2[1])),
    )
