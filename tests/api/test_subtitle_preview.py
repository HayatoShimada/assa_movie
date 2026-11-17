"""プレビュー用の字幕API(書き出しと同じ材料で時刻表を作り、libassの画像を返す)。

issue #4: プレビューと書き出しは別々に字幕を組み立てていた。フィラー除去・
表示時間の延長・話者の色・字幕位置の既定が片方にしか効かず、見た目が違った。
"""

import numpy as np
import pytest

from backend.jobs import export_job
from backend.pipeline import subtitle as sub
from backend.pipeline import subtitle_preview as pv
from tests.helpers import create_media, insert_segments


@pytest.fixture
def media(client, tmp_path):
    ids = create_media(client, tmp_path)
    db = client.app.state.db
    db.execute("UPDATE media SET width=1920, height=1080, duration=60 WHERE id=?",
               (ids["media_id"],))
    insert_segments(db, ids["media_id"], [
        {"text": "こんにちは", "speaker": "はやまる", "start": 1.0, "end": 1.4},
        {"text": "うん", "speaker": "ゲスト", "start": 2.0, "end": 2.3, "is_aizuchi": 1},
        {"text": "えーと今日は古着屋とAIの話をしていきたいと思います",
         "speaker": "ゲスト", "start": 5.0, "end": 9.0},
        {"text": "採用されなかった行", "speaker": "はやまる", "start": 12.0, "end": 13.0,
         "subtitle_show": "auto_hide"},
        {"text": "よろしくお願いします", "speaker": "はやまる", "start": 20.0, "end": 22.0},
    ])
    pv.cache.clear()
    yield ids
    pv.cache.clear()


def _get(client, media, **params):
    r = client.get(f"/api/media/{media['media_id']}/subtitle-preview", params=params)
    assert r.status_code == 200, r.text
    return r.json()


def test_時刻表は書き出しと同じ字幕だけを同じ時間で出す(client, media):
    body = _get(client, media)
    assert (body["width"], body["height"]) == (1920, 1080)
    texts = [e["text"].replace("\n", "") for e in body["events"]]
    # 相槌と非採用は出ない(書き出しの segments_to_events と同じ)
    assert texts == ["こんにちは", "えーと今日は古着屋とAIの話をしていきたいと思います",
                     "よろしくお願いします"]
    # 短い発話は読み切れる長さまで延びる(1.0〜1.4秒 → 最短1秒)。以前のプレビューは
    # 発話の長さのままで、書き出しより早く消えていた
    first = body["events"][0]
    assert (first["start"], first["end"]) == (1.0, 2.0)


def test_フィラー除去が効く(client, media):
    """安全群のフィラー(えーと)は弱モード以上で書き出しから消える。プレビューも同じ"""
    client.patch("/api/settings", json={"filler_level": "weak"})
    texts = [e["text"].replace("\n", "") for e in _get(client, media)["events"]]
    assert texts[1] == "今日は古着屋とAIの話をしていきたいと思います"


def test_書き出しのASSと同じ材料で描く(client, media):
    """各字幕の描画材料(ASS)は、書き出しのASSと同じスタイル行・同じ本文を持つ"""
    body = _get(client, media)
    db = client.app.state.db
    from backend.core.project_settings import resolve_settings

    s = resolve_settings(db, media_id=media["media_id"])
    export_ass = export_job._build_subtitles(
        db, media["media_id"], s, {}, 0.0, 60.0, 1920, 1080
    )
    export_styles = [l for l in export_ass.splitlines() if l.startswith("Style:")]
    export_texts = [l.split(",", 9)[9] for l in export_ass.splitlines()
                    if l.startswith("Dialogue:")]
    export_style_names = [l.split(",")[3] for l in export_ass.splitlines()
                          if l.startswith("Dialogue:")]
    for event, text, style_name in zip(body["events"], export_texts, export_style_names):
        ass = pv.cache._jobs[event["key"]].ass
        assert [l for l in ass.splitlines() if l.startswith("Style:")] == export_styles
        dialogue = next(l for l in ass.splitlines() if l.startswith("Dialogue:"))
        assert dialogue.split(",", 9)[9] == text
        assert dialogue.split(",")[3] == style_name


def test_位置を渡さなければ設定の字幕位置を使う(client, media):
    """秒指定の書き出しも同じ規則にした(以前は「下・ずらし0」に決め打ちで、
    設定を上にしていてもプレビューだけ上・書き出しは下になっていた)"""
    default = _get(client, media)["events"][0]["key"]
    client.patch("/api/settings", json={"subtitle_position": "top"})
    by_setting = _get(client, media)["events"][0]["key"]
    by_param = _get(client, media, position="top")["events"][0]["key"]
    assert by_setting != default
    assert by_setting == by_param
    # クリップの値は設定より優先
    assert _get(client, media, position="bottom")["events"][0]["key"] == default


def test_秒指定の書き出しも設定の字幕位置で焼く(client, media):
    from backend.core.project_settings import resolve_settings

    client.patch("/api/settings", json={"subtitle_position": "top", "subtitle_offset_y": 30})
    s = resolve_settings(client.app.state.db, media_id=media["media_id"])
    style = export_job.subtitle_style(s, {}, 1920, 1080)
    assert style == sub.scaled_style(s, 1920, 1080, "top", 30)
    # クリップが 0 を持っていれば 0 が勝つ(未指定とは区別する)
    clip = export_job.subtitle_style(
        s, {"subtitle_position": "bottom", "subtitle_offset_y": 0}, 1920, 1080
    )
    assert clip == sub.scaled_style(s, 1920, 1080, "bottom", 0)


def test_クリップの範囲を渡すと話者の色がその範囲で決まる(client, media):
    """書き出しは「書き出す範囲に出てくる話者」に順に色を割り当てる"""
    whole = _get(client, media)
    clip = _get(client, media, start=4.0, end=10.0)  # ゲストしか出てこない
    assert [e["text"] for e in clip["events"]] == [whole["events"][1]["text"]]
    assert clip["events"][0]["start"] == 5.0, "時刻は元動画の絶対時刻"
    assert clip["events"][0]["key"] != whole["events"][1]["key"]


def test_縦向きのプロジェクトは縦の解像度(client, tmp_path):
    pid = client.post("/api/projects", json={"name": "縦", "output_orientation": "portrait"}).json()["id"]
    src = tmp_path / "v.mov"
    src.write_bytes(b"x")
    mid = client.post(f"/api/projects/{pid}/media", json={"path": str(src)}).json()["id"]
    db = client.app.state.db
    db.execute("UPDATE media SET width=1920, height=1080 WHERE id=?", (mid,))
    db.commit()
    body = client.get(f"/api/media/{mid}/subtitle-preview").json()
    assert (body["width"], body["height"]) == (1080, 1920)


def test_画像はPNGで長くキャッシュさせる(client, media, monkeypatch):
    monkeypatch.setattr(pv, "render_overlay", lambda job, ffmpeg=None: np.zeros((2, 2, 4), np.uint8))
    key = _get(client, media)["events"][0]["key"]
    r = client.get(f"/api/media/{media['media_id']}/subtitle-preview/{key}.png")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "image/png"
    assert "immutable" in r.headers["cache-control"]
    assert r.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_再起動で材料を忘れていても同じ条件なら描ける(client, media, monkeypatch):
    monkeypatch.setattr(pv, "render_overlay", lambda job, ffmpeg=None: np.zeros((2, 2, 4), np.uint8))
    key = _get(client, media, position="top")["events"][0]["key"]
    pv.cache.clear()
    url = f"/api/media/{media['media_id']}/subtitle-preview/{key}.png"
    assert client.get(url, params={"position": "top"}).status_code == 200


def test_もう無い字幕の画像は404(client, media):
    r = client.get(f"/api/media/{media['media_id']}/subtitle-preview/{'0' * 20}.png")
    assert r.status_code == 404


def test_描けなかったら理由つきで503(client, media, monkeypatch):
    def fail(job, ffmpeg=None):
        raise RuntimeError("ffmpeg が見つかりません")

    monkeypatch.setattr(pv, "render_overlay", fail)
    key = _get(client, media)["events"][0]["key"]
    r = client.get(f"/api/media/{media['media_id']}/subtitle-preview/{key}.png")
    assert r.status_code == 503
    assert "ffmpeg" in r.json()["detail"]


def test_ffmpegが無ければ時刻表だけ返して理由を伝える(client, media, monkeypatch):
    from backend.api import preview

    monkeypatch.setattr(preview, "ffmpeg_path", lambda: None)
    body = _get(client, media)
    assert body["available"] is False
    assert "ffmpeg" in body["reason"]
    assert len(body["events"]) == 3, "代替文字で出せるよう時刻表は返す"


def test_存在しないメディアは404(client):
    assert client.get("/api/media/99999/subtitle-preview").status_code == 404


def test_位置の値が正しくなければ400(client, media):
    r = client.get(f"/api/media/{media['media_id']}/subtitle-preview", params={"position": "left"})
    assert r.status_code == 400
