"""組み立てるffmpegフィルタグラフが、同梱ffmpegにあるフィルタだけで出来ていること。

許可リストは tests/fixtures/ffmpeg_filters.txt(実機検証スクリプトと共有)。
GPL専用フィルタの名前を並べて弾く方式では、書き忘れたフィルタや
引数なしの使い方(`,eq,` など)を見逃していた。
"""

import itertools
import re
from pathlib import Path

import pytest

from backend.api.clips import SILENCE_MIN_DURATION, SILENCE_NOISE_DB
from backend.pipeline.export import build_export_cmd
from backend.pipeline.layout import FacePlan, build_layout_filter

ALLOWED = frozenset(
    line.strip()
    for line in (Path(__file__).parents[1] / "fixtures" / "ffmpeg_filters.txt")
    .read_text(encoding="utf-8").splitlines()
    if line.strip() and not line.startswith("#")
)


def filter_names(graph: str) -> set[str]:
    """フィルタグラフ文字列から使っているフィルタ名を取り出す(純関数)。

    `[in]name=args[out]` / `name,name2=args` のどちらの書き方も拾う。
    引数内の `'...'`(assのパス)は先に取り除く。
    """
    graph = re.sub(r"'(?:\\.|[^'\\])*'", "''", graph)
    names = set()
    for chain in graph.split(";"):
        for part in chain.split(","):
            part = re.sub(r"\[[^\]]*\]", "", part).strip()
            if part:
                names.add(part.split("=", 1)[0])
    return names


@pytest.mark.parametrize("graph, expected", [
    ("[0:v]split[bg][fg];[bg]scale=1:2,crop=1:2,gblur=sigma=33[bgb]",
     {"split", "scale", "crop", "gblur"}),
    ("[ta][tb]vstack[vlay]", {"vstack"}),
    ("ass='/tmp/a\\'b,c.ass',format=nv12,hwupload", {"ass", "format", "hwupload"}),
    ("[0:v]eq,boxblur[o]", {"eq", "boxblur"}),  # 引数なしの書き方も拾う
])
def test_filter_names(graph, expected):
    assert filter_names(graph) == expected


def _layouts():
    faces = [
        None,
        FacePlan(mode="single", centers=(0.5,)),
        FacePlan(mode="stack", centers=(0.3, 0.7), centers_y=(0.4, 0.6)),
    ]
    sizes = [(1920, 1080, 1080, 1920), (1080, 1920, 1920, 1080), (1920, 1080, 1920, 1080)]
    out = [None]
    for (sw, sh, ow, oh), method, face in itertools.product(
        sizes, ["crop", "blur_pad", "face"], faces
    ):
        out.append(build_layout_filter(sw, sh, ow, oh, method, face_plan=face))
    return out


def _graphs(cmd: list[str]) -> list[str]:
    return [cmd[i + 1] for i, a in enumerate(cmd) if a in ("-filter_complex", "-vf", "-af")]


@pytest.mark.parametrize("encoder", ["libx264", "h264_vaapi"])
@pytest.mark.parametrize("cuts", [None, [(2.0, 3.0)], [(1.0, 2.0), (4.0, 5.0)]])
@pytest.mark.parametrize("with_ass", [False, True])
def test_書き出しのフィルタは同梱ffmpegにあるものだけ(encoder, cuts, with_ass, tmp_path):
    for layout in _layouts():
        cmd = build_export_cmd(
            tmp_path / "in.mov", tmp_path / "out.mp4", 0.0, 10.0,
            ass_path=(tmp_path / "s.ass") if with_ass else None,
            encoder=encoder, cuts=cuts, layout_filter=layout,
        )
        for graph in _graphs(cmd):
            unknown = filter_names(graph) - ALLOWED
            assert not unknown, f"許可リストに無いフィルタ {unknown}: {graph}"


def test_無音検出のフィルタも許可リストにある():
    graph = f"silencedetect=noise={SILENCE_NOISE_DB}dB:d={SILENCE_MIN_DURATION}"
    assert filter_names(graph) <= ALLOWED
