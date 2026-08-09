"""テスト間で共有する組み立て。

同じ形の下準備が何度もコピーされていた(プロジェクト+メディアの作成が5回、
FakeLLMの差し替えが5回)。片方だけ直しても気付けないので1箇所にまとめる。

`conftest.py` ではなく普通のモジュールにしてあるのは、fixtureではなく
引数付きの関数として呼びたいものが混ざるため(use_fake など)。
"""

import sqlite3

from backend.engines.llm.base import FakeLLMClient
from backend.jobs import resolve_job


def create_media(client, tmp_path, name: str = "p") -> dict:
    """プロジェクトとメディアを1件ずつ作る。セグメントは呼び出し側で入れる。

    メディアの実体(音声)は要らないが、登録APIが存在を確かめるので空で置く。
    """
    project_id = client.post("/api/projects", json={"name": name}).json()["id"]
    path = tmp_path / "a.wav"
    path.write_bytes(b"x")
    media_id = client.post(
        f"/api/projects/{project_id}/media", json={"path": str(path)}
    ).json()["id"]
    return {"project_id": project_id, "media_id": media_id}


def insert_segments(db: sqlite3.Connection, media_id: int, rows: list[dict]) -> None:
    """セグメントをまとめて入れる。rowsのキーはsegmentsの列名。

    text だけ渡せば original_text と時刻は埋める(**original_text は常に原文を
    保持する**という決まりがあるので、テストでも空にしない)。
    """
    for idx, row in enumerate(rows):
        values = {
            "media_id": media_id,
            "idx": idx,
            "start": float(idx),
            "end": float(idx) + 1.0,
            "original_text": row.get("text", ""),
            **row,
        }
        columns = ", ".join(values)
        placeholders = ", ".join("?" * len(values))
        db.execute(
            f"INSERT INTO segments ({columns}) VALUES ({placeholders})",
            tuple(values.values()),
        )
    db.commit()


def use_fake(responses) -> FakeLLMClient:
    """LLMをFakeに差し替える。

    実LLMに依存したテストは書かない(CLAUDE.md)。差し替えたままにならないよう、
    後始末は conftest.py の autouse fixture が行う。
    """
    fake = FakeLLMClient(responses=responses)
    resolve_job.set_client_factory(lambda: fake)
    return fake
