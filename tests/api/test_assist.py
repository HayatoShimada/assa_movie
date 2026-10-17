"""M6: 対話アシストAPIのテスト(FakeLLM)"""

import pytest
from fastapi.testclient import TestClient

from tests.helpers import use_fake

TEXTS = [
    "はやまる: 去年ハッカソンに出たんですよ",
    "はやまる: それがすごく良くて",
]


@pytest.fixture
def seg_ids(client, tmp_path):
    pid = client.post("/api/projects", json={"name": "p"}).json()["id"]
    f = tmp_path / "a.wav"
    f.write_bytes(b"x")
    mid = client.post(f"/api/projects/{pid}/media", json={"path": str(f)}).json()["id"]
    db = client.app.state.db
    for idx, text in enumerate(TEXTS):
        db.execute(
            "INSERT INTO segments (media_id, idx, start, end, text, original_text)"
            " VALUES (?,?,?,?,?,?)", (mid, idx, idx, idx + 1, text, text)
        )
    db.commit()
    rows = db.execute("SELECT id FROM segments WHERE media_id=? ORDER BY idx", (mid,))
    return {"media_id": mid, "project_id": pid, "ids": [r["id"] for r in rows]}




def test_assist_creates_proposed_edit(client, seg_ids):
    use_fake([{
        "reply": "『それ』はハッカソンを指すと解釈して提案しました。",
        "edits": [{"original": "それ", "replacement": "去年のハッカソン",
                   "referent": "去年のハッカソン"}],
        "instruction_suggestion": "",
    }])
    r = client.post(f"/api/segments/{seg_ids['ids'][1]}/assist",
                    json={"message": "このそれはハッカソンのこと"})
    assert r.status_code == 200
    body = r.json()
    assert "ハッカソン" in body["reply"]
    assert len(body["edits"]) == 1
    assert body["edits"][0]["status"] == "proposed"
    assert body["edits"][0]["created_by"] == "assist"
    assert body["instruction_suggestion"] is None

    # 通常のレビューAPIで承認できる
    eid = body["edits"][0]["id"]
    accepted = client.post(f"/api/edits/{eid}/accept", json={})
    assert accepted.status_code == 200
    segs = client.get(f"/api/media/{seg_ids['media_id']}/segments").json()
    assert "去年のハッカソン" in segs[1]["text"]


def test_assist_passes_context_and_message_to_llm(client, seg_ids):
    fake = use_fake([{"reply": "了解", "edits": []}])
    client.post(f"/api/segments/{seg_ids['ids'][1]}/assist", json={"message": "質問です"})
    system, user = fake.calls[0]
    assert "▶ 対象行: " + TEXTS[1] in user
    assert "文脈: " + TEXTS[0] in user
    assert "ユーザーの指示: 質問です" in user


def test_assist_returns_instruction_suggestion(client, seg_ids):
    use_fake([{
        "reply": "恒久ルールにできます。",
        "edits": [],
        "instruction_suggestion": "『それ』は基本的にハッカソンを指す",
    }])
    r = client.post(f"/api/segments/{seg_ids['ids'][1]}/assist", json={"message": "..."})
    assert r.json()["instruction_suggestion"] == "『それ』は基本的にハッカソンを指す"


def test_assist_blocks_invalid_edit_with_guard(client, seg_ids):
    """アシスト経由でも機械ガード(削除のみ等)は効く"""
    use_fake([{
        "reply": "消しておきますね。",
        "edits": [{"original": "それ", "replacement": "そ", "referent": ""}],
    }])
    r = client.post(f"/api/segments/{seg_ids['ids'][1]}/assist", json={"message": "..."})
    assert r.json()["edits"] == []  # ガードで弾かれ、editsに保存されない
    assert client.get(f"/api/media/{seg_ids['media_id']}/edits").json() == []


def test_assist_unknown_segment_404(client):
    assert client.post("/api/segments/999/assist", json={"message": "x"}).status_code == 404


# ---- 応答文は実際の状態どおりにする(LLMの「変更しました」を信じない) ----
def test_assist_reply_says_proposal_is_pending_even_if_llm_claims_done(client, seg_ids):
    use_fake([{
        "reply": "『それ』をハッカソンに変更しました。",
        "edits": [{"original": "それ", "replacement": "去年のハッカソン",
                   "referent": "去年のハッカソン"}],
    }])
    body = client.post(f"/api/segments/{seg_ids['ids'][1]}/assist",
                       json={"message": "このそれはハッカソンのこと"}).json()
    assert "変更しました" not in body["reply"]
    assert "案を作りました" in body["reply"]
    assert "まだ反映していません" in body["reply"]
    # 承認したときに行がどうなるかを、そのまま見せられるように返す
    assert body["edits"][0]["after_text"] == "はやまる: それ(去年のハッカソン)がすごく良くて"
    # まだ何も変わっていない
    segs = client.get(f"/api/media/{seg_ids['media_id']}/segments").json()
    assert segs[1]["text"] == TEXTS[1]


def test_assist_reply_when_guard_rejects_everything(client, seg_ids):
    use_fake([{
        "reply": "消しておきました。",
        "edits": [{"original": "それ", "replacement": "そ", "referent": ""}],
    }])
    body = client.post(f"/api/segments/{seg_ids['ids'][1]}/assist", json={"message": "..."}).json()
    assert "この行は変わっていません" in body["reply"]
    assert "消しておきました" not in body["reply"]


def test_assist_reply_for_plain_question_includes_ai_answer(client, seg_ids):
    use_fake([{"reply": "この『それ』はハッカソンを指しています。", "edits": []}])
    body = client.post(f"/api/segments/{seg_ids['ids'][1]}/assist", json={"message": "?"}).json()
    assert body["reply"].startswith("この行は変わっていません。")
    assert "ハッカソンを指しています" in body["reply"]
