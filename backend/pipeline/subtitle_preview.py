"""プレビュー用の字幕を、書き出しと同じ libass で描く。

以前のプレビューはCSSで字幕を描いていた。同じ「48px」でも、ASSのFontsizeは
行の高さ・CSSのfont-sizeは文字の大きさを指すので、プレビューの方が約1.45倍
大きく見えていた(実測: 書き出し33px/字、プレビュー48px/字)。縁取り・背景の箱・
フォントの代替・行間も別物で、規則を揃えても見た目は揃わなかった(issue #4)。

そこで、書き出しと同じASS(backend/pipeline/subtitle.py の build_ass)を、
書き出しと同じffmpeg(libass)に描かせ、透過画像にして映像へ重ねる。
同じ部品を通すので、文字の大きさ・フォント・縁取り・位置・改行が作りとして一致する。

透過画像の作り方: 黒と白の2枚に同じ字幕を焼き、差から透明度を割り出す。
ffmpegのassフィルタは透明な下地にも描けるが(alpha=1)、縁取りのある字幕では
重ね合わせの計算が合わず、最大58/255の誤差が出た(実測)。黒と白に焼いた結果は
libassが実際に出す画素そのものなので、どんな背景に重ねても書き出しと一致する。
"""

import hashlib
import subprocess
import tempfile
import threading
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from backend.core.ffmpeg import ffmpeg_path
from backend.pipeline import subtitle as subtitle_mod
from backend.pipeline.export import escape_filter_path

# 1件の字幕を描くときの表示区間(秒)。黒と白の2コマ(0秒・1秒)を覆えばよい
RENDER_SPAN = 10.0
RENDER_TIMEOUT = 30


@dataclass(frozen=True)
class PreviewEvent:
    start: float  # 元動画の絶対時刻(秒)
    end: float
    key: str      # 画像の識別子(見た目が同じなら同じ値)
    text: str     # 折り返し済みの文(改行は \n)。画像が出せないときの代替文字


@dataclass(frozen=True)
class RenderJob:
    ass: str
    width: int
    height: int


def single_event_ass(
    event: subtitle_mod.AssEvent,
    style: subtitle_mod.SubtitleStyle,
    speakers: list[str],
) -> str:
    """字幕1件だけを 0〜RENDER_SPAN 秒に出すASS(純関数)。

    話者の色は書き出し範囲全体の並び(speakers)で決める。1件だけから決めると
    全員が1番目の色(白)になる。
    """
    one = subtitle_mod.AssEvent(0.0, RENDER_SPAN, event.text, event.speaker)
    return subtitle_mod.build_ass([one], style, speakers=speakers)


def event_key(ass: str, width: int, height: int) -> str:
    """見た目を決める入力(ASS全文と解像度)のハッシュ(純関数)"""
    digest = hashlib.sha1(f"{width}x{height}\n{ass}".encode("utf-8")).hexdigest()  # noqa: S324
    return digest[:20]


def plan(
    events: list[subtitle_mod.AssEvent],
    style: subtitle_mod.SubtitleStyle,
    clip_start: float = 0.0,
) -> tuple[list[PreviewEvent], dict[str, RenderJob]]:
    """字幕イベント列から、プレビューの時刻表と描画の材料を作る(純関数)。

    events はクリップ相対時刻(書き出しと同じもの)。時刻表は元動画の絶対時刻で返す
    (プレビューは元動画を再生するため)。
    """
    speakers = subtitle_mod.speakers_of(events)
    width, height = style.play_res_x, style.play_res_y
    timeline: list[PreviewEvent] = []
    jobs: dict[str, RenderJob] = {}
    for e in events:
        ass = single_event_ass(e, style, speakers)
        key = event_key(ass, width, height)
        jobs[key] = RenderJob(ass, width, height)
        timeline.append(PreviewEvent(
            start=round(e.start + clip_start, 3),
            end=round(e.end + clip_start, 3),
            key=key,
            text="\n".join(subtitle_mod.wrap_subtitle(e.text, style.max_chars_per_line)),
        ))
    return timeline, jobs


def build_render_cmd(ffmpeg: str, ass_path: Path, width: int, height: int) -> list[str]:
    """黒・白の2コマに字幕を焼いて生の画素で受け取るコマンド(純関数)。

    入力は標準入力から渡す。同梱のffmpegは入力デバイス(lavfi)を無効にして
    ビルドしているので `-f lavfi -i color=…` は使えない。
    """
    return [
        ffmpeg, "-hide_banner", "-loglevel", "error",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{width}x{height}", "-r", "1",
        "-i", "pipe:0",
        "-vf", f"ass='{escape_filter_path(ass_path)}'",
        "-frames:v", "2", "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1",
    ]


def extract_overlay(black: np.ndarray, white: np.ndarray) -> np.ndarray:
    """黒地と白地に焼いた結果(RGB)から、透過画像(RGBA・色は透明度を掛けない値)を作る(純関数)。

    libassの重ね合わせは下地に対して線形: 出力 = P + 下地×T。
    黒地の結果がP、白地との差からT(透過率)が分かる。不透明度 = 1 − T。
    """
    b = black.astype(np.float32)
    w = white.astype(np.float32)
    alpha = 1.0 - np.clip((w - b).mean(axis=2) / 255.0, 0.0, 1.0)
    safe = np.where(alpha > 0, alpha, 1.0)[..., None]
    color = np.clip(b / safe, 0, 255)
    out = np.zeros((*black.shape[:2], 4), dtype=np.uint8)
    out[..., :3] = np.rint(color)
    out[..., 3] = np.rint(alpha * 255)
    return out


def encode_png(rgba: np.ndarray) -> bytes:
    import cv2

    ok, buf = cv2.imencode(".png", cv2.cvtColor(rgba, cv2.COLOR_RGBA2BGRA))
    if not ok:
        raise RuntimeError("字幕のプレビュー画像を作れませんでした(PNGの書き出しに失敗)")
    return buf.tobytes()


def render_overlay(job: RenderJob, ffmpeg: str | None = None) -> np.ndarray:
    """字幕1件を libass で描き、透過画像(RGBA)を返す"""
    exe = ffmpeg or ffmpeg_path()
    if exe is None:
        raise RuntimeError("ffmpeg が見つかりません")
    w, h = job.width, job.height
    frame = w * h * 3
    with tempfile.TemporaryDirectory(prefix="ks-preview-") as work:
        ass_path = Path(work) / "subtitle.ass"
        ass_path.write_text(job.ass, encoding="utf-8")
        # 出力はバイト列(画素)なので文字として読まない
        proc = subprocess.run(
            build_render_cmd(exe, ass_path, w, h),
            input=bytes(frame) + b"\xff" * frame,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=RENDER_TIMEOUT,
        )
    if proc.returncode != 0 or len(proc.stdout) < frame * 2:
        err = proc.stderr.decode("utf-8", errors="replace")[-500:]
        raise RuntimeError(f"字幕のプレビューを描けませんでした(ffmpeg exit {proc.returncode}): {err}")
    pixels = np.frombuffer(proc.stdout[: frame * 2], dtype=np.uint8).reshape(2, h, w, 3)
    return extract_overlay(pixels[0], pixels[1])


class PreviewCache:
    """描画の材料と描いた画像を覚えておく(プロセス内・件数に上限)。

    時刻表を返すときに材料(ASS)を登録し、画像の要求で初めて描く。
    同じ見た目の字幕は1回しか描かない。ffmpegの同時起動は絞る
    (再生中の先読みで何十も同時に走らせない)。
    """

    def __init__(self, max_jobs: int = 20000, max_images: int = 300, workers: int = 2):
        self._jobs: OrderedDict[str, RenderJob] = OrderedDict()
        self._images: OrderedDict[str, bytes] = OrderedDict()
        self._max_jobs = max_jobs
        self._max_images = max_images
        self._lock = threading.Lock()
        self._slots = threading.Semaphore(workers)

    def register(self, jobs: dict[str, RenderJob]) -> None:
        with self._lock:
            for key, job in jobs.items():
                self._jobs[key] = job
                self._jobs.move_to_end(key)
            while len(self._jobs) > self._max_jobs:
                self._jobs.popitem(last=False)

    def knows(self, key: str) -> bool:
        with self._lock:
            return key in self._jobs

    def image(self, key: str, render=None) -> bytes | None:
        """画像(PNG)。材料を知らないキーなら None"""
        with self._lock:
            cached = self._images.get(key)
            if cached is not None:
                self._images.move_to_end(key)
                return cached
            job = self._jobs.get(key)
        if job is None:
            return None
        with self._slots:
            with self._lock:  # 待っている間に別の要求が描き終えていないか
                cached = self._images.get(key)
            if cached is None:
                cached = encode_png((render or render_overlay)(job))
                with self._lock:
                    self._images[key] = cached
                    while len(self._images) > self._max_images:
                        self._images.popitem(last=False)
        return cached

    def clear(self) -> None:
        with self._lock:
            self._jobs.clear()
            self._images.clear()


cache = PreviewCache()
