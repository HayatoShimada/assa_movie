"""ハードウェアプロファイルの永続化と、旧設定キーの掃除。

設計(DESIGN.md 2026-08-10): プロファイル(OS×GPUクラス)は初回起動で1回
検出してDBに保存し、以後は再検出操作でのみ変わる。エンジン構成の対応表は
コードが持つため、DBに残った旧 asr_engine 等のキーは意味を失う。
毎起動の冪等DELETEで掃除する(v0.9.5の固定保存事故の再発防止も兼ねる)。
"""

import json

import pytest

from backend.core import hwprofile
from backend.core.hwprofile import HwProfile
from backend.models import schema


@pytest.fixture
def conn(tmp_path):
    c = schema.init_db(tmp_path / "t.db")
    yield c
    c.close()


@pytest.fixture(autouse=True)
def reset_current():
    """プロセス内キャッシュをテストごとに戻す"""
    hwprofile.set_current(None)
    yield
    hwprofile.set_current(None)


FIXED = HwProfile(os="linux", gpu="nvidia", gpu_name="RTX", vram_total_mb=8000,
                  whispercpp_ok=True, detected_at="2026-08-10T00:00:00")


def _saved(conn) -> dict | None:
    row = conn.execute(
        "SELECT value_json FROM app_settings WHERE key=?", (hwprofile.PROFILE_KEY,)
    ).fetchone()
    return json.loads(row["value_json"]) if row else None


# ---- 初回検出と保存 ----
def test_初回はプロファイルを検出して保存する(conn):
    profile = hwprofile.ensure_profile(conn, detector=lambda: FIXED)
    assert profile == FIXED
    assert _saved(conn)["gpu"] == "nvidia"


def test_保存済みなら再検出しない(conn):
    """「最初に認識した環境で固定」— 起動のたびに検出し直さない"""
    hwprofile.save_profile(conn, FIXED)

    def never():
        raise AssertionError("保存済みなのに検出が走った")

    assert hwprofile.ensure_profile(conn, detector=never) == FIXED


def test_ensureはプロセス内の現在値も確定させる(conn):
    hwprofile.ensure_profile(conn, detector=lambda: FIXED)
    assert hwprofile.current() == FIXED


def test_再検出は明示操作でのみ上書きする(conn):
    hwprofile.save_profile(conn, FIXED)
    newer = HwProfile(os="linux", gpu="cpu", detected_at="2026-08-11T00:00:00")
    got = hwprofile.redetect(conn, detector=lambda: newer)
    assert got == newer
    assert _saved(conn)["gpu"] == "cpu"
    assert hwprofile.current() == newer


def test_壊れた保存値は読み捨てて検出し直す(conn):
    """手で書き換えられたJSONで起動不能にならない"""
    conn.execute(
        "INSERT INTO app_settings (key, value_json) VALUES (?, 'not-json')",
        (hwprofile.PROFILE_KEY,),
    )
    conn.commit()
    assert hwprofile.ensure_profile(conn, detector=lambda: FIXED) == FIXED


# ---- 旧設定キーの掃除(毎起動・冪等) ----
REMOVED_KEYS = ("asr_engine", "asr_compute_type", "diarization_engine",
                "_migrated_asr_engine_auto")


def test_旧キーは起動時に掃除される(tmp_path):
    db = tmp_path / "t.db"
    c = schema.init_db(db)
    for key in REMOVED_KEYS:
        c.execute(
            "INSERT INTO app_settings (key, value_json) VALUES (?, '\"x\"')"
            " ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json",
            (key,),
        )
    c.commit()
    c.close()

    c = schema.init_db(db)
    try:
        remaining = {r["key"] for r in c.execute("SELECT key FROM app_settings")}
        assert not (remaining & set(REMOVED_KEYS))
    finally:
        c.close()


def test_掃除は他の設定を触らない(tmp_path):
    db = tmp_path / "t.db"
    c = schema.init_db(db)
    c.execute(
        "INSERT INTO app_settings (key, value_json) VALUES ('asr_model', '\"large-v3\"')"
    )
    c.commit()
    c.close()

    c = schema.init_db(db)
    try:
        row = c.execute(
            "SELECT value_json FROM app_settings WHERE key='asr_model'"
        ).fetchone()
        assert row["value_json"] == '"large-v3"'
    finally:
        c.close()


def test_プロファイルは設定APIから書き換えられない():
    """書き込み経路は検出コードと再検出APIだけに限定する"""
    from backend.core.project_settings import MUTABLE_FIELDS

    assert hwprofile.PROFILE_KEY not in MUTABLE_FIELDS


def test_プロファイルは掃除の対象にならない(tmp_path):
    db = tmp_path / "t.db"
    c = schema.init_db(db)
    hwprofile.save_profile(c, FIXED)
    c.close()

    c = schema.init_db(db)
    try:
        assert hwprofile.load_profile(c) == FIXED
    finally:
        c.close()
