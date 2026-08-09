"""M4: resolveジョブとレビューAPIの統合テスト(FakeLLMで決定的に動かす)"""

import pytest
from fastapi.testclient import TestClient

from tests.helpers import create_media, insert_segments, use_fake

SEGMENT_TEXTS = [
    "はやまる: 去年ハッカソンに出たんですよ",
    "はやまる: それがすごく良くて",
    "高田さん: その人自身が変わったって感じですか",
]


@pytest.fixture
def media(client, tmp_path):
    ids = create_media(client, tmp_path)
    insert_segments(
        client.app.state.db,
        ids["media_id"],
        [
            {"text": t, "speaker": "はやまる", "start": i * 2.0, "end": i * 2.0 + 1.5}
            for i, t in enumerate(SEGMENT_TEXTS)
        ],
    )
    return ids




def run_resolve(client, media_id, params=None):
    job = client.post(
        f"/api/media/{media_id}/jobs",
        json={"type": "resolve", "params": params or {}},
    ).json()
    return client.app.state.jobs.wait(job["id"], timeout=30)


def segments(client, media_id):
    return client.get(f"/api/media/{media_id}/segments").json()


def edits(client, media_id, status=None):
    url = f"/api/media/{media_id}/edits" + (f"?status={status}" if status else "")
    return client.get(url).json()


# ---- 提案の保存と適用 ----
def test_auto_confidence_is_applied_review_is_not(client, media):
    mid = media["media_id"]
    use_fake([{"edits": [
        {"line": 2, "original": "それ", "replacement": "去年のハッカソン",
         "referent": "去年のハッカソン", "confidence": "auto"},
        {"line": 3, "original": "その人", "replacement": "はやまる",
         "referent": "はやまる", "confidence": "review"},
    ]}])
    job = run_resolve(client, mid, {"apply_mode": "auto_and_review", "form": "annotate"})
    assert job["status"] == "completed", job["error"]

    rows = edits(client, mid)
    by_status = {r["status"] for r in rows}
    assert by_status == {"applied", "proposed"}

    segs = segments(client, mid)
    assert segs[1]["text"] == "はやまる: それ(去年のハッカソン)がすごく良くて"
    assert segs[2]["text"] == SEGMENT_TEXTS[2]  # reviewは未適用


def test_full_auto_applies_everything(client, media):
    mid = media["media_id"]
    use_fake([{"edits": [
        {"line": 2, "original": "それ", "replacement": "ハッカソン",
         "referent": "ハッカソン", "confidence": "review"},
    ]}])
    run_resolve(client, mid, {"apply_mode": "full_auto"})
    assert edits(client, mid)[0]["status"] == "applied"


def test_all_review_applies_nothing(client, media):
    mid = media["media_id"]
    use_fake([{"edits": [
        {"line": 2, "original": "それ", "replacement": "ハッカソン",
         "referent": "ハッカソン", "confidence": "auto"},
    ]}])
    run_resolve(client, mid, {"apply_mode": "all_review"})
    assert edits(client, mid)[0]["status"] == "proposed"
    assert segments(client, mid)[1]["text"] == SEGMENT_TEXTS[1]


def test_machine_guard_blocks_bad_edit_and_records_feedback(client, media):
    """「その人 → 人」のような削除のみの編集はeditsに入らずfeedbackに残る"""
    mid = media["media_id"]
    use_fake([{"edits": [
        {"line": 3, "original": "その人", "replacement": "人",
         "referent": "人", "confidence": "auto"},
    ]}])
    run_resolve(client, mid)

    assert edits(client, mid) == []
    fb = client.app.state.db.execute(
        "SELECT * FROM feedback WHERE media_id=?", (mid,)
    ).fetchall()
    assert len(fb) == 1
    assert "機械ガード" in fb[0]["note"]
    assert "削除のみ" in fb[0]["note"]


# ---- レビュー操作 ----
def test_accept_proposed_edit(client, media):
    mid = media["media_id"]
    use_fake([{"edits": [
        {"line": 2, "original": "それ", "replacement": "ハッカソン",
         "referent": "ハッカソン", "confidence": "review"},
    ]}])
    run_resolve(client, mid, {"apply_mode": "all_review"})
    eid = edits(client, mid)[0]["id"]

    r = client.post(f"/api/edits/{eid}/accept", json={})
    assert r.status_code == 200 and r.json()["status"] == "applied"
    assert "(ハッカソン)" in segments(client, mid)[1]["text"]


def test_accept_with_correction_records_feedback(client, media):
    mid = media["media_id"]
    use_fake([{"edits": [
        {"line": 2, "original": "それ", "replacement": "ハッカソン",
         "referent": "ハッカソン", "confidence": "review"},
    ]}])
    run_resolve(client, mid, {"apply_mode": "all_review"})
    eid = edits(client, mid)[0]["id"]

    r = client.post(f"/api/edits/{eid}/accept",
                    json={"replacement": "去年のAIハッカソン", "form": "replace"})
    assert r.status_code == 200
    assert r.json()["replacement"] == "去年のAIハッカソン"
    assert "去年のAIハッカソン" in segments(client, mid)[1]["text"]

    fb = client.app.state.db.execute(
        "SELECT * FROM feedback WHERE kind='correction'"
    ).fetchall()
    assert len(fb) == 1 and fb[0]["after"] == "去年のAIハッカソン"


def test_reject_records_feedback_with_note(client, media):
    mid = media["media_id"]
    use_fake([{"edits": [
        {"line": 2, "original": "それ", "replacement": "ハッカソン",
         "referent": "ハッカソン", "confidence": "review"},
    ]}])
    run_resolve(client, mid, {"apply_mode": "all_review"})
    eid = edits(client, mid)[0]["id"]

    r = client.post(f"/api/edits/{eid}/reject", json={"note": "文脈が違う"})
    assert r.status_code == 200 and r.json()["status"] == "rejected"
    assert segments(client, mid)[1]["text"] == SEGMENT_TEXTS[1]

    fb = client.app.state.db.execute("SELECT * FROM feedback WHERE kind='rejection'").fetchone()
    assert fb["note"] == "文脈が違う"


def test_revert_applied_edit_restores_text(client, media):
    mid = media["media_id"]
    use_fake([{"edits": [
        {"line": 2, "original": "それ", "replacement": "ハッカソン",
         "referent": "ハッカソン", "confidence": "auto"},
    ]}])
    run_resolve(client, mid)
    eid = edits(client, mid)[0]["id"]
    assert segments(client, mid)[1]["text"] != SEGMENT_TEXTS[1]

    r = client.post(f"/api/edits/{eid}/revert")
    assert r.status_code == 200 and r.json()["status"] == "reverted"
    assert segments(client, mid)[1]["text"] == SEGMENT_TEXTS[1]  # 原文に戻る


def test_reject_applied_edit_is_rejected_with_400(client, media):
    mid = media["media_id"]
    use_fake([{"edits": [
        {"line": 2, "original": "それ", "replacement": "ハッカソン",
         "referent": "ハッカソン", "confidence": "auto"},
    ]}])
    run_resolve(client, mid)
    eid = edits(client, mid)[0]["id"]
    assert client.post(f"/api/edits/{eid}/reject", json={}).status_code == 400


# ---- フィードバック学習ループ(M4の受け入れ基準) ----
def test_rejected_feedback_appears_in_next_prompt(client, media):
    """却下 → 再実行時にfew-shotとしてプロンプトに載る"""
    mid = media["media_id"]
    use_fake([{"edits": [
        {"line": 2, "original": "それ", "replacement": "ハッカソン",
         "referent": "ハッカソン", "confidence": "review"},
    ]}])
    run_resolve(client, mid, {"apply_mode": "all_review"})
    eid = edits(client, mid)[0]["id"]
    client.post(f"/api/edits/{eid}/reject", json={"note": "参照先が違う"})

    fake2 = use_fake([{"edits": []}])
    run_resolve(client, mid)

    system_prompt = fake2.calls[0][0]
    assert "却下された編集" in system_prompt
    assert "参照先が違う" in system_prompt  # 却下理由が次回に効く


def test_custom_instruction_and_glossary_reach_prompt(client, media):
    mid, pid = media["media_id"], media["project_id"]
    client.post(f"/api/projects/{pid}/instructions",
                json={"text": "『それ』は基本的にAIハッカソンを指す"})
    client.post(f"/api/projects/{pid}/glossary",
                json={"term": "箱ストア", "description": "はやまるの古着店"})

    fake = use_fake([{"edits": []}])
    run_resolve(client, mid)

    prompt = fake.calls[0][0]
    assert "AIハッカソン" in prompt
    assert "箱ストア" in prompt and "古着店" in prompt


def test_disabled_instruction_is_excluded(client, media):
    mid, pid = media["media_id"], media["project_id"]
    inst = client.post(f"/api/projects/{pid}/instructions",
                       json={"text": "無効にする指示"}).json()
    client.patch(f"/api/instructions/{inst['id']}?enabled=false")

    fake = use_fake([{"edits": []}])
    run_resolve(client, mid)
    assert "無効にする指示" not in fake.calls[0][0]


# ---- 範囲再実行 ----
def test_rerun_unresolved_skips_segments_with_edits(client, media):
    mid = media["media_id"]
    use_fake([{"edits": [
        {"line": 2, "original": "それ", "replacement": "ハッカソン",
         "referent": "ハッカソン", "confidence": "auto"},
    ]}])
    run_resolve(client, mid)

    fake2 = use_fake([{"edits": []}])
    run_resolve(client, mid, {"scope": "unresolved"})

    user_prompt = fake2.calls[0][1]
    targets = user_prompt.split("## 編集対象")[1]
    assert "2: " not in targets     # 既に編集がある行は対象外
    assert "1: " in targets and "3: " in targets


def test_rerun_keeps_applied_edits(client, media):
    mid = media["media_id"]
    use_fake([{"edits": [
        {"line": 2, "original": "それ", "replacement": "ハッカソン",
         "referent": "ハッカソン", "confidence": "auto"},
    ]}])
    run_resolve(client, mid)
    before = [e["id"] for e in edits(client, mid, status="applied")]

    use_fake([{"edits": []}])
    run_resolve(client, mid, {"scope": "all"})
    after = [e["id"] for e in edits(client, mid, status="applied")]
    assert before == after  # 承認済みは再実行で消えない


def test_rerun_specific_segments_only(client, media):
    mid = media["media_id"]
    seg_ids = [s["id"] for s in segments(client, mid)]
    fake = use_fake([{"edits": []}])
    run_resolve(client, mid, {"scope": "segment_ids", "segment_ids": [seg_ids[2]]})

    targets = fake.calls[0][1].split("## 編集対象")[1]
    assert "3: " in targets and "1: " not in targets


def test_user_edited_segment_is_not_overwritten(client, media):
    """手動修正済みのセグメントは自動適用で上書きしない"""
    mid = media["media_id"]
    sid = segments(client, mid)[1]["id"]
    client.patch(f"/api/segments/{sid}", json={"text": "はやまる: 手で直した文"})

    use_fake([{"edits": [
        {"line": 2, "original": "それ", "replacement": "ハッカソン",
         "referent": "ハッカソン", "confidence": "auto"},
    ]}])
    run_resolve(client, mid)
    assert segments(client, mid)[1]["text"] == "はやまる: 手で直した文"
