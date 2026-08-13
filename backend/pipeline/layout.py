"""向き変換(縦↔横)のffmpegフィルタ生成。すべて純関数。

生成するフィルタは "[0:v]...[vlay]" 形式のグラフ断片で、
build_export_cmd(pipeline/export.py)がこの契約で連結する。
"""

from dataclasses import dataclass

# プロジェクトの向き→出力解像度
OUTPUT_RES: dict[str, tuple[int, int]] = {
    "landscape": (1920, 1080),
    "portrait": (1080, 1920),
}

CONVERT_METHODS = ("crop", "blur_pad", "face")


@dataclass(frozen=True)
class FacePlan:
    """顔検出の後処理結果(pipeline/face.py が生成。JSONシリアライズ可能)"""

    mode: str                    # 'single' | 'stack' | 'none'
    centers: tuple[float, ...]   # 正規化x中心(0..1)。stackは左→右順で2つ
    centers_y: tuple[float, ...] = ()  # 正規化y中心(縦方向のクロップ位置決めに使う)


def _even(v: float) -> int:
    """ffmpegのエンコーダ要件(偶数解像度)に合わせて丸める"""
    return max(2, int(round(v / 2) * 2))


def _crop_window(
    src_w: int, src_h: int, out_w: int, out_h: int, pos: float
) -> tuple[int, int, int, int]:
    """出力アスペクトに合わせたクロップ窓 (cw, ch, x, y) を計算する。

    pos(0..1)は「切り落とす軸」に沿った位置。横→縦なら水平位置、縦→横なら垂直位置。
    """
    pos = max(0.0, min(1.0, pos))
    out_ar = out_w / out_h
    if src_w / src_h > out_ar:
        # 横長すぎ → 幅を切る(高さは全部使う)
        ch = src_h - (src_h % 2)
        cw = _even(ch * out_ar)
        if cw > src_w:
            cw = src_w - (src_w % 2)
        x = int(round((src_w - cw) * pos))
        y = (src_h - ch) // 2
    else:
        # 縦長すぎ → 高さを切る(幅は全部使う)
        cw = src_w - (src_w % 2)
        ch = _even(cw / out_ar)
        if ch > src_h:
            ch = src_h - (src_h % 2)
        x = (src_w - cw) // 2
        y = int(round((src_h - ch) * pos))
    return cw, ch, x, y


def _crop_filter(src_w, src_h, out_w, out_h, pos: float) -> str:
    cw, ch, x, y = _crop_window(src_w, src_h, out_w, out_h, pos)
    return f"[0:v]crop={cw}:{ch}:{x}:{y},scale={out_w}:{out_h}[vlay]"


def _blur_pad_filter(out_w: int, out_h: int) -> str:
    """元映像を切らずに全体表示し、余白をぼかし拡大背景で埋める。

    背景のぼかしは gblur(ガウスぼかし)を使う。boxblur はffmpegの
    GPL専用フィルタで、同梱しているLGPLビルドには入っていない
    (指定すると `No such filter: 'boxblur'` で書き出しが落ちる。実測)。
    gblur は LGPL で同じ用途に使える。sigma=20 が boxblur の
    luma_radius=40:luma_power=2 とおおよそ同じ見た目。
    """
    return (
        "[0:v]split[bg][fg];"
        f"[bg]scale={out_w}:{out_h}:force_original_aspect_ratio=increase,"
        f"crop={out_w}:{out_h},gblur=sigma=20[bgb];"
        f"[fg]scale={out_w}:{out_h}:force_original_aspect_ratio=decrease[fgs];"
        "[bgb][fgs]overlay=(W-w)/2:(H-h)/2[vlay]"
    )


def _stack_filter(
    src_w: int, src_h: int, out_w: int, out_h: int, face_plan: FacePlan
) -> str:
    """2人対談の上下分割: 各話者の顔を中心に切り出して縦に積む"""
    half_h = _even(out_h / 2)
    pane_ar = out_w / half_h
    ch = src_h - (src_h % 2)
    cw = _even(ch * pane_ar)
    if cw > src_w:
        # 幅が足りない(縦長ソース等)場合は幅基準にして高さを縮める
        cw = src_w - (src_w % 2)
        ch = _even(cw / pane_ar)
    centers_y = face_plan.centers_y or (0.5, 0.5)
    chains = ["[0:v]split[a][b]"]
    for label, out_label, cx, cy in zip(
        "ab", ("ta", "tb"), face_plan.centers[:2], centers_y[:2]
    ):
        x = max(0, min(src_w - cw, int(round(cx * src_w - cw / 2))))
        y = max(0, min(src_h - ch, int(round(cy * src_h - ch / 2))))
        chains.append(
            f"[{label}]crop={cw}:{ch}:{x}:{y},scale={out_w}:{half_h}[{out_label}]"
        )
    chains.append("[ta][tb]vstack[vlay]")
    return ";".join(chains)


def build_layout_filter(
    src_w: int,
    src_h: int,
    out_w: int,
    out_h: int,
    method: str,
    crop_x: float = 0.5,
    face_plan: FacePlan | None = None,
) -> str | None:
    """ソース解像度と出力解像度から向き変換フィルタを組み立てる。

    - 解像度が同一ならNone(パススルー)、同アスペクトならscaleのみ
    - crop:     位置調整可能なクロップ(crop_xは切り落とす軸に沿った0..1)
    - blur_pad: 全体表示+ぼかし拡大背景
    - face:     顔検出結果で crop(1人)/上下分割(2人)。検出失敗は blur_pad
    """
    if (src_w, src_h) == (out_w, out_h):
        return None
    if src_w * out_h == src_h * out_w:  # 同アスペクト → 拡縮のみ
        return f"[0:v]scale={out_w}:{out_h}[vlay]"

    if method == "face":
        if face_plan is None or face_plan.mode == "none" or not face_plan.centers:
            return _blur_pad_filter(out_w, out_h)  # 検出できなければ安全側へ
        if face_plan.mode == "stack" and len(face_plan.centers) >= 2:
            return _stack_filter(src_w, src_h, out_w, out_h, face_plan)
        # クロップ窓の中心を顔の中心に合わせる(切り落とす軸: 横長すぎ→x、縦長すぎ→y)。
        # crop_x(0..1)は「移動量に対する比率」なので、顔中心座標から換算する
        cw, ch, _, _ = _crop_window(src_w, src_h, out_w, out_h, 0.5)
        if src_w / src_h > out_w / out_h:
            travel = src_w - cw
            pos = 0.5 if travel <= 0 else (face_plan.centers[0] * src_w - cw / 2) / travel
        else:
            cy = face_plan.centers_y[0] if face_plan.centers_y else 0.5
            travel = src_h - ch
            pos = 0.5 if travel <= 0 else (cy * src_h - ch / 2) / travel
        return _crop_filter(src_w, src_h, out_w, out_h, pos)
    if method == "crop":
        return _crop_filter(src_w, src_h, out_w, out_h, crop_x)
    return _blur_pad_filter(out_w, out_h)
