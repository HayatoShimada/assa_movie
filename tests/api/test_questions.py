"""M4-9: 固有名詞の質問機能のテスト

題材は実際の文字起こしで発生した誤認識(反動体 → 半導体)。
音は合っているが漢字が誤るケースは機械では確定できないのでユーザーに聞く。
"""

import pytest
from fastapi.testclient import TestClient

from tests.helpers import create_media, insert_segments, use_fake

TEXTS = [
    "はやまる: NVIDIAって会社はですね",
    "はやまる: 反動体を作ってる会社なんですよ",
    "高田さん: 反動体って何ですか",
    "はやまる: 反動体っていうのはコンピュータの部品です",
]


@pytest.fixture
def media(client, tmp_path):
    ids = create_media(client, tmp_path)
    insert_segments(
        client.app.state.db, ids["media_id"], [{"text": t} for t in TEXTS]
    )
    return ids




def run_extract(client, media_id):
    job = client.post(
        f"/api/media/{media_id}/jobs", json={"type": "extract_terms", "params": {}}
    ).json()
    return client.app.state.jobs.wait(job["id"], timeout=30)


TERM_RESPONSE = {"questions": [
    {"term": "反動体", "reason": "半導体の誤認識と思われます", "candidates": ["半導体"]}
]}


def test_extract_terms_creates_question_with_count(client, media):
    mid = media["media_id"]
    use_fake([TERM_RESPONSE])
    job = run_extract(client, mid)
    assert job["status"] == "completed", job["error"]

    qs = client.get(f"/api/media/{mid}/questions").json()
    assert len(qs) == 1
    q = qs[0]
    assert "反動体" in q["question_text"]
    assert "3回出現" in q["question_text"]   # 実際の出現回数を数える
    assert "半導体" in q["question_text"]
    assert q["candidates"] == ["半導体"]
    assert q["status"] == "open"


def test_extract_terms_ignores_hallucinated_terms(client, media):
    """本文に存在しない語をLLMが挙げても質問にしない"""
    mid = media["media_id"]
    use_fake([{"questions": [
        {"term": "存在しない語", "reason": "でっちあげ", "candidates": ["x"]}
    ]}])
    run_extract(client, mid)
    assert client.get(f"/api/media/{mid}/questions").json() == []


def test_extract_terms_is_idempotent(client, media):
    mid = media["media_id"]
    use_fake([TERM_RESPONSE])
    run_extract(client, mid)
    use_fake([TERM_RESPONSE])
    run_extract(client, mid)
    assert len(client.get(f"/api/media/{mid}/questions").json()) == 1  # 重複登録しない


def test_answer_replaces_all_occurrences_and_registers_glossary(client, media):
    mid, pid = media["media_id"], media["project_id"]
    use_fake([TERM_RESPONSE])
    run_extract(client, mid)
    qid = client.get(f"/api/media/{mid}/questions").json()[0]["id"]

    r = client.post(f"/api/questions/{qid}/answer", json={"text": "半導体"})
    assert r.status_code == 200
    assert r.json()["segments_changed"] == 3   # 3セグメントに出現

    segs = client.get(f"/api/media/{mid}/segments").json()
    assert all("反動体" not in s["text"] for s in segs)
    assert "半導体を作ってる会社" in segs[1]["text"]
    assert segs[1]["original_text"] == TEXTS[1]  # 原文は保持

    glossary = client.get(f"/api/projects/{pid}/glossary").json()
    assert [g["term"] for g in glossary] == ["半導体"]

    assert client.get(f"/api/media/{mid}/questions").json() == []  # openが無くなる


def test_answer_records_edits_for_audit(client, media):
    mid = media["media_id"]
    use_fake([TERM_RESPONSE])
    run_extract(client, mid)
    qid = client.get(f"/api/media/{mid}/questions").json()[0]["id"]
    client.post(f"/api/questions/{qid}/answer", json={"text": "半導体"})

    edits = client.get(f"/api/media/{mid}/edits").json()
    assert len(edits) == 3
    assert all(e["kind"] == "term" and e["status"] == "applied" for e in edits)
    assert all(e["created_by"] == "user" for e in edits)


def test_dismiss_question(client, media):
    mid = media["media_id"]
    use_fake([TERM_RESPONSE])
    run_extract(client, mid)
    qid = client.get(f"/api/media/{mid}/questions").json()[0]["id"]

    assert client.post(f"/api/questions/{qid}/dismiss").json()["status"] == "dismissed"
    assert client.get(f"/api/media/{mid}/questions").json() == []
    assert len(client.get(f"/api/media/{mid}/questions?status=dismissed").json()) == 1


def test_answer_unknown_question_404(client):
    assert client.post("/api/questions/999/answer", json={"text": "x"}).status_code == 404


def test_glossary_from_answer_reaches_pronoun_prompt(client, media):
    """質問への回答が用語集に入り、指示語解決のプロンプトにも効く"""
    mid = media["media_id"]
    use_fake([TERM_RESPONSE])
    run_extract(client, mid)
    qid = client.get(f"/api/media/{mid}/questions").json()[0]["id"]
    client.post(f"/api/questions/{qid}/answer", json={"text": "半導体"})

    fake = use_fake([{"edits": []}])
    job = client.post(
        f"/api/media/{mid}/jobs", json={"type": "resolve", "params": {}}
    ).json()
    client.app.state.jobs.wait(job["id"], timeout=30)
    assert "半導体" in fake.calls[0][0]
