"""M8: アテンション・クリップ・ジェットカット・書き出しのテスト"""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.engines.llm.base import FakeLLMClient
from backend.jobs import resolve_job
from backend.pipeline.attention import (
    ClipFeatures,
    clip_features,
    combined_score,
    parse_silences,
)
from backend.pipeline.export import build_export_cmd


# ---- 機械特徴(純関数) ----
def _seg(idx, start, end, text, speaker="A", aizuchi=0):
    return {"idx": idx, "start": start, "end": end, "text": text,
            "speaker": speaker, "is_aizuchi": aizuchi}


def test_clip_features_density_and_turns():
    segs = [
        _seg(0, 0, 5, "あ" * 30, "A"),
        _seg(1, 5, 10, "い" * 30, "B"),
        _seg(2, 10, 20, "う" * 20, "A"),
        _seg(3, 20, 30, "うん", "B", aizuchi=1),  # 相槌は密度から除外
    ]
    f = clip_features(segs, 0, 30)
    assert f.duration == 30
    assert f.density_cps == pytest.approx(80 / 30)
    assert f.turns_per_min == pytest.approx(3 / 30 * 60)  # A→B→A→B
    assert f.laugh_count == 0


def test_clip_features_detects_laughter():
    segs = [_seg(0, 0, 10, "それで(笑)みたいな www")]
    assert clip_features(segs, 0, 10).laugh_count == 2


def test_combined_score_adds_reasons():
    f = ClipFeatures(duration=60, density_cps=7.0, turns_per_min=8.0, laugh_count=1)
    score, reasons = combined_score(7, f, target_duration=60)
    assert score == pytest.approx(7 + 0.8 + 0.5 + 0.5 + 0.7)
    assert set(reasons) == {"笑いあり", "テンポが良い", "掛け合い", "目標尺に合う"}


def test_combined_score_penalizes_wrong_duration():
    f = ClipFeatures(duration=200, density_cps=1.0, turns_per_min=0, laugh_count=0)
    score, _ = combined_score(7, f, target_duration=60)
    assert score == pytest.approx(6.0)  # 2倍超は減点


def test_parse_silences():
    stderr = """
[silencedetect @ 0x1] silence_start: 12.5
[silencedetect @ 0x1] silence_end: 13.4 | silence_duration: 0.9
[silencedetect @ 0x1] silence_start: 20.0
[silencedetect @ 0x1] silence_end: 21.0 | silence_duration: 1.0
"""
    assert parse_silences(stderr, offset=100.0) == [(112.5, 113.4), (120.0, 121.0)]


# ---- 書き出しコマンド(中抜き) ----
def test_keep_intervals_merges_and_complements():
    from backend.pipeline.export import keep_intervals

    # 重なり・順不同の中抜きを整理して補集合(残す区間)を返す
    keeps = keep_intervals(60.0, [(20.0, 22.0), (5.0, 6.5), (21.0, 23.0)])
    assert keeps == [(0.0, 5.0), (6.5, 20.0), (23.0, 60.0)]
    # 先頭からの中抜き・全区間中抜きも壊れない
    assert keep_intervals(10.0, [(0.0, 3.0)]) == [(3.0, 10.0)]
    assert keep_intervals(10.0, [(0.0, 10.0)]) == []
    assert keep_intervals(10.0, []) == [(0.0, 10.0)]


def test_build_export_cmd_with_cuts_uses_trim_concat():
    """select式はffmpegバージョン依存の不具合があるためtrim+concat方式を使う"""
    cmd = build_export_cmd(
        Path("in.mov"), Path("out.mp4"), 10.0, 70.0,
        ass_path=Path("s.ass"), use_nvenc=False,
        cuts=[(5.0, 6.5), (20.0, 22.0)],
    )
    graph = cmd[cmd.index("-filter_complex") + 1]
    assert graph.index("ass=") < graph.index("trim=")  # 字幕を焼いてからカット
    assert "split=3" in graph and "asplit=3" in graph   # 残す区間は3つ
    assert "trim=start=0.000:end=5.000" in graph
    assert "trim=start=6.500:end=20.000" in graph
    assert "trim=start=22.000:end=60.000" in graph
    assert "concat=n=3:v=1:a=1" in graph
    assert "-map" in cmd


def test_build_export_cmd_ignores_empty_cuts():
    cmd = build_export_cmd(Path("i"), Path("o"), 0, 10, cuts=[], use_nvenc=False)
    assert "-filter_complex" not in cmd


# ---- API統合(FakeLLM) ----
@pytest.fixture
def client(tmp_path, monkeypatch):
    from backend.core import config

    monkeypatch.setattr(config.settings, "db_path", tmp_path / "m8.db")
    from backend.app import app

    with TestClient(app) as c:
        yield c
    resolve_job.set_client_factory(None)


@pytest.fixture
def media(client, tmp_path):
    pid = client.post("/api/projects", json={"name": "p"}).json()["id"]
    f = tmp_path / "a.wav"
    f.write_bytes(b"x")
    mid = client.post(f"/api/projects/{pid}/media", json={"path": str(f)}).json()["id"]
    db = client.app.state.db
    texts = [
        ("はやまる", "去年ハッカソンに出たんですよ", 0),
        ("高田さん", "へえ、どんな内容だったんですか", 0),
        ("はやまる", "それがすごく面白くて(笑)", 0),
        ("高田さん", "うん", 1),
        ("はやまる", "AIで古着屋の接客をやってみたんです", 0),
        ("高田さん", "面白い、結果はどうだったんですか", 0),
    ]
    for idx, (speaker, text, aizuchi) in enumerate(texts):
        db.execute(
            "INSERT INTO segments (media_id, idx, start, end, text, original_text,"
            " speaker, is_aizuchi) VALUES (?,?,?,?,?,?,?,?)",
            (mid, idx, idx * 5.0, idx * 5.0 + 4.0, f"{speaker}: {text}",
             f"{speaker}: {text}", speaker, aizuchi),
        )
    db.commit()
    return {"project_id": pid, "media_id": mid}


def use_fake(responses):
    fake = FakeLLMClient(responses=responses)
    resolve_job.set_client_factory(lambda: fake)
    return fake


def run_job(client, media_id, job_type, params=None):
    job = client.post(
        f"/api/media/{media_id}/jobs", json={"type": job_type, "params": params or {}}
    ).json()
    return client.app.state.jobs.wait(job["id"], timeout=30)


ATTENTION_RESPONSE = {"candidates": [
    {"start_line": 1, "end_line": 5, "title": "AI接客ハッカソン",
     "hook": "古着屋×AIの意外な結果", "score": 8, "reasons": ["完結した話題"]},
]}


def test_attention_creates_suggested_clips(client, media):
    mid = media["media_id"]
    use_fake([ATTENTION_RESPONSE])
    job = run_job(client, mid, "attention", {"target_duration": 30})
    assert job["status"] == "completed", job["error"]

    clips = client.get(f"/api/media/{mid}/clips").json()
    assert len(clips) == 1
    c = clips[0]
    assert c["status"] == "suggested"
    assert c["title"] == "AI接客ハッカソン"
    # 行番号は相槌を除いた発話に振られる: 5行目=元idx5のセグメント(end=29.0)
    assert c["start"] == 0.0 and c["end"] == 29.0
    assert "完結した話題" in c["score_reasons"]
    assert "笑いあり" in c["score_reasons"]           # 機械特徴が合成されている
    assert c["score"] > 8


def test_attention_uses_brief_in_prompt(client, media):
    mid = media["media_id"]
    client.patch(f"/api/media/{mid}/brief", json={"theme": "AI活用の対談", "people": "", "notes": ""})
    fake = use_fake([ATTENTION_RESPONSE])
    run_job(client, mid, "attention", {})
    assert "AI活用の対談" in fake.calls[0][0]


def test_clip_crud_and_range_validation(client, media):
    mid = media["media_id"]
    clip = client.post(f"/api/media/{mid}/clips", json={"start": 5, "end": 20}).json()
    assert clip["status"] == "draft"
    assert clip["subtitle_position"] == "bottom"
    assert clip["subtitle_offset_y"] == 0

    r = client.patch(f"/api/clips/{clip['id']}", json={"end": 25, "title": "手動クリップ"})
    assert r.json()["end"] == 25 and r.json()["title"] == "手動クリップ"

    r2 = client.patch(f"/api/clips/{clip['id']}", json={"subtitle_position": "top"})
    assert r2.json()["subtitle_position"] == "top"
    r3 = client.patch(f"/api/clips/{clip['id']}", json={"subtitle_offset_y": -24})
    assert r3.json()["subtitle_offset_y"] == -24

    assert client.patch(f"/api/clips/{clip['id']}", json={"end": 3}).status_code == 400
    assert client.delete(f"/api/clips/{clip['id']}").status_code == 200
    assert client.get(f"/api/media/{mid}/clips").json() == []


def test_jetcut_proposes_aizuchi_cuts_and_toggle(client, media):
    """ffmpegが使えない偽メディアでも相槌の中抜きは提案される"""
    mid = media["media_id"]
    clip = client.post(f"/api/media/{mid}/clips", json={"start": 0, "end": 30}).json()
    r = client.post(f"/api/clips/{clip['id']}/jetcut")
    assert r.status_code == 200
    cuts = r.json()["cuts"]
    aizuchi_cuts = [c for c in cuts if c["source"] == "aizuchi"]
    assert len(aizuchi_cuts) == 1
    assert aizuchi_cuts[0]["start"] == 15.0  # 「うん」の区間

    cut_id = aizuchi_cuts[0]["id"]
    assert client.patch(f"/api/clip_cuts/{cut_id}?active=false").json()["active"] == 0


def test_clip_update_drops_out_of_range_cuts(client, media):
    mid = media["media_id"]
    clip = client.post(f"/api/media/{mid}/clips", json={"start": 0, "end": 30}).json()
    client.post(f"/api/clips/{clip['id']}/jetcut")
    r = client.patch(f"/api/clips/{clip['id']}", json={"end": 10})  # 相槌(15-19)が範囲外に
    assert all(c["end"] <= 10 for c in r.json()["cuts"])


def test_clip_resolve_uses_extra_instruction(client, media):
    mid = media["media_id"]
    clip = client.post(f"/api/media/{mid}/clips", json={"start": 10, "end": 30}).json()
    fake = use_fake([{"edits": []}])
    r = client.post(f"/api/clips/{clip['id']}/resolve")
    assert r.status_code == 200
    client.app.state.jobs.wait(r.json()["job_id"], timeout=30)

    system = fake.calls[0][0]
    assert "切り抜き動画として単体で公開" in system  # 自己完結化の追加指示が入る


def test_clip_meta_generation(client, media):
    mid = media["media_id"]
    clip = client.post(f"/api/media/{mid}/clips", json={"start": 0, "end": 30}).json()
    use_fake([{
        "title": "古着屋×AIの挑戦",
        "hooks": ["AIに接客させたら?", "意外な結末", "古着屋の実験"],
        "description": "古着屋でAI接客を試した話。",
        "hashtags": ["#AI", "#古着"],
    }])
    job = run_job(client, mid, "clip_meta", {"clip_id": clip["id"]})
    assert job["status"] == "completed", job["error"]

    c = [x for x in client.get(f"/api/media/{mid}/clips").json() if x["id"] == clip["id"]][0]
    assert c["meta"]["hooks"] == ["AIに接客させたら?", "意外な結末", "古着屋の実験"]
    assert c["title"] == "古着屋×AIの挑戦"      # 空だったので自動設定
    assert c["hook_text"] == "AIに接客させたら?"


def test_clip_export_enqueues_job_with_cuts(client, media):
    mid = media["media_id"]
    clip = client.post(f"/api/media/{mid}/clips", json={"start": 0, "end": 30}).json()
    client.post(f"/api/clips/{clip['id']}/jetcut")

    r = client.post(f"/api/clips/{clip['id']}/export")
    assert r.status_code == 200
    job = client.app.state.jobs.get(r.json()["job_id"])
    params = json.loads(job["params_json"])
    assert params["clip_id"] == clip["id"]
    assert len(params["cuts"]) == 1  # 有効な中抜きが渡っている
    assert params["subtitle_position"] == "bottom"
    assert params["subtitle_offset_y"] == 0
    # 偽メディアなのでffmpegは失敗するが、パラメータの受け渡しが検証できれば良い
