"""文字起こしの手直し(本文・話者)のAPIテスト。

利用者が誤認識(例「腕駒」)を手で直せること、直したものをいつでも戻せること
(original_text は常に原文のまま)、AIの編集と手直しが互いを消さないことを見る。
"""

import pytest

from tests.helpers import create_media, insert_segments, use_fake

TEXTS = [
    "去年ハッカソンに出たんですよ",
    "それがすごく良くて腕駒の話もした",
    "その人自身が変わったって感じですか",
]


@pytest.fixture
def media(client, tmp_path):
    ids = create_media(client, tmp_path)
    insert_segments(
        client.app.state.db,
        ids["media_id"],
        [
            {"text": TEXTS[0], "speaker": "話者A"},
            {"text": TEXTS[1], "speaker": "話者A"},
            {"text": TEXTS[2], "speaker": "話者B"},
        ],
    )
    return ids


def segments(client, media_id):
    return client.get(f"/api/media/{media_id}/segments").json()


def edits(client, media_id, status=None):
    url = f"/api/media/{media_id}/edits" + (f"?status={status}" if status else "")
    return client.get(url).json()


def propose(client, segment_id, original, replacement):
    """アシスト経由で承認待ちの編集を1件作る"""
    use_fake([{
        "reply": "提案します",
        "edits": [{"original": original, "replacement": replacement, "referent": replacement}],
    }])
    body = client.post(f"/api/segments/{segment_id}/assist", json={"message": "x"}).json()
    return body["edits"][0]["id"]


# ---- 本文の手直し ----
def test_manual_edit_keeps_original_and_marks_edited(client, media):
    seg = segments(client, media["media_id"])[1]
    r = client.patch(f"/api/segments/{seg['id']}", json={"text": "それがすごく良くて腕前の話もした"})
    assert r.status_code == 200
    body = r.json()
    assert body["text"] == "それがすごく良くて腕前の話もした"
    assert body["original_text"] == TEXTS[1]  # 原文は残る
    assert body["edited_by_user"] is True


def test_speaker_change_alone_is_not_a_text_edit(client, media):
    """話者の付け替えは本文の手直しではない(「編集済」にしない・AIの再実行を止めない)"""
    seg = segments(client, media["media_id"])[1]
    body = client.patch(f"/api/segments/{seg['id']}", json={"speaker": "話者B"}).json()
    assert body["speaker"] == "話者B"
    assert body["edited_by_user"] is False


def test_manual_edit_back_to_same_text_is_not_edited(client, media):
    """直した結果が元と同じなら手直し扱いにしない"""
    seg = segments(client, media["media_id"])[1]
    body = client.patch(f"/api/segments/{seg['id']}", json={"text": TEXTS[1]}).json()
    assert body["edited_by_user"] is False


def test_empty_text_is_rejected(client, media):
    seg = segments(client, media["media_id"])[1]
    r = client.patch(f"/api/segments/{seg['id']}", json={"text": "   "})
    assert r.status_code == 400
    assert segments(client, media["media_id"])[1]["text"] == TEXTS[1]


def test_restore_discards_manual_edit(client, media):
    seg = segments(client, media["media_id"])[1]
    client.patch(f"/api/segments/{seg['id']}", json={"text": "全部書き換えた"})

    r = client.post(f"/api/segments/{seg['id']}/restore")
    assert r.status_code == 200
    body = r.json()
    assert body["text"] == TEXTS[1]
    assert body["edited_by_user"] is False


def test_restore_keeps_accepted_ai_edits(client, media):
    """手直しを取り消しても、承認済みのAIの修正は残る"""
    seg = segments(client, media["media_id"])[1]
    eid = propose(client, seg["id"], "それ", "ハッカソン")
    client.post(f"/api/edits/{eid}/accept", json={"form": "annotate"})
    client.patch(f"/api/segments/{seg['id']}", json={"text": "全部書き換えた"})

    body = client.post(f"/api/segments/{seg['id']}/restore").json()
    assert body["text"] == "それ(ハッカソン)がすごく良くて腕駒の話もした"
    assert edits(client, media["media_id"], "applied")[0]["id"] == eid


def test_restore_reverts_edits_made_on_top_of_manual_text(client, media):
    """手直しした文に対して承認した編集は、手直しを取り消すと当てる場所が無いので取り消し扱い"""
    seg = segments(client, media["media_id"])[1]
    client.patch(f"/api/segments/{seg['id']}", json={"text": "あれがすごく良かった"})
    eid = propose(client, seg["id"], "あれ", "イベント")
    client.post(f"/api/edits/{eid}/accept", json={"form": "annotate"})

    body = client.post(f"/api/segments/{seg['id']}/restore").json()
    assert body["text"] == TEXTS[1]
    assert edits(client, media["media_id"])[0]["status"] == "reverted"


def test_revert_ai_edit_keeps_manual_edit(client, media):
    """手直しした行でAIの修正を取り消しても、手直しは消えない(以前は原文に戻っていた)"""
    seg = segments(client, media["media_id"])[1]
    eid = propose(client, seg["id"], "それ", "ハッカソン")
    client.post(f"/api/edits/{eid}/accept", json={"form": "annotate"})
    client.patch(
        f"/api/segments/{seg['id']}",
        json={"text": "それ(ハッカソン)がすごく良くて腕前の話もした"},
    )

    r = client.post(f"/api/edits/{eid}/revert")
    assert r.status_code == 200
    after = segments(client, media["media_id"])[1]
    assert after["text"] == "それがすごく良くて腕前の話もした"
    assert after["edited_by_user"] is True


def test_revert_ai_edit_whose_text_was_rewritten_by_hand_is_refused(client, media):
    seg = segments(client, media["media_id"])[1]
    eid = propose(client, seg["id"], "それ", "ハッカソン")
    client.post(f"/api/edits/{eid}/accept", json={"form": "annotate"})
    client.patch(f"/api/segments/{seg['id']}", json={"text": "全部書き換えた"})

    r = client.post(f"/api/edits/{eid}/revert")
    assert r.status_code == 400
    assert "手で直して" in r.json()["detail"]
    assert segments(client, media["media_id"])[1]["text"] == "全部書き換えた"


def test_revert_term_edit_does_not_turn_into_annotation(client, media):
    """固有名詞の一括修正を含む行で別の編集を取り消しても、本文が壊れない
    (以前は全編集を注釈形式で当て直し「腕駒(腕前)」になっていた)"""
    mid = media["media_id"]
    seg = segments(client, mid)[1]
    db = client.app.state.db
    db.execute(
        "INSERT INTO edits (media_id, segment_id, kind, original, replacement, status,"
        " confidence, created_by) VALUES (?,?,'term','腕駒','腕前','applied','auto','user')",
        (mid, seg["id"]),
    )
    db.execute("UPDATE segments SET text=? WHERE id=?",
               ("それがすごく良くて腕前の話もした", seg["id"]))
    db.commit()
    eid = propose(client, seg["id"], "それ", "ハッカソン")
    client.post(f"/api/edits/{eid}/accept", json={"form": "annotate"})

    client.post(f"/api/edits/{eid}/revert")
    assert segments(client, mid)[1]["text"] == "それがすごく良くて腕前の話もした"


def test_resolve_does_not_mark_edit_applied_on_hand_edited_segment(client, media):
    """手直しした行には自動適用しない。適用していないのに「適用済み」と記録しない"""
    mid = media["media_id"]
    seg = segments(client, mid)[1]
    client.patch(f"/api/segments/{seg['id']}", json={"text": "それがとても良かった"})
    use_fake([{"edits": [
        {"line": 2, "original": "それ", "replacement": "ハッカソン",
         "referent": "ハッカソン", "confidence": "auto"},
    ]}])
    job = client.post(
        f"/api/media/{mid}/jobs",
        json={"type": "resolve", "params": {"apply_mode": "full_auto"}},
    ).json()
    assert client.app.state.jobs.wait(job["id"], timeout=30)["status"] == "completed"

    assert segments(client, mid)[1]["text"] == "それがとても良かった"
    rows = edits(client, mid)
    assert [r["status"] for r in rows] == ["proposed"]


# ---- 話者名の変更 ----
def test_rename_speaker_changes_every_row_of_the_media(client, media):
    mid = media["media_id"]
    r = client.post(f"/api/media/{mid}/speakers/rename",
                    json={"current": "話者A", "new": " 山田 "})
    assert r.status_code == 200
    assert r.json() == {"changed": 2}
    assert [s["speaker"] for s in segments(client, mid)] == ["山田", "山田", "話者B"]
    # 本文は変えない(手直し扱いにもしない)
    assert all(not s["edited_by_user"] for s in segments(client, mid))


def test_rename_speaker_only_touches_that_media(client, media, tmp_path):
    # 同じプロジェクトの別の動画(話者名は動画ごとに付く)
    path = tmp_path / "b.wav"
    path.write_bytes(b"x")
    other_mid = client.post(
        f"/api/projects/{media['project_id']}/media", json={"path": str(path)}
    ).json()["id"]
    insert_segments(client.app.state.db, other_mid, [{"text": "別の動画", "speaker": "話者A"}])

    client.post(f"/api/media/{media['media_id']}/speakers/rename",
                json={"current": "話者A", "new": "山田"})
    assert segments(client, other_mid)[0]["speaker"] == "話者A"


@pytest.mark.parametrize(
    ("new", "status", "detail"),
    [
        ("", 400, "名前を入れてください"),
        ("山田,太郎", 400, "使えません"),
        # 既にいる話者の名前にすると2人が混ざり、元に戻せなくなる
        ("話者B", 400, "すでにこの動画にいる話者"),
    ],
)
def test_rename_speaker_rejects_bad_names(client, media, new, status, detail):
    r = client.post(f"/api/media/{media['media_id']}/speakers/rename",
                    json={"current": "話者A", "new": new})
    assert r.status_code == status
    assert detail in r.json()["detail"]
    assert segments(client, media["media_id"])[0]["speaker"] == "話者A"


def test_rename_unknown_speaker_is_404(client, media):
    r = client.post(f"/api/media/{media['media_id']}/speakers/rename",
                    json={"current": "いない人", "new": "山田"})
    assert r.status_code == 404


def test_patch_speaker_validates_name(client, media):
    seg = segments(client, media["media_id"])[0]
    r = client.patch(f"/api/segments/{seg['id']}", json={"speaker": "a:b"})
    assert r.status_code == 400
