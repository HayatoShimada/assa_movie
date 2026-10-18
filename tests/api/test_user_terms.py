"""利用者の辞書(名前・用語)をHTTP経由で見る。

- 質問に答えると辞書に載る(プロジェクトをまたいで残る)
- 辞書の語が次の文字起こしでWhisperに渡る(空なら従来と全く同じ)
- 設定で使わないようにできる
- 辞書の画面から追加・修正・削除できる
- 以前の聞き間違いが新しい動画に出たら、AIに聞かなくても質問にする
"""

import numpy as np
import pytest

from backend.core.config import settings
from backend.engines.asr.base import Segment, TranscribeResult, Word
from backend.engines.asr.prompt import VERBATIM_STYLE
from tests.helpers import create_media, insert_segments, use_fake

TEXTS = [
    "はやまる: NVIDIAって会社はですね",
    "はやまる: 反動体を作ってる会社なんですよ",
    "高田さん: 反動体って何ですか",
]
TERM_RESPONSE = {"questions": [
    {"term": "反動体", "reason": "半導体の誤認識と思われます", "candidates": ["半導体"]}
]}


@pytest.fixture
def media(client, tmp_path):
    ids = create_media(client, tmp_path)
    insert_segments(client.app.state.db, ids["media_id"], [{"text": t} for t in TEXTS])
    return ids


def run_job(client, media_id, job_type, params=None):
    job = client.post(
        f"/api/media/{media_id}/jobs", json={"type": job_type, "params": params or {}}
    ).json()
    return client.app.state.jobs.wait(job["id"], timeout=30)


def answer_first_question(client, media_id, text):
    qid = client.get(f"/api/media/{media_id}/questions").json()[0]["id"]
    return client.post(f"/api/questions/{qid}/answer", json={"text": text})


# ---- 質問への回答で辞書に載る ----

def test_回答した表記が辞書に載り聞き間違いも覚える(client, media):
    use_fake([TERM_RESPONSE])
    run_job(client, media["media_id"], "extract_terms")
    assert answer_first_question(client, media["media_id"], "半導体").status_code == 200

    terms = client.get("/api/user-terms").json()
    assert len(terms) == 1
    assert terms[0]["term"] == "半導体"
    assert terms[0]["misrecognitions"] == ["反動体"]
    assert terms[0]["source"] == "question"
    assert terms[0]["used_for_asr"] is True


def test_別の動画で同じ語に答えても1件にまとまる(client, media, tmp_path):
    use_fake([TERM_RESPONSE])
    run_job(client, media["media_id"], "extract_terms")
    answer_first_question(client, media["media_id"], "半導体")

    other = create_media(client, tmp_path, name="別の対談")
    insert_segments(client.app.state.db, other["media_id"], [{"text": "はんどう体の話"}])
    use_fake([{"questions": [
        {"term": "はんどう体", "reason": "半導体の誤認識", "candidates": ["半導体"]}
    ]}])
    run_job(client, other["media_id"], "extract_terms")
    answer_first_question(client, other["media_id"], "半導体")

    terms = client.get("/api/user-terms").json()
    assert [t["term"] for t in terms] == ["半導体"]
    assert terms[0]["hits"] == 2
    assert terms[0]["misrecognitions"] == ["反動体", "はんどう体"]


def test_表記がそのままで正しいと答えても辞書に載る(client, media):
    use_fake([TERM_RESPONSE])
    run_job(client, media["media_id"], "extract_terms")
    answer_first_question(client, media["media_id"], "反動体")
    terms = client.get("/api/user-terms").json()
    assert [t["term"] for t in terms] == ["反動体"]
    assert terms[0]["misrecognitions"] == []


def test_回答してもプロジェクトの用語集と原文はこれまでどおり(client, media):
    """辞書は追加の保存先。LLMのプロンプトに効く用語集と非破壊の原則は変えない"""
    use_fake([TERM_RESPONSE])
    run_job(client, media["media_id"], "extract_terms")
    answer_first_question(client, media["media_id"], "半導体")
    glossary = client.get(f"/api/projects/{media['project_id']}/glossary").json()
    assert [g["term"] for g in glossary] == ["半導体"]
    segs = client.get(f"/api/media/{media['media_id']}/segments").json()
    assert segs[1]["original_text"] == TEXTS[1]


# ---- 辞書の画面(CRUD) ----

def test_追加_修正_削除(client):
    created = client.post("/api/user-terms", json={"term": "反動体"})
    assert created.status_code == 200
    tid = created.json()["id"]

    patched = client.patch(
        f"/api/user-terms/{tid}", json={"term": "半導体", "misrecognitions": ["反動体", ""]}
    )
    assert patched.status_code == 200
    assert patched.json()["term"] == "半導体"
    assert patched.json()["misrecognitions"] == ["反動体"]

    assert client.delete(f"/api/user-terms/{tid}").status_code == 200
    assert client.get("/api/user-terms").json() == []


def test_同じ語を追加すると1件にまとまる(client):
    client.post("/api/user-terms", json={"term": "半導体"})
    again = client.post("/api/user-terms", json={"term": " 半導体 "})
    assert again.status_code == 200
    assert again.json()["hits"] == 2
    assert len(client.get("/api/user-terms").json()) == 1


@pytest.mark.parametrize("term", ["", "   ", "あ" * 41])
def test_空や長すぎる語は400(client, term):
    r = client.post("/api/user-terms", json={"term": term})
    assert r.status_code == 400


def test_既にある語に直そうとすると409(client):
    client.post("/api/user-terms", json={"term": "半導体"})
    tid = client.post("/api/user-terms", json={"term": "反動体"}).json()["id"]
    r = client.patch(f"/api/user-terms/{tid}", json={"term": "半導体"})
    assert r.status_code == 409
    assert "すでに" in r.json()["detail"]


def test_無い語は404(client):
    assert client.patch("/api/user-terms/999", json={"term": "x"}).status_code == 404
    assert client.delete("/api/user-terms/999").status_code == 404


def test_上限を超えた語は今回は使わないと示す(client):
    # 長い語を大量に入れて、Whisperに渡せる量を超えさせる
    for i in range(40):
        client.post("/api/user-terms", json={"term": f"株式会社サイバーエージェント{i:02d}"})
    terms = client.get("/api/user-terms").json()
    used = [t for t in terms if t["used_for_asr"]]
    assert 0 < len(used) < len(terms)
    # 上から順に使う(並び順と使われる順が一致する)
    assert terms[: len(used)] == used


def test_設定で使わないにすると一覧でも使わないと示す(client):
    client.post("/api/user-terms", json={"term": "半導体"})
    client.patch("/api/settings", json={"asr_use_user_terms": False})
    assert client.get("/api/user-terms").json()[0]["used_for_asr"] is False


# ---- 次の文字起こしに渡る ----

class _CapturingEngine:
    name = "fake"

    def __init__(self):
        self.prompts: list[str | None] = []

    def transcribe(self, audio, language=None, progress=None, initial_prompt=None):
        self.prompts.append(initial_prompt)
        return TranscribeResult(segments=[
            Segment(start=0.0, end=1.0, text="半導体の話", words=[Word(0.0, 1.0, "半導体の話", 0.9)]),
        ])

    def unload(self):
        pass


@pytest.fixture
def engine(monkeypatch):
    from backend.jobs import transcribe_job

    fake = _CapturingEngine()
    monkeypatch.setattr(transcribe_job, "build_engine", lambda s: fake)
    monkeypatch.setattr(
        transcribe_job.audio_io, "decode", lambda path: np.zeros(16000, dtype=np.float32)
    )
    settings.diarization_enabled = False  # モデルもGPUも要らないように
    return fake


def test_辞書が空なら従来と同じプロンプト(client, media, engine):
    job = run_job(client, media["media_id"], "transcribe")
    assert job["status"] == "completed", job["error"]
    # v1.0.1までの initial_prompt と一字一句同じ
    assert engine.prompts == ["えーと、あのー、そのー、なんか、うん。"]


def test_辞書の語が次の文字起こしに渡る(client, media, engine):
    client.post("/api/user-terms", json={"term": "箱ストア"})
    client.post("/api/user-terms", json={"term": "半導体"})
    client.post("/api/user-terms", json={"term": "半導体"})  # よく使う語が先
    run_job(client, media["media_id"], "transcribe")
    assert engine.prompts == [f"{VERBATIM_STYLE} 半導体、箱ストア。"]


def test_別プロジェクトで覚えた語も使う(client, media, engine, tmp_path):
    """辞書は利用者単位。どのプロジェクトの文字起こしにも効く"""
    other = create_media(client, tmp_path, name="別の対談")
    client.post("/api/user-terms", json={"term": "半導体"})
    run_job(client, other["media_id"], "transcribe")
    run_job(client, media["media_id"], "transcribe")
    assert engine.prompts == [f"{VERBATIM_STYLE} 半導体。"] * 2


def test_辞書を使わない設定なら渡さない(client, media, engine):
    client.post("/api/user-terms", json={"term": "半導体"})
    client.patch("/api/settings", json={"asr_use_user_terms": False})
    run_job(client, media["media_id"], "transcribe")
    assert engine.prompts == [VERBATIM_STYLE]


def test_プロジェクト単位でも辞書を切れる(client, media, engine):
    client.post("/api/user-terms", json={"term": "半導体"})
    client.patch(
        f"/api/projects/{media['project_id']}",
        json={"settings": {"asr_use_user_terms": False}},
    )
    run_job(client, media["media_id"], "transcribe")
    assert engine.prompts == [VERBATIM_STYLE]


# ---- 以前の聞き間違いを質問にする ----

def test_以前の聞き間違いが出たらAIに聞かずに質問にする(client, media):
    client.post("/api/user-terms", json={"term": "半導体", "misrecognitions": ["反動体"]})
    fake = use_fake([{"questions": []}])
    job = run_job(client, media["media_id"], "extract_terms")
    assert job["status"] == "completed", job["error"]

    qs = client.get(f"/api/media/{media['media_id']}/questions").json()
    assert len(qs) == 1
    assert "反動体" in qs[0]["question_text"]
    assert "2回出現" in qs[0]["question_text"]
    assert "辞書" in qs[0]["question_text"]
    assert qs[0]["candidates"] == ["半導体"]
    assert len(fake.calls) == 1  # AIのスキャン自体は走る


def test_AIが同じ語を挙げても質問は1つ(client, media):
    client.post("/api/user-terms", json={"term": "半導体", "misrecognitions": ["反動体"]})
    use_fake([TERM_RESPONSE])
    run_job(client, media["media_id"], "extract_terms")
    qs = client.get(f"/api/media/{media['media_id']}/questions").json()
    assert len(qs) == 1


def test_辞書にある正しい表記はAIが挙げても聞かない(client, media):
    client.post("/api/user-terms", json={"term": "NVIDIA"})
    use_fake([{"questions": [
        {"term": "NVIDIA", "reason": "社名の表記確認", "candidates": ["エヌビディア"]}
    ]}])
    run_job(client, media["media_id"], "extract_terms")
    assert client.get(f"/api/media/{media['media_id']}/questions").json() == []


def test_AIに繋がらなくても辞書からの質問は残る(client, media):
    client.post("/api/user-terms", json={"term": "半導体", "misrecognitions": ["反動体"]})

    def broken(system, user):
        raise RuntimeError("Ollamaに接続できません")

    use_fake(broken)
    job = run_job(client, media["media_id"], "extract_terms")
    assert job["status"] == "failed"
    qs = client.get(f"/api/media/{media['media_id']}/questions").json()
    assert [q["candidates"] for q in qs] == [["半導体"]]
