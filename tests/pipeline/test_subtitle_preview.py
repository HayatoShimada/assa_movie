"""プレビューの字幕を書き出しと同じ libass で描く(backend/pipeline/subtitle_preview.py)。

issue #4: プレビュー(CSS)と書き出し(libass)で字幕の大きさ・縁取り・位置が違っていた。
同じASSを同じffmpegに描かせて映像へ重ねるので、作りとして一致する。
ここでは (1) 材料の組み立て(純関数) と (2) 実際にffmpegで描いた画像が
「直接焼き込んだ結果」と画素で一致すること、を確かめる。
"""

import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from backend.pipeline import subtitle as sub
from backend.pipeline import subtitle_preview as pv


def _settings(**over):
    base = dict(
        subtitle_font_family="Noto Sans JP", subtitle_font_size=48,
        subtitle_max_chars_per_line=15, subtitle_text_color="#FFFFFF",
        subtitle_speaker_colors=True, subtitle_bg="none",
        subtitle_bg_color="#000000", subtitle_bg_opacity=0.5,
    )
    return SimpleNamespace(**{**base, **over})


def _style(w=1920, h=1080, position="bottom", offset=0, **over):
    return sub.scaled_style(_settings(**over), w, h, position, offset)


EVENTS = [
    sub.AssEvent(0.0, 2.0, "こんにちは", "はやまる"),
    sub.AssEvent(2.0, 4.0, "今日は古着屋とAIの話をしていきたいと思います", "ゲスト"),
    sub.AssEvent(4.0, 6.0, "こんにちは", "はやまる"),
]


# ---- 材料の組み立て(純関数) ----

def test_時刻表は元動画の絶対時刻で返す():
    """イベントはクリップ相対(書き出しと同じ)。プレビューは元動画を再生する"""
    timeline, _ = pv.plan(EVENTS, _style(), clip_start=100.0)
    assert [(e.start, e.end) for e in timeline] == [(100.0, 102.0), (102.0, 104.0), (104.0, 106.0)]


def test_代替文字は書き出しと同じ折り返し():
    timeline, _ = pv.plan(EVENTS, _style())
    assert timeline[1].text == "\n".join(sub.wrap_subtitle(EVENTS[1].text, 15))
    assert "\n" in timeline[1].text


def test_見た目が同じ字幕は同じ画像を使う():
    timeline, jobs = pv.plan(EVENTS, _style())
    assert timeline[0].key == timeline[2].key
    assert timeline[0].key != timeline[1].key
    assert set(jobs) == {timeline[0].key, timeline[1].key}


@pytest.mark.parametrize(
    "name, a, b",
    [
        ("文字の大きさ", {}, {"subtitle_font_size": 64}),
        ("フォント", {}, {"subtitle_font_family": "IPAGothic"}),
        ("背景", {}, {"subtitle_bg": "box"}),
        ("文字色", {"subtitle_speaker_colors": False},
         {"subtitle_speaker_colors": False, "subtitle_text_color": "#FF0000"}),
        ("折り返し幅", {}, {"subtitle_max_chars_per_line": 8}),
    ],
)
def test_見た目が変わる設定はキーが変わる(name, a, b):
    """キーが変わらないと、設定を変えても前の画像が出続ける"""
    ka = pv.plan(EVENTS, _style(**a))[0][1].key
    kb = pv.plan(EVENTS, _style(**b))[0][1].key
    assert ka != kb, name


def test_位置と解像度でもキーが変わる():
    base = pv.plan(EVENTS, _style())[0][0].key
    assert pv.plan(EVENTS, _style(position="top"))[0][0].key != base
    assert pv.plan(EVENTS, _style(offset=-60))[0][0].key != base
    assert pv.plan(EVENTS, _style(w=1080, h=1920))[0][0].key != base


def test_話者の色は書き出し範囲全体の並びで決める():
    """1件ずつ描いても、書き出しと同じ色(話者ごとのスタイル)になる"""
    _, jobs = pv.plan(EVENTS, _style())
    timeline, _ = pv.plan(EVENTS, _style())
    full = sub.build_ass(EVENTS, _style())
    # 書き出しのASSで「はやまる」に付くスタイル名を、1件だけのASSも使っている
    speaker_style = next(
        line.split(",")[3] for line in full.splitlines()
        if line.startswith("Dialogue:") and ",はやまる," in line
    )
    one = jobs[timeline[0].key].ass
    dialogue = next(line for line in one.splitlines() if line.startswith("Dialogue:"))
    assert dialogue.split(",")[3] == speaker_style
    # スタイルの定義(色)も書き出しのASSと同じ行
    styles = lambda text: [l for l in text.splitlines() if l.startswith("Style:")]  # noqa: E731
    assert styles(one) == styles(full)


def test_1件だけのASSは字幕を0秒から出す():
    ass = pv.single_event_ass(EVENTS[0], _style(), ["はやまる"])
    dialogue = [line for line in ass.splitlines() if line.startswith("Dialogue:")]
    assert len(dialogue) == 1
    assert dialogue[0].startswith("Dialogue: 0,0:00:00.00,0:00:10.00,")


def test_描画コマンドは標準入力から画素を受ける(tmp_path):
    """同梱のffmpegは入力デバイス(lavfi)を無効にしてある。-f lavfi は使えない"""
    cmd = pv.build_render_cmd("ffmpeg", tmp_path / "s.ass", 1080, 1920)
    assert "lavfi" not in cmd
    assert cmd[cmd.index("-i") + 1] == "pipe:0"
    assert cmd[cmd.index("-s") + 1] == "1080x1920"
    assert cmd[cmd.index("-vf") + 1].startswith("ass='")


# ---- 黒地と白地から透過画像を割り出す(純関数) ----

def _px(*rgb):
    return np.array([[rgb]], dtype=np.uint8)


@pytest.mark.parametrize(
    "name, black, white, expected",
    [
        ("何も描かれていない", (0, 0, 0), (255, 255, 255), (0, 0, 0, 0)),
        ("不透明な白い字", (255, 255, 255), (255, 255, 255), (255, 255, 255, 255)),
        ("不透明な黒い縁", (0, 0, 0), (0, 0, 0), (0, 0, 0, 255)),
        ("不透明な黄色", (255, 215, 0), (255, 215, 0), (255, 215, 0, 255)),
        # 半透明の黒い箱(不透明度50%): 黒地では0、白地では半分の明るさ
        ("半透明の黒", (0, 0, 0), (128, 128, 128), (0, 0, 0, 127)),
        # 半透明の白(50%): 黒地で128、白地で255
        ("半透明の白", (128, 128, 128), (255, 255, 255), (255, 255, 255, 128)),
    ],
)
def test_extract_overlay(name, black, white, expected):
    got = pv.extract_overlay(_px(*black), _px(*white))[0, 0]
    assert np.abs(got.astype(int) - np.array(expected)).max() <= 1, f"{name}: {got}"


def test_extract_overlay_は重ね直すと元に戻る():
    """どんな背景に重ねても、libassが直接描いた結果と同じになること(±1階調)"""
    rng = np.random.default_rng(0)
    alpha = rng.random((8, 8, 1))
    color = rng.integers(0, 256, (8, 8, 3)).astype(float)
    on = lambda bg: np.rint(color * alpha + bg * (1 - alpha)).astype(np.uint8)  # noqa: E731
    out = pv.extract_overlay(on(0.0), on(255.0)).astype(float)
    a = out[..., 3:4] / 255
    for bg in (0.0, 90.0, 255.0):
        diff = np.abs(out[..., :3] * a + bg * (1 - a) - on(bg))
        assert diff.max() <= 2.0, (bg, diff.max())


# ---- キャッシュ ----

def test_同じ字幕は1回しか描かない():
    cache = pv.PreviewCache()
    cache.register({"k": pv.RenderJob("ass", 4, 2)})
    calls = []

    def render(job):
        calls.append(job)
        return np.zeros((2, 4, 4), dtype=np.uint8)

    first = cache.image("k", render)
    assert cache.image("k", render) == first
    assert len(calls) == 1
    assert first[:8] == b"\x89PNG\r\n\x1a\n"


def test_知らないキーはNone():
    assert pv.PreviewCache().image("nope") is None


def test_画像は上限を超えたら古いものから捨てる():
    cache = pv.PreviewCache(max_images=2)
    cache.register({k: pv.RenderJob(k, 1, 1) for k in "abc"})
    calls = []

    def render(job):
        calls.append(job.ass)
        return np.zeros((1, 1, 4), dtype=np.uint8)

    for k in "abc":
        cache.image(k, render)
    cache.image("a", render)  # 捨てられたので描き直す
    assert calls == ["a", "b", "c", "a"]


# ---- 実際にffmpeg(libass)で描く ----

def _ffmpeg_with_libass() -> str | None:
    exe = shutil.which("ffmpeg")
    if not exe:
        return None
    out = subprocess.run([exe, "-hide_banner", "-filters"], capture_output=True)
    return exe if b" ass " in out.stdout else None


FFMPEG = _ffmpeg_with_libass()
needs_ffmpeg = pytest.mark.skipif(FFMPEG is None, reason="libass入りのffmpegが要る")


def _burn_direct(ass: str, w: int, h: int, bg: tuple[int, int, int], tmp_path: Path) -> np.ndarray:
    """書き出しと同じやり方(映像へ直接焼く)で1コマ作る"""
    ass_path = tmp_path / "direct.ass"
    ass_path.write_text(ass, encoding="utf-8")
    frame = bytes(bg) * (w * h)
    proc = subprocess.run(
        pv.build_render_cmd(FFMPEG, ass_path, w, h)[:-7]
        + ["-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"],
        input=frame, capture_output=True, check=True,
    )
    return np.frombuffer(proc.stdout, dtype=np.uint8).reshape(h, w, 3)


@needs_ffmpeg
@pytest.mark.parametrize(
    "name, w, h, over",
    [
        ("縁取り・横", 1920, 1080, {}),
        ("背景の箱・横", 1920, 1080, {"subtitle_bg": "box"}),
        ("縁取り・縦", 1080, 1920, {"subtitle_font_size": 96}),
        ("話者の色なし・赤", 1920, 1080,
         {"subtitle_speaker_colors": False, "subtitle_text_color": "#FF3300"}),
    ],
)
def test_プレビューの画像を重ねると書き出しと同じ画素になる(name, w, h, over, tmp_path):
    """透過画像を背景に重ねた結果 = 同じASSをその背景へ直接焼いた結果(±2階調)"""
    style = _style(w=w, h=h, **over)
    timeline, jobs = pv.plan(EVENTS, style)
    job = jobs[timeline[1].key]  # 2行に折り返す長い字幕
    overlay = pv.render_overlay(job, FFMPEG).astype(float)
    assert overlay.shape == (h, w, 4)
    assert (overlay[..., 3] > 0).sum() > 1000, "字幕が描かれている"

    a = overlay[..., 3:4] / 255
    for bg in ((0, 0, 255), (90, 140, 60), (255, 255, 255)):
        direct = _burn_direct(job.ass, w, h, bg, tmp_path).astype(float)
        composed = overlay[..., :3] * a + np.array(bg, dtype=float) * (1 - a)
        diff = np.abs(composed - direct).max(axis=2)
        assert diff.max() <= 2.0, f"{name} 背景{bg}: 最大差 {diff.max()}"


@needs_ffmpeg
def test_位置を変えると描かれる場所が変わる():
    def rows(position, offset=0):
        _, jobs = pv.plan(EVENTS[:1], _style(position=position, offset=offset))
        overlay = pv.render_overlay(next(iter(jobs.values())), FFMPEG)
        ys = np.where(overlay[..., 3] > 0)[0]
        return int(ys.min()), int(ys.max())

    top, bottom, center = rows("top"), rows("bottom"), rows("center")
    assert top[1] < center[0] < center[1] < bottom[0]
    # +で下へ、-で上へ(クリップ画面の微調整と同じ向き)
    assert rows("bottom", -100)[1] < bottom[1]
