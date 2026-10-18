"""テンプレート(書き出しの向き)ごとのプロジェクト既定値。

字幕のpx値は1920×1080基準で保存し、フォントは幅比率で換算する(CLAUDE.md)。
規則は変えないので、幅1080の縦動画では同じ値が0.56倍になり、既定の48では
27pxと小さすぎる。しかも下余白40は画面最下部で、ShortsのUIと重なる。
だから縦向きに書き出すテンプレートは、作成時にプロジェクトの差分として
縦動画向けの値を持たせる(既存プロジェクトの保存値は変えない)。
"""

import pytest

from backend.core.project_settings import ORIENTATION_DEFAULTS, with_orientation_defaults

PORTRAIT = ORIENTATION_DEFAULTS["portrait"]


def test_縦向きの既定値は字幕を大きく下端から離す():
    assert PORTRAIT["subtitle_font_size"] > 48
    # 縦1080幅で約54px(横1920幅の既定48pxと同程度の見た目)
    assert round(PORTRAIT["subtitle_font_size"] * 1080 / 1920) >= 50
    # 下配置で、微調整の上限(-120)まで上げる
    assert PORTRAIT["subtitle_position"] == "bottom"
    assert PORTRAIT["subtitle_offset_y"] == -120


def test_横向きは既定値を足さない():
    assert ORIENTATION_DEFAULTS["landscape"] == {}


@pytest.mark.parametrize(
    "name, overrides, new, old, expected",
    [
        ("作成: 横→横は差分そのまま", {"filler_level": "weak"}, "landscape", None,
         {"filler_level": "weak"}),
        ("作成: 縦は既定値を足す", {}, "portrait", None, dict(PORTRAIT)),
        ("作成: 利用者が決めた値は上書きしない", {"subtitle_font_size": 60}, "portrait", None,
         {**PORTRAIT, "subtitle_font_size": 60}),
        ("変更なし(縦→縦)なら何も足さない", {}, "portrait", "portrait", {}),
        ("横→縦に切り替えたら足す", {"filler_level": "weak"}, "portrait", "landscape",
         {**PORTRAIT, "filler_level": "weak"}),
        ("縦→横に戻したら縦の既定値のままの項目を外す", dict(PORTRAIT), "landscape", "portrait",
         {}),
        ("縦→横でも利用者が変えた値は残す", {**PORTRAIT, "subtitle_font_size": 70},
         "landscape", "portrait", {"subtitle_font_size": 70}),
    ],
)
def test_with_orientation_defaults(name, overrides, new, old, expected):
    before = dict(overrides)
    assert with_orientation_defaults(overrides, new, old) == expected, name
    assert overrides == before, "引数を書き換えない(純関数)"


# ---- APIでの適用 ----

def test_縦向きプロジェクトは作成時に縦向けの字幕既定値を持つ(client):
    body = client.post("/api/projects", json={
        "name": "縦", "input_orientation": "landscape", "output_orientation": "portrait",
    }).json()
    for key, value in PORTRAIT.items():
        assert body["settings"][key] == value


def test_縦向きプロジェクトで作るクリップは縦向けの字幕位置を引き継ぐ(client, tmp_path):
    pid = client.post("/api/projects", json={
        "name": "縦", "output_orientation": "portrait",
    }).json()["id"]
    src = tmp_path / "v.mov"
    src.write_bytes(b"x")
    mid = client.post(f"/api/projects/{pid}/media", json={"path": str(src)}).json()["id"]
    clip = client.post(f"/api/media/{mid}/clips", json={"start": 0, "end": 10}).json()
    assert clip["subtitle_position"] == "bottom"
    assert clip["subtitle_offset_y"] == PORTRAIT["subtitle_offset_y"]


def test_既存プロジェクトの保存値は名前の変更などで変わらない(client):
    db = client.app.state.db
    # 旧版で作った縦プロジェクト(差分なし)を直接作る
    cur = db.execute(
        "INSERT INTO projects (name, input_orientation, output_orientation)"
        " VALUES ('旧', 'landscape', 'portrait')"
    )
    db.commit()
    pid = cur.lastrowid
    assert client.get(f"/api/projects/{pid}").json()["settings"] == {}
    r = client.patch(f"/api/projects/{pid}", json={"name": "旧(改名)"})
    assert r.json()["settings"] == {}
    # 向きを送っても同じ向きなら変えない
    r = client.patch(f"/api/projects/{pid}", json={"output_orientation": "portrait"})
    assert r.json()["settings"] == {}


def test_テンプレートを横から縦へ切り替えると縦向けの既定値が入る(client):
    pid = client.post("/api/projects", json={
        "name": "p", "settings": {"filler_level": "weak"},
    }).json()["id"]
    r = client.patch(f"/api/projects/{pid}", json={"output_orientation": "portrait"})
    assert r.json()["settings"] == {**PORTRAIT, "filler_level": "weak"}

    # 横へ戻すと、縦の既定値のまま触っていない項目は外れる
    r = client.patch(f"/api/projects/{pid}", json={"output_orientation": "landscape"})
    assert r.json()["settings"] == {"filler_level": "weak"}
