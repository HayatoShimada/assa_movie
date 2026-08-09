"""M40: 効いていない設定を消す。

UIに出ているのにバックエンドがどこからも読んでいない項目があった。
利用者から見ると「切ったのに効かない」で、実装から見ると「あるように見えて無い」。
どちらにとっても嘘なので、実態に合わせて消す。

| 消したもの | なぜ効いていなかったか |
|---|---|
| aizuchi_filter_enabled | 相槌は subtitle.py で常に除外される。切っても除外される |
| subtitle_mode | 参照ゼロ。all/selective のどちらでも出力が変わらない |
| subtitle_max_lines | 参照ゼロ。行数は max_chars_per_line の折り返しだけで決まる |
| pronoun_enabled | 参照ゼロ。OFFにしても指示語置換のジョブは走る |
| max_replacement_len | Settings側は残骸。実体は pronoun.py の LEVELS が持つ |

消したあとも、古いDBに残った値で壊れないことを確かめる。
"""

import json

import pytest

from backend.core.config import Settings
from backend.core.project_settings import (
    MUTABLE_FIELDS,
    load_global_overrides,
    project_overrides,
)
from backend.models import schema

REMOVED = [
    "aizuchi_filter_enabled",
    "subtitle_mode",
    "subtitle_max_lines",
    "pronoun_enabled",
    "max_replacement_len",
]


@pytest.mark.parametrize("name", REMOVED)
def test_設定から消えている(name):
    assert name not in Settings.model_fields, f"{name} が残っている"
    assert name not in MUTABLE_FIELDS


@pytest.mark.parametrize("name", REMOVED)
def test_古いDBに残っていても壊れない(tmp_path, name):
    """既に使っている人のDBには値が入っている。読み飛ばすだけにする"""
    conn = schema.init_db(tmp_path / "t.db")
    try:
        conn.execute(
            "INSERT INTO app_settings (key, value_json) VALUES (?,?)"
            " ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json",
            (name, json.dumps(False)),
        )
        conn.commit()
        load_global_overrides(conn)  # 例外を投げないこと
    finally:
        conn.close()


@pytest.mark.parametrize("name", REMOVED)
def test_プロジェクトの差分に残っていても無視される(tmp_path, name):
    conn = schema.init_db(tmp_path / "t.db")
    try:
        cur = conn.execute(
            "INSERT INTO projects (name, settings_json) VALUES ('p', ?)",
            (json.dumps({name: False, "asr_model": "large-v3-turbo"}),),
        )
        conn.commit()
        got = project_overrides(conn, cur.lastrowid)
        assert name not in got
        assert got["asr_model"] == "large-v3-turbo", "生きている項目まで落とさない"
    finally:
        conn.close()


def test_採用率は残す():
    """subtitle_mode は消すが、採用率は judge_job が実際に読んでいる"""
    assert "subtitle_adoption_rate" in Settings.model_fields
    assert "subtitle_adoption_rate" in MUTABLE_FIELDS


def test_置換の長さ上限は積極性から決まる():
    """max_replacement_len の実体。設定から消しても判定は変わらない"""
    from backend.pipeline.pronoun import LEVELS

    assert LEVELS["weak"].max_replacement_len < LEVELS["strong"].max_replacement_len


def test_UIに消した項目が残っていない():
    """設定画面に出したままだと「切ったのに効かない」が再発する"""
    from pathlib import Path

    source = Path("frontend/src/components/settings/SettingsFields.tsx").read_text(
        encoding="utf-8"
    )
    残り = [name for name in REMOVED if name in source]
    assert not 残り, f"UIに残っている: {残り}"
