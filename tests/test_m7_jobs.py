"""M7: フィラージョブ・ジャッジジョブ・書き出し・概要注入の統合テスト"""

import json

import pytest
from fastapi.testclient import TestClient

from backend.engines.llm.base import FakeLLMClient
from backend.jobs import resolve_job
from backend.pipeline.export import build_export_cmd
from backend.pipeline.judge import JudgeInput, score, select_subtitles


@pytest.fixture
def client(tmp_path, monkeypatch):
    from backend.core import config

    monkeypatch.setattr(config.settings, "db_path", tmp_path / "m7.db")
    from backend.app import app

    with TestClient(app) as c:
        yield c
    resolve_job.set_client_factory(None)


SEGS = [
    # (text, words, filler_candidates)
    ("そのー、人と話すときに", [{"start": 0.0, "end": 0.6, "text": "そのー", "probability": 0.4}]),
    ("なんか、いい感じですね", [{"start": 2.0, "end": 2.2, "text": "なんか", "probability": 0.9}]),
    ("その半導体の話です", []),
]


@pytest.fixture
def media(client, tmp_path):
    pid = client.post("/api/projects", json={"name": "p"}).json()["id"]
    f = tmp_path / "a.wav"
    f.write_bytes(b"x")
    mid = client.post(f"/api/projects/{pid}/media", json={"path": str(f)}).json()["id"]
    db = client.app.state.db
    from backend.pipeline.filler import analyze_line

    for idx, (text, words) in enumerate(SEGS):
        db.execute(
            "INSERT INTO segments (media_id, idx, start, end, text, original_text,"
            " words_json, filler_candidates_json, asr_confidence)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (mid, idx, idx * 3.0, idx * 3.0 + 2.0, text, text,
             json.dumps(words), json.dumps(analyze_line(text, words)), -0.2 - idx * 0.3),
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


# ---- フィラージョブ(2段構成) ----
def test_filler_weak_applies_likely_without_llm(client, media):
    """Whisper段階で filler_likely と判定済みの語はLLMなしで適用される"""
    mid = media["media_id"]
    fake = use_fake([])  # LLMは呼ばれないはず
    job = run_job(client, mid, "filler", {"level": "weak"})
    assert job["status"] == "completed", job["error"]
    assert fake.calls == []

    edits = client.get(f"/api/media/{mid}/edits").json()
    # そのー(長音+読点+低確率)は filler_likely → 適用済み
    assert any(e["kind"] == "filler" and e["original"] == "その"
               and e["status"] == "applied" for e in edits)


def test_filler_strong_sends_ambiguous_to_llm_and_user(client, media):
    """曖昧な候補はLLMへ。LLMも曖昧と言えばユーザーへの質問になる"""
    mid = media["media_id"]
    fake = use_fake([{"fillers": [
        {"line": 2, "word": "なんか", "judgment": "ambiguous"},
    ]}])
    job = run_job(client, mid, "filler", {"level": "strong"})
    assert job["status"] == "completed", job["error"]
    assert len(fake.calls) == 1
    assert "なんか" in fake.calls[0][1]  # 曖昧候補がLLMに渡っている

    qs = client.get(f"/api/media/{mid}/questions").json()
    filler_qs = [q for q in qs if q["kind"] == "filler"]
    assert len(filler_qs) == 1
    assert "なんか" in filler_qs[0]["question_text"]
    assert "フィラー(字幕から削除)" in filler_qs[0]["candidates"]


def test_filler_question_answer_delete(client, media):
    mid = media["media_id"]
    use_fake([{"fillers": [{"line": 2, "word": "なんか", "judgment": "ambiguous"}]}])
    run_job(client, mid, "filler", {"level": "strong"})
    qid = [q for q in client.get(f"/api/media/{mid}/questions").json()
           if q["kind"] == "filler"][0]["id"]

    r = client.post(f"/api/questions/{qid}/answer", json={"text": "フィラー(字幕から削除)"})
    assert r.status_code == 200 and r.json()["segments_changed"] == 1

    edits = client.get(f"/api/media/{mid}/edits").json()
    assert any(e["kind"] == "filler" and e["original"] == "なんか"
               and e["created_by"] == "user" for e in edits)
    # トランスクリプト本文は変わらない(字幕生成時にのみ除去される)
    segs = client.get(f"/api/media/{mid}/segments").json()
    assert "なんか" in segs[1]["text"]


def test_filler_question_answer_keep(client, media):
    mid = media["media_id"]
    use_fake([{"fillers": [{"line": 2, "word": "なんか", "judgment": "ambiguous"}]}])
    run_job(client, mid, "filler", {"level": "strong"})
    qid = [q for q in client.get(f"/api/media/{mid}/questions").json()
           if q["kind"] == "filler"][0]["id"]

    r = client.post(f"/api/questions/{qid}/answer", json={"text": "意味がある(残す)"})
    assert r.json()["segments_changed"] == 0
    assert not any(e["original"] == "なんか"
                   for e in client.get(f"/api/media/{mid}/edits").json())


def test_filler_demonstrative_likely_is_untouched(client, media):
    """「その半導体」のような連体詞用法は候補にすら入らない"""
    mid = media["media_id"]
    use_fake([{"fillers": []}])
    run_job(client, mid, "filler", {"level": "strong"})
    edits = client.get(f"/api/media/{mid}/edits").json()
    seg3_id = client.get(f"/api/media/{mid}/segments").json()[2]["id"]
    assert not any(e["segment_id"] == seg3_id for e in edits)


# ---- 字幕採用ジャッジ ----
def test_judge_score_ordering():
    hard = JudgeInput(idx=0, text="専門用語だらけの話", duration=1.0,
                      confidence=-0.9, has_term=True, llm_important=True)
    easy = JudgeInput(idx=1, text="はい", duration=1.0, confidence=-0.05,
                      has_term=False, llm_important=False)
    assert score(hard) > score(easy)


def test_select_subtitles_respects_rate():
    inputs = [
        JudgeInput(idx=i, text="あ" * 10, duration=1.0, confidence=-0.1 * i,
                   has_term=False) for i in range(10)
    ]
    selected = select_subtitles(inputs, rate=0.3)
    assert len(selected) == 3
    assert 9 in selected  # 最も confidence が低い(聞き取りにくい)ものが選ばれる


def test_judge_job_marks_segments_and_preserves_user_choice(client, media):
    mid = media["media_id"]
    db = client.app.state.db
    segs = client.get(f"/api/media/{mid}/segments").json()
    # ユーザーが手動で非表示にした行は保護される
    client.patch(f"/api/segments/{segs[0]['id']}", json={"subtitle_show": "user_hide"})

    use_fake([{"important_lines": [3]}])
    job = run_job(client, mid, "judge_subtitles", {"rate": 0.34})
    assert job["status"] == "completed", job["error"]

    segs = client.get(f"/api/media/{mid}/segments").json()
    assert segs[0]["subtitle_show"] == "user_hide"          # 保護
    shows = [s["subtitle_show"] for s in segs[1:]]
    assert "auto_show" in shows and "auto_hide" in shows    # 採用/非採用が分かれる
    reasons = db.execute(
        "SELECT subtitle_reasons_json FROM segments WHERE media_id=? AND idx=2", (mid,)
    ).fetchone()[0]
    assert "重要な発言" in reasons


# ---- 概要(ブリーフ) ----
def test_brief_roundtrip_and_prompt_injection(client, media):
    mid = media["media_id"]
    r = client.patch(f"/api/media/{mid}/brief", json={
        "theme": "AIと人の関わりについての対談",
        "people": "はやまる(古着店主)と高田さん(エッセイスト)",
        "notes": "「箱ストア」ははやまるの店名",
    })
    assert r.status_code == 200
    assert client.get(f"/api/media/{mid}/brief").json()["theme"].startswith("AIと人")

    fake = use_fake([{"edits": []}])
    run_job(client, mid, "resolve", {})
    system = fake.calls[0][0]
    assert "AIと人の関わりについての対談" in system
    assert "古着店主" in system
    assert "箱ストア" in system


# ---- 書き出しコマンド ----
def test_build_export_cmd_with_subtitles(tmp_path):
    cmd = build_export_cmd(
        tmp_path / "in.mov", tmp_path / "out.mp4", 10.0, 70.0,
        ass_path=tmp_path / "sub.ass", use_nvenc=False,
    )
    joined = " ".join(cmd)
    assert "-ss 10.000" in joined
    assert "-t 60.000" in joined
    assert "ass=" in joined
    assert "libx264" in joined


def test_build_export_cmd_nvenc():
    from pathlib import Path

    cmd = build_export_cmd(Path("in.mov"), Path("out.mp4"), 0, 10, use_nvenc=True)
    assert "h264_nvenc" in cmd
    assert not any("ass=" in c for c in cmd)  # 字幕なしならフィルタもなし
