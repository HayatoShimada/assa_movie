"""M28: 初回セットアップ(話者分離モデルの取得)。

インストール版のユーザーは `./dev.sh diarize-models` を叩けないので、
アプリから状態を見て取得できる必要がある。ネットワークは使わない。
"""

import pytest

from backend.jobs import setup_job


@pytest.fixture
def models(monkeypatch, tmp_path):
    """モデルの置き場所を一時ディレクトリに逃がす"""
    monkeypatch.setattr(setup_job.onnx, "DEFAULT_SEGMENTATION", tmp_path / "seg" / "model.onnx")
    monkeypatch.setattr(setup_job.onnx, "DEFAULT_EMBEDDING", tmp_path / "emb.onnx")
    return tmp_path


def place(models):
    (models / "seg").mkdir(parents=True, exist_ok=True)
    (models / "seg" / "model.onnx").write_bytes(b"x")
    (models / "emb.onnx").write_bytes(b"x")


# ---- 状態の取得 ----
def test_未取得なら未準備と返る(client, models):
    body = client.get("/api/setup").json()
    assert body["diarization"]["ready"] is False
    assert body["diarization"]["size_mb"] > 0


def test_取得済みなら準備済みと返る(client, models):
    place(models)
    assert client.get("/api/setup").json()["diarization"]["ready"] is True


def test_whispercppの状態も返す(client, models):
    body = client.get("/api/setup").json()
    assert "whispercpp" in body
    assert body["whispercpp"]["size_mb"] > 0


def test_話者分離モデルはアプリから取得できる(client, models):
    assert client.get("/api/setup").json()["diarization"]["installable"] is True


# ---- ダウンロード(ネットワークは使わない) ----
def test_取得すると準備済みになる(client, models, monkeypatch):
    def fake_download(url, dest, progress):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"x")
        progress(1.0)

    monkeypatch.setattr(setup_job, "download", fake_download)
    monkeypatch.setattr(setup_job, "extract_archive", lambda src, dest: place(models))

    setup_job.fetch_diarization_models(lambda p: None)
    assert client.get("/api/setup").json()["diarization"]["ready"] is True


def test_進捗は0から1へ単調に増える(models, monkeypatch):
    """UIのバーが戻らないこと"""
    def fake_download(url, dest, progress):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"x")
        progress(0.0)
        progress(0.5)
        progress(1.0)

    monkeypatch.setattr(setup_job, "download", fake_download)
    monkeypatch.setattr(setup_job, "extract_archive", lambda src, dest: place(models))

    seen = []
    setup_job.fetch_diarization_models(seen.append)
    assert seen == sorted(seen)
    assert seen[0] >= 0.0 and seen[-1] == 1.0


def test_途中で失敗しても壊れたファイルを残さない(models, monkeypatch):
    """中途半端なファイルがあるとエンジンが「使える」と誤判定してしまう"""
    def broken(url, dest, progress):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"partial")  # 途中まで書けた状態
        raise RuntimeError("回線が切れた")

    monkeypatch.setattr(setup_job, "download", broken)
    with pytest.raises(RuntimeError):
        setup_job.fetch_diarization_models(lambda p: None)
    assert not setup_job.onnx.is_available(
        setup_job.onnx.DEFAULT_SEGMENTATION, setup_job.onnx.DEFAULT_EMBEDDING
    )


def test_取得済みなら何もしない(models, monkeypatch):
    place(models)
    called = []
    monkeypatch.setattr(setup_job, "download", lambda *a: called.append(1))
    setup_job.fetch_diarization_models(lambda p: None)
    assert called == []


# ---- ジョブとして実行できる ----
def test_ジョブ種別として登録されている():
    from backend.jobs.queue import _HANDLERS

    assert "setup_diarization" in _HANDLERS


# ---- 取得を開始するAPI ----
def test_取得を開始するとジョブが積まれる(client, models):
    res = client.post("/api/setup/diarization")
    assert res.status_code == 200
    body = res.json()
    assert body["type"] == "setup_diarization"
    # 既存のジョブAPIで進捗を追える
    assert client.get(f"/api/jobs/{body['id']}").status_code == 200


def test_知らない項目は404(client, models):
    assert client.post("/api/setup/unknown").status_code == 404


# ---- whisper.cpp モデルの取得(同梱バイナリがあるときだけ) ----
@pytest.fixture
def whispercpp(monkeypatch, tmp_path):
    from backend.engines.asr import whispercpp as wc

    monkeypatch.setattr(wc, "DEFAULT_HOME", tmp_path)
    monkeypatch.setattr(wc, "bundled_dir", lambda: tmp_path / "app")
    return wc


def place_whispercpp_binary(wc):
    path = wc.bundled_dir() / "bin" / wc.BINARY_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\n", encoding="utf-8")
    path.chmod(0o755)
    return path


def test_バイナリが無ければモデルは取得させない(client, models, whispercpp):
    """モデルだけ3.1GB落としても使えない。無駄なダウンロードをさせない"""
    body = client.get("/api/setup").json()
    assert body["whispercpp"]["installable"] is False


def test_同梱バイナリがあればモデルを取得できる(client, models, whispercpp):
    place_whispercpp_binary(whispercpp)
    body = client.get("/api/setup").json()
    assert body["whispercpp"]["installable"] is True
    assert body["whispercpp"]["ready"] is False   # モデルがまだ無い


def test_モデルが揃えば準備済みになる(client, models, whispercpp):
    place_whispercpp_binary(whispercpp)
    model = whispercpp.resolve_model()
    model.parent.mkdir(parents=True, exist_ok=True)
    model.write_bytes(b"x")
    assert client.get("/api/setup").json()["whispercpp"]["ready"] is True


def test_モデル取得ジョブが登録されている():
    from backend.jobs.queue import _HANDLERS

    assert "setup_whispercpp" in _HANDLERS


def test_モデル取得は途中で失敗しても壊れたファイルを残さない(whispercpp, monkeypatch):
    place_whispercpp_binary(whispercpp)

    def broken(url, dest, progress):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"partial")
        raise RuntimeError("回線が切れた")

    monkeypatch.setattr(setup_job, "download", broken)
    with pytest.raises(RuntimeError):
        setup_job.fetch_whispercpp_model(lambda p: None)
    assert not whispercpp.resolve_model().exists()


def test_モデル取得済みなら何もしない(whispercpp, monkeypatch):
    place_whispercpp_binary(whispercpp)
    model = whispercpp.resolve_model()
    model.parent.mkdir(parents=True, exist_ok=True)
    model.write_bytes(b"x")
    called = []
    monkeypatch.setattr(setup_job, "download", lambda *a: called.append(1))
    setup_job.fetch_whispercpp_model(lambda p: None)
    assert called == []
