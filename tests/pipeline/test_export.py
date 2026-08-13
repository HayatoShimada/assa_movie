"""M14: 書き出しジョブへの向き変換統合テスト(ffmpeg実行はモック)。

方式の優先順位(クリップ上書き > プロジェクト設定 > グローバル)と、
ASSのPlayResが最終出力解像度になることを検証する。
"""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def captured(monkeypatch):
    """ffmpeg実行を捕捉し、組み立てられたコマンドを記録する"""
    from backend.pipeline import export as export_mod

    calls: list[list[str]] = []
    monkeypatch.setattr(export_mod, "detect_encoder", lambda: "libx264")
    monkeypatch.setattr(
        export_mod, "run_export",
        lambda cmd, duration, progress=None, timeout=0: calls.append(cmd),
    )
    from backend.api import clips as clips_api

    monkeypatch.setattr(clips_api, "_require_ffmpeg", lambda: None)
    return calls


def _make_media(client, tmp_path, *, output_orientation, width, height, settings=None):
    pid = client.post("/api/projects", json={
        "name": "p", "output_orientation": output_orientation,
        "settings": settings or {},
    }).json()["id"]
    f = tmp_path / f"src_{pid}.mov"
    f.write_bytes(b"x")
    mid = client.post(f"/api/projects/{pid}/media", json={"path": str(f)}).json()["id"]
    db = client.app.state.db
    db.execute("UPDATE media SET width=?, height=?, duration=60 WHERE id=?",
               (width, height, mid))
    db.commit()
    return pid, mid


def _export(client, mid, clip_body):
    clip = client.post(f"/api/media/{mid}/clips", json=clip_body).json()
    r = client.post(f"/api/clips/{clip['id']}/export")
    assert r.status_code == 200, r.text
    job_id = r.json()["job_id"]
    job = client.app.state.jobs.wait(job_id, timeout=30)
    assert job["status"] == "completed", job["error"]
    return clip


def test_portrait_project_gets_layout_filter(client, tmp_path, captured):
    _, mid = _make_media(
        client, tmp_path, output_orientation="portrait", width=1920, height=1080,
        settings={"convert_method": "crop"},
    )
    _export(client, mid, {"start": 0, "end": 10})
    cmd = captured[-1]
    graph = cmd[cmd.index("-filter_complex") + 1]
    assert "crop=608:1080:656:0,scale=1080:1920" in graph  # プロジェクト設定のcrop
    assert graph.index("crop=") < graph.index("ass=")      # 変換→字幕の順


def test_clip_override_beats_project_setting(client, tmp_path, captured):
    _, mid = _make_media(
        client, tmp_path, output_orientation="portrait", width=1920, height=1080,
        settings={"convert_method": "crop"},
    )
    clip = client.post(f"/api/media/{mid}/clips", json={"start": 0, "end": 10}).json()
    client.patch(f"/api/clips/{clip['id']}", json={"convert_method": "blur_pad"})
    r = client.post(f"/api/clips/{clip['id']}/export")
    job = client.app.state.jobs.wait(r.json()["job_id"], timeout=30)
    assert job["status"] == "completed", job["error"]
    graph = captured[-1][captured[-1].index("-filter_complex") + 1]
    assert "gblur=" in graph  # クリップ上書きが勝つ


def test_crop_x_slider_moves_window(client, tmp_path, captured):
    _, mid = _make_media(
        client, tmp_path, output_orientation="portrait", width=1920, height=1080,
        settings={"convert_method": "crop"},
    )
    clip = client.post(f"/api/media/{mid}/clips", json={"start": 0, "end": 10}).json()
    client.patch(f"/api/clips/{clip['id']}", json={"crop_x": 0.0})
    r = client.post(f"/api/clips/{clip['id']}/export")
    client.app.state.jobs.wait(r.json()["job_id"], timeout=30)
    graph = captured[-1][captured[-1].index("-filter_complex") + 1]
    assert "crop=608:1080:0:0" in graph  # 左端


def test_landscape_project_same_source_is_passthrough(client, tmp_path, captured):
    _, mid = _make_media(
        client, tmp_path, output_orientation="landscape", width=1920, height=1080,
    )
    _export(client, mid, {"start": 0, "end": 10})
    cmd = captured[-1]
    assert "-filter_complex" not in cmd  # 変換不要(字幕もないので-vfもなし)


def test_ass_playres_matches_output_resolution(client, tmp_path, captured):
    _, mid = _make_media(
        client, tmp_path, output_orientation="portrait", width=1920, height=1080,
        settings={"convert_method": "crop"},
    )
    db = client.app.state.db
    db.execute(
        "INSERT INTO segments (media_id, idx, start, end, text, original_text)"
        " VALUES (?,0,1,3,'こんにちは','こんにちは')", (mid,),
    )
    db.commit()
    _export(client, mid, {"start": 0, "end": 10})
    cmd = captured[-1]
    graph = cmd[cmd.index("-filter_complex") + 1]
    assert "ass=" in graph
    # ASSファイルの中身: PlayResが縦出力(1080×1920)・フォントは幅比率で27px
    import re
    from pathlib import Path

    m = re.search(r"ass='([^']+)'", graph)
    ass_text = Path(m.group(1).replace("\\:", ":")).read_text(encoding="utf-8")
    assert "PlayResX: 1080" in ass_text
    assert "PlayResY: 1920" in ass_text
    assert ",27," in ass_text.splitlines()[
        next(i for i, l in enumerate(ass_text.splitlines()) if l.startswith("Style: Default"))
    ]


def test_face_method_falls_back_without_faces(client, tmp_path, captured, monkeypatch):
    from backend.jobs import export_job as ej

    # ダミー動画ではフレーム抽出できない → 検出ゼロ → blur_padフォールバック
    monkeypatch.setattr(ej.face_mod, "sample_frames", lambda path, times: [None] * 5)
    _, mid = _make_media(
        client, tmp_path, output_orientation="portrait", width=1920, height=1080,
        settings={"convert_method": "face"},
    )
    _export(client, mid, {"start": 0, "end": 10})
    graph = captured[-1][captured[-1].index("-filter_complex") + 1]
    assert "gblur=" in graph
