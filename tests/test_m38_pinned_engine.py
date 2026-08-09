"""M38: 初回セットアップが固定したASRエンジンを一度だけ解除する。

v0.9.5のウィザードは「推奨設定を適用」で asr_engine を具体名(faster_whisper)で
保存していた。その後 whisper.cpp を同梱してもエンジン選択がその値に固定された
ままになり、GPUがあっても遅いエンジンが使われ続けた(実機で確認)。

利用者が選んだ値ではなくこちらが書いた値なので、一度だけ解除して auto に戻す。
以降に利用者が明示的に選んだ値は残す。
"""

from backend.models import schema


def _settings(conn) -> dict:
    return {r["key"]: r["value_json"] for r in conn.execute("SELECT key, value_json FROM app_settings")}


def test_固定されたエンジンを外す(tmp_path):
    db = tmp_path / "t.db"
    conn = schema.init_db(db)
    conn.execute(
        "INSERT INTO app_settings (key, value_json) VALUES ('asr_engine', '\"faster_whisper\"')"
        " ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json"
    )
    # 移行済みの記録を消して、旧バージョンから上げた状態を作る
    conn.execute("DELETE FROM app_settings WHERE key=?", (schema._ASR_ENGINE_MIGRATION,))
    conn.commit()
    conn.close()

    conn = schema.init_db(db)
    try:
        assert "asr_engine" not in _settings(conn), "固定が残っている(autoに戻らない)"
    finally:
        conn.close()


def test_解除は一度だけ(tmp_path):
    """あとから利用者が選んだ値は消さない"""
    db = tmp_path / "t.db"
    conn = schema.init_db(db)  # ここで移行済みの記録が付く
    conn.execute(
        "INSERT INTO app_settings (key, value_json) VALUES ('asr_engine', '\"whispercpp\"')"
        " ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json"
    )
    conn.commit()
    conn.close()

    conn = schema.init_db(db)
    try:
        assert _settings(conn).get("asr_engine") == '"whispercpp"', "利用者の選択を消している"
    finally:
        conn.close()


def test_他の設定は触らない(tmp_path):
    db = tmp_path / "t.db"
    conn = schema.init_db(db)
    conn.execute("DELETE FROM app_settings WHERE key=?", (schema._ASR_ENGINE_MIGRATION,))
    for key, value in [("asr_model", '"large-v3"'), ("llm_provider", '"gemini"')]:
        conn.execute(
            "INSERT INTO app_settings (key, value_json) VALUES (?,?)"
            " ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json",
            (key, value),
        )
    conn.commit()
    conn.close()

    conn = schema.init_db(db)
    try:
        got = _settings(conn)
        assert got["asr_model"] == '"large-v3"'
        assert got["llm_provider"] == '"gemini"'
    finally:
        conn.close()


def test_記録キーは設定として読み込まれない(tmp_path):
    """MUTABLE_FIELDS 外なので設定に混ざらない"""
    from backend.core.project_settings import MUTABLE_FIELDS

    assert schema._ASR_ENGINE_MIGRATION not in MUTABLE_FIELDS
