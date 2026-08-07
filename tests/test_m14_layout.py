"""M14: 向き変換フィルタ生成(純関数)のテーブル駆動テスト。ffmpeg実行は不要。"""

import pytest

from backend.pipeline.layout import (
    OUTPUT_RES,
    FacePlan,
    build_layout_filter,
)


def test_output_res_presets():
    assert OUTPUT_RES["landscape"] == (1920, 1080)
    assert OUTPUT_RES["portrait"] == (1080, 1920)


# ---- 同一アスペクト ----

def test_same_resolution_is_passthrough():
    assert build_layout_filter(1920, 1080, 1920, 1080, "crop") is None


def test_same_aspect_different_size_scales_only():
    f = build_layout_filter(3840, 2160, 1920, 1080, "crop")
    assert f == "[0:v]scale=1920:1080[vlay]"


# ---- 横→縦 crop ----

def test_landscape_to_portrait_center_crop():
    f = build_layout_filter(1920, 1080, 1080, 1920, "crop", crop_x=0.5)
    # 高さ1080を使い、幅は 1080*(1080/1920)=607.5→偶数丸め608。中央: (1920-608)/2=656
    assert f == "[0:v]crop=608:1080:656:0,scale=1080:1920[vlay]"


@pytest.mark.parametrize(
    "crop_x, expected_x",
    [
        (0.0, 0),        # 左端
        (1.0, 1312),     # 右端(1920-608)
        (0.25, 328),     # 中間 (1920-608)*0.25
        (-5.0, 0),       # クランプ
        (5.0, 1312),     # クランプ
    ],
)
def test_crop_x_position_table(crop_x, expected_x):
    f = build_layout_filter(1920, 1080, 1080, 1920, "crop", crop_x=crop_x)
    assert f"crop=608:1080:{expected_x}:0" in f


# ---- 横→縦 blur_pad ----

def test_landscape_to_portrait_blur_pad():
    f = build_layout_filter(1920, 1080, 1080, 1920, "blur_pad")
    # 背景: cover→crop→ぼかし、前景: contain、中央に重ねる
    assert f.startswith("[0:v]split[bg][fg];")
    assert "boxblur=" in f
    assert "overlay=(W-w)/2:(H-h)/2" in f
    assert f.endswith("[vlay]")


# ---- 縦→横 ----

def test_portrait_to_landscape_crop():
    # 縦ソース(1080×1920)→横(1920×1080): 幅1080を使い高さを切る
    f = build_layout_filter(1080, 1920, 1920, 1080, "crop", crop_x=0.5)
    # 高さ = 1080*(1080/1920)=607.5→608。縦方向中央: (1920-608)/2=656
    assert f == "[0:v]crop=1080:608:0:656,scale=1920:1080[vlay]"


def test_portrait_to_landscape_blur_pad():
    f = build_layout_filter(1080, 1920, 1920, 1080, "blur_pad")
    assert "boxblur=" in f and f.endswith("[vlay]")


# ---- face ----

def test_face_single_uses_face_center():
    plan = FacePlan(mode="single", centers=(0.25,))
    f = build_layout_filter(1920, 1080, 1080, 1920, "face", face_plan=plan)
    # crop_x=0.25相当: (1920-608)*0.25=328
    assert "crop=608:1080:328:0" in f


def test_face_stack_two_speakers():
    plan = FacePlan(mode="stack", centers=(0.25, 0.75))
    f = build_layout_filter(1920, 1080, 1080, 1920, "face", face_plan=plan)
    # 上下2分割: 各段 1080×960 のクロップを縦に積む
    assert "split[a][b]" in f
    assert "vstack" in f
    assert f.endswith("[vlay]")


def test_face_none_falls_back_to_blur_pad():
    plan = FacePlan(mode="none", centers=())
    f = build_layout_filter(1920, 1080, 1080, 1920, "face", face_plan=plan)
    assert "boxblur=" in f  # 顔が見つからなければ安全なぼかし背景


def test_face_without_plan_falls_back_to_blur_pad():
    f = build_layout_filter(1920, 1080, 1080, 1920, "face", face_plan=None)
    assert "boxblur=" in f


# ---- 奇数ソースの偶数丸め ----

def test_odd_source_produces_even_crop():
    f = build_layout_filter(1919, 1079, 1080, 1920, "crop")
    import re

    m = re.search(r"crop=(\d+):(\d+):", f)
    assert m and int(m.group(1)) % 2 == 0 and int(m.group(2)) % 2 == 0
