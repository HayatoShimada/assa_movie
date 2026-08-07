"""M14: 顔検出の後処理(顔ボックス→クロップ計画)のテスト。検出自体は実行しない。"""

import pytest

from backend.pipeline.face import make_face_plan

W, H = 1920, 1080


def _box(cx_norm: float, size: int = 200) -> tuple[int, int, int, int]:
    """正規化x中心からピクセルの顔ボックス(x, y, w, h)を作る"""
    x = int(cx_norm * W - size / 2)
    return (x, 300, size, size)


def test_single_person():
    samples = [[_box(0.3)], [_box(0.31)], [_box(0.29)], [_box(0.3)], [_box(0.3)]]
    plan = make_face_plan(samples, W, H)
    assert plan.mode == "single"
    assert plan.centers[0] == pytest.approx(0.3, abs=0.02)


def test_two_person_interview():
    samples = [
        [_box(0.25), _box(0.75)],
        [_box(0.26), _box(0.74)],
        [_box(0.25), _box(0.76)],
        [_box(0.24), _box(0.75)],
        [_box(0.25), _box(0.75)],
    ]
    plan = make_face_plan(samples, W, H)
    assert plan.mode == "stack"
    assert len(plan.centers) == 2
    assert plan.centers[0] < plan.centers[1]  # 左→右順
    assert plan.centers[0] == pytest.approx(0.25, abs=0.02)
    assert plan.centers[1] == pytest.approx(0.75, abs=0.02)


def test_no_faces_detected():
    plan = make_face_plan([[], [], [], [], []], W, H)
    assert plan.mode == "none"


def test_mostly_empty_samples_is_none():
    # 5サンプル中1つしか検出できない → 信頼できないのでnone
    plan = make_face_plan([[], [_box(0.5)], [], [], []], W, H)
    assert plan.mode == "none"


def test_outlier_detection_is_robust():
    # 誤検出(外れ値)が混ざっても中央値ベースで安定する
    samples = [
        [_box(0.3)],
        [_box(0.3), _box(0.95, size=40)],  # 小さな誤検出
        [_box(0.31)],
        [_box(0.29)],
        [_box(0.3)],
    ]
    plan = make_face_plan(samples, W, H)
    assert plan.mode == "single"
    assert plan.centers[0] == pytest.approx(0.3, abs=0.03)


def test_close_faces_are_single_cluster():
    # 2つの顔でもx中心が近ければ(距離<0.2)クラスタを分けない
    samples = [[_box(0.45), _box(0.55)]] * 5
    plan = make_face_plan(samples, W, H)
    assert plan.mode == "single"
