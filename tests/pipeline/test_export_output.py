"""書き出し先とファイル名、書き出し結果を開く/再生するAPI。

ファイル選択で取り込んだ動画は保存名の先頭に衝突よけの32桁hexが付く
(backend/api/projects.py)。それを書き出しファイル名にそのまま使うと
`f878c15d…_対談_9s-55s_clip1.mp4` になり、利用者には何のファイルか分からない。
表示名の規則(frontend/src/lib/media.ts の mediaDisplayName)と揃えて外す。
"""

from pathlib import Path

import pytest

from backend.pipeline import export as export_mod

HEX = "f878c15d0123456789abcdef01234567"


@pytest.mark.parametrize(
    "name, media, start, end, clip_id, expected",
    [
        ("パス登録の動画", "/v/対談.mov", 624.4, 676.9, None, "対談_624s-676s.mp4"),
        ("クリップには番号が付く", "/v/対談.mov", 9.0, 55.0, 3, "対談_9s-55s_clip3.mp4"),
        ("取り込んだ動画は衝突よけを外す", f"/u/{HEX}_smoke_test.mp4", 9.2, 55.0, 1,
         "smoke_test_9s-55s_clip1.mp4"),
        ("32桁に満たないhexは元の名前の一部として残す", "/u/abc123_対談.mov", 0, 10, None,
         "abc123_対談_0s-10s.mp4"),
        ("hexだけの名前は消さない", f"/u/{HEX}_.mov", 0, 10, None, f"{HEX}__0s-10s.mp4"),
    ],
)
def test_export_file_name(name, media, start, end, clip_id, expected):
    assert export_mod.export_file_name(Path(media), start, end, clip_id) == expected, name


@pytest.mark.parametrize(
    "name, configured, expected",
    [
        ("設定が空なら既定の場所", "", Path("/home/u/Videos/KirinukiStudio")),
        ("空白だけも空として扱う", "   ", Path("/home/u/Videos/KirinukiStudio")),
        ("設定したフォルダをそのまま使う", "/mnt/外付け/切り抜き", Path("/mnt/外付け/切り抜き")),
        ("前後の空白は落とす", "  /mnt/a  ", Path("/mnt/a")),
    ],
)
def test_resolve_export_dir(name, configured, expected):
    got = export_mod.resolve_export_dir(configured, default=Path("/home/u/Videos/KirinukiStudio"))
    assert got == expected, name


def test_書き出し先はチルダをホームに展開する():
    assert export_mod.resolve_export_dir("~/切り抜き") == Path.home() / "切り抜き"


def test_check_export_dir_は無ければ作る(tmp_path):
    target = tmp_path / "深い" / "場所"
    assert export_mod.check_export_dir(str(target)) is None
    assert target.is_dir()


def test_check_export_dir_は相対パスを断る():
    problem = export_mod.check_export_dir("切り抜き")
    assert problem and "先頭から" in problem


def test_check_export_dir_は作れない場所を直し方つきで断る(tmp_path):
    blocker = tmp_path / "file.txt"
    blocker.write_text("x", encoding="utf-8")
    problem = export_mod.check_export_dir(str(blocker / "sub"))
    assert problem and "別のフォルダを選んでください" in problem


# ---- ジョブ: 書き出し先には完成品だけを置く ----

@pytest.fixture
def captured(monkeypatch):
    """ffmpegは走らせず、渡された字幕ファイルの中身と出力先を記録する"""
    calls: list[dict] = []

    def fake_run(cmd, duration, progress=None, timeout=0):
        ass = next((a for a in cmd if "ass='" in a), None)
        ass_path = None
        if ass:
            import re

            ass_path = Path(re.search(r"ass='([^']+)'", ass).group(1).replace("\\:", ":"))
        calls.append({
            "cmd": cmd,
            "ass_path": ass_path,
            "ass_text": ass_path.read_text(encoding="utf-8") if ass_path else None,
        })
        Path(cmd[-1]).write_bytes(b"mp4")  # 出力ができたことにする

    monkeypatch.setattr(export_mod, "detect_encoder", lambda: "libx264")
    monkeypatch.setattr(export_mod, "run_export", fake_run)
    from backend.api import clips as clips_api

    monkeypatch.setattr(clips_api, "_require_ffmpeg", lambda: None)
    return calls


def _media(client, tmp_path, filename="対談.mov"):
    pid = client.post("/api/projects", json={"name": "p"}).json()["id"]
    src = tmp_path / filename
    src.write_bytes(b"x")
    mid = client.post(f"/api/projects/{pid}/media", json={"path": str(src)}).json()["id"]
    db = client.app.state.db
    db.execute("UPDATE media SET width=1920, height=1080, duration=60 WHERE id=?", (mid,))
    db.execute(
        "INSERT INTO segments (media_id, idx, start, end, text, original_text)"
        " VALUES (?,0,1,3,'こんにちは','こんにちは')", (mid,),
    )
    db.commit()
    return mid


def _export_clip(client, mid, start=0, end=10):
    clip = client.post(f"/api/media/{mid}/clips", json={"start": start, "end": end}).json()
    r = client.post(f"/api/clips/{clip['id']}/export")
    job = client.app.state.jobs.wait(r.json()["job_id"], timeout=30)
    assert job["status"] == "completed", job["error"]
    return clip, r.json()["job_id"]


def test_書き出し先に字幕の中間ファイルを残さない(client, tmp_path, captured):
    mid = _media(client, tmp_path)
    clip, job_id = _export_clip(client, mid)

    exports = tmp_path / "videos" / "KirinukiStudio"
    assert sorted(p.name for p in exports.iterdir()) == [f"対談_0s-10s_clip{clip['id']}.mp4"]
    # 字幕は焼き込まれている(ffmpegには渡っていた)が、作業用の場所に置かれ後で消える
    assert "こんにちは" in captured[-1]["ass_text"]
    assert captured[-1]["ass_path"].parent != exports
    assert not captured[-1]["ass_path"].exists()


def test_取り込んだ動画の書き出し名に衝突よけが付かない(client, tmp_path, captured):
    mid = _media(client, tmp_path, filename=f"{HEX}_smoke_test.mp4")
    clip, job_id = _export_clip(client, mid, 9, 55)
    result = client.get(f"/api/jobs/{job_id}").json()["result"]
    assert Path(result["path"]).name == f"smoke_test_9s-55s_clip{clip['id']}.mp4"
    assert Path(result["path"]).parent == tmp_path / "videos" / "KirinukiStudio"


def test_既定の書き出し先は元動画の隣ではなく動画フォルダ(client, tmp_path, captured):
    """issue #3: 取り込んだ動画はアプリのデータフォルダ(Finderでは隠れている)に
    コピーされる。その隣の exports/ に書き出していたので見つけられなかった"""
    mid = _media(client, tmp_path)
    _, job_id = _export_clip(client, mid)
    out = Path(client.get(f"/api/jobs/{job_id}").json()["result"]["path"])
    assert out.parent == tmp_path / "videos" / "KirinukiStudio"
    assert not (tmp_path / "exports").exists()


def test_設定した書き出し先に書き出す(client, tmp_path, captured):
    target = tmp_path / "自分で選んだ場所"
    r = client.patch("/api/settings", json={"export_dir": str(target)})
    assert r.status_code == 200, r.text
    mid = _media(client, tmp_path)
    clip, job_id = _export_clip(client, mid)
    assert [p.name for p in target.iterdir()] == [f"対談_0s-10s_clip{clip['id']}.mp4"]


def test_書き出し先はプロジェクトごとには変えられない(client):
    """「書き出した動画はどこ?」の答えを1つにする"""
    r = client.post("/api/projects", json={"name": "p", "settings": {"export_dir": "/tmp/x"}})
    assert r.status_code == 400


def test_使えない書き出し先は保存させない(client, tmp_path):
    blocker = tmp_path / "file.txt"
    blocker.write_text("x", encoding="utf-8")
    r = client.patch("/api/settings", json={"export_dir": str(blocker / "sub")})
    assert r.status_code == 400
    assert "別のフォルダ" in r.json()["detail"]
    assert client.get("/api/settings").json()["values"]["export_dir"] == ""


def test_書き出し先が使えなくなっていたら直し方つきで失敗する(client, tmp_path, captured):
    """保存した後に外付けドライブを外した、など"""
    from backend.core.config import settings

    blocker = tmp_path / "file.txt"
    blocker.write_text("x", encoding="utf-8")
    settings.export_dir = str(blocker / "sub")
    mid = _media(client, tmp_path)
    clip = client.post(f"/api/media/{mid}/clips", json={"start": 0, "end": 10}).json()
    r = client.post(f"/api/clips/{clip['id']}/export")
    job = client.app.state.jobs.wait(r.json()["job_id"], timeout=30)
    assert job["status"] == "failed"
    assert "別のフォルダを選んでください" in job["error"]


# ---- 書き出し先の表示と、フォルダを開く ----

def test_書き出し先の表示は既定と設定を区別する(client, tmp_path):
    default = str(tmp_path / "videos" / "KirinukiStudio")
    assert client.get("/api/export-dir").json() == {
        "path": default, "default_path": default, "is_default": True,
    }
    target = tmp_path / "選んだ場所"
    client.patch("/api/settings", json={"export_dir": str(target)})
    assert client.get("/api/export-dir").json() == {
        "path": str(target), "default_path": default, "is_default": False,
    }
    # 空に戻すと既定に戻る
    client.patch("/api/settings", json={"export_dir": ""})
    assert client.get("/api/export-dir").json()["is_default"] is True


def test_書き出し先のフォルダを書き出す前でも開ける(client, tmp_path, monkeypatch):
    from backend.core import reveal

    opened: list[Path] = []
    monkeypatch.setattr(reveal, "open_folder", lambda path, os_name=None: opened.append(path))
    r = client.post("/api/export-dir/reveal")
    assert r.status_code == 200, r.text
    target = tmp_path / "videos" / "KirinukiStudio"
    assert opened == [target]
    assert target.is_dir(), "まだ無ければ作ってから開く"


# ---- 書き出し先を開く・再生する ----

@pytest.fixture
def revealed(monkeypatch):
    from backend.core import reveal

    calls: list[Path] = []
    monkeypatch.setattr(reveal, "reveal", lambda path, os_name=None: calls.append(path))
    return calls


def test_書き出し結果のフォルダを開ける(client, tmp_path, captured, revealed):
    mid = _media(client, tmp_path)
    _, job_id = _export_clip(client, mid)
    r = client.post(f"/api/jobs/{job_id}/reveal")
    assert r.status_code == 200, r.text
    out = Path(client.get(f"/api/jobs/{job_id}").json()["result"]["path"])
    assert revealed == [out]
    assert r.json() == {"folder": str(out.parent)}


def test_書き出し結果を再生用に取得できる(client, tmp_path, captured):
    mid = _media(client, tmp_path)
    _, job_id = _export_clip(client, mid)
    r = client.get(f"/api/jobs/{job_id}/output")
    assert r.status_code == 200
    assert r.content == b"mp4"


def test_書き出し以外のジョブは開けない(client, tmp_path, revealed):
    mid = _media(client, tmp_path)
    db = client.app.state.db
    # 実行はさせない(LLMを呼ばない)。完了済みの行だけ作る
    job_id = db.execute(
        "INSERT INTO jobs (media_id, type, status, result_json)"
        " VALUES (?, 'filler', 'completed', ?)",
        (mid, '{"path": "/etc/passwd"}'),
    ).lastrowid
    db.commit()
    assert client.post(f"/api/jobs/{job_id}/reveal").status_code == 400
    assert client.get(f"/api/jobs/{job_id}/output").status_code == 400
    assert revealed == []


def test_存在しないジョブは404(client, revealed):
    assert client.post("/api/jobs/99999/reveal").status_code == 404
    assert client.get("/api/jobs/99999/output").status_code == 404


def test_書き出し先を変えた後も前の書き出しを開ける(client, tmp_path, captured, revealed):
    """開ける範囲をフォルダで縛ると、設定を変えた途端に前の書き出しが開けなくなる"""
    mid = _media(client, tmp_path)
    _, job_id = _export_clip(client, mid)
    client.patch("/api/settings", json={"export_dir": str(tmp_path / "別の場所")})
    assert client.post(f"/api/jobs/{job_id}/reveal").status_code == 200
    assert client.get(f"/api/jobs/{job_id}/output").status_code == 200


def test_このジョブが作ったのではないファイルは開かない(client, tmp_path, captured, revealed):
    """結果のパスはジョブが書くが、任意のパスを開けるAPIにしないため念のため確かめる"""
    mid = _media(client, tmp_path)
    _, job_id = _export_clip(client, mid)
    import json

    db = client.app.state.db
    # 別の名前のファイルも、同じフォルダにある別の動画も開かない
    for name in ("secret.txt", "別の動画_0s-10s.mp4"):
        outside = tmp_path / "videos" / "KirinukiStudio" / name
        outside.write_text("x", encoding="utf-8")
        db.execute(
            "UPDATE jobs SET result_json=? WHERE id=?",
            (json.dumps({"path": str(outside)}), job_id),
        )
        db.commit()
        assert client.post(f"/api/jobs/{job_id}/reveal").status_code == 400, name
        assert client.get(f"/api/jobs/{job_id}/output").status_code == 400, name
    assert revealed == []


def test_消された書き出しファイルは分かる言葉で404(client, tmp_path, captured, revealed):
    mid = _media(client, tmp_path)
    _, job_id = _export_clip(client, mid)
    out = Path(client.get(f"/api/jobs/{job_id}").json()["result"]["path"])
    out.unlink()
    r = client.post(f"/api/jobs/{job_id}/reveal")
    assert r.status_code == 404
    assert "見つかりません" in r.json()["detail"]
    assert revealed == []
