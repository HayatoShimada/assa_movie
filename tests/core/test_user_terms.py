"""利用者の辞書(名前・用語)のテスト。

質問タブで答えた固有名詞の正しい表記を、プロジェクトや動画をまたいで覚えておき、
次の文字起こしでWhisperに渡す。ここでは保存・重複の扱い・優先順・移行を見る。
"""

import pytest

from backend.core import user_terms
from backend.core.user_terms import (
    DuplicateTermError,
    InvalidTermError,
    find_misrecognitions,
    merge_misrecognitions,
    normalize_term,
    replace_misrecognition,
)
from backend.models import schema


@pytest.fixture
def db(tmp_path):
    conn = schema.init_db(tmp_path / "test.db")
    yield conn
    conn.close()


# ---- 正規化(純関数) ----

@pytest.mark.parametrize(
    "raw, expected",
    [
        ("半導体", "半導体"),
        ("  半導体　", "半導体"),        # 全角空白も落とす
        ("ＮＶＩＤＩＡ", "NVIDIA"),       # 全角英字は半角に揃える(Whisperの出力に合わせる)
        ("ｷﾘﾇｷ", "キリヌキ"),            # 半角カナは全角に
        ("Kirinuki   Studio", "Kirinuki Studio"),  # 連続空白は1つに
    ],
)
def test_normalize_term(raw, expected):
    assert normalize_term(raw) == expected


@pytest.mark.parametrize("raw", ["", "   ", "　", "あ" * 41])
def test_空や長すぎる語は登録できない(raw, db):
    with pytest.raises(InvalidTermError):
        user_terms.add_term(db, raw)


@pytest.mark.parametrize(
    "existing, new, term, expected",
    [
        ([], ["反動体"], "半導体", ["反動体"]),
        (["反動体"], ["反動体"], "半導体", ["反動体"]),            # 重複しない
        (["反動体"], ["はんどう体"], "半導体", ["反動体", "はんどう体"]),
        ([], ["半導体", " ", ""], "半導体", []),                   # 正しい表記そのものと空は除く
        ([], ["ＡＢＣ"], "x", ["ABC"]),                            # 正規化してから比べる
    ],
)
def test_merge_misrecognitions(existing, new, term, expected):
    assert merge_misrecognitions(existing, new, term) == expected


def test_聞き間違いは新しいものを残して上限で切る():
    many = [f"誤{i}" for i in range(15)]
    merged = merge_misrecognitions([], many, "正")
    assert len(merged) == user_terms.MAX_MISRECOGNITIONS
    assert merged[-1] == "誤14"


# ---- 保存と重複 ----

def test_追加すると一覧に載る(db):
    row = user_terms.add_term(db, "半導体", misrecognitions=["反動体"], source="question")
    assert row["term"] == "半導体"
    assert row["misrecognitions"] == ["反動体"]
    assert row["source"] == "question"
    assert [t["term"] for t in user_terms.list_terms(db)] == ["半導体"]


def test_同じ語は1件にまとめ回数と聞き間違いを足す(db):
    user_terms.add_term(db, "半導体", misrecognitions=["反動体"])
    row = user_terms.add_term(db, "半導体", misrecognitions=["はんどう体"])
    assert len(user_terms.list_terms(db)) == 1
    assert row["hits"] == 2
    assert row["misrecognitions"] == ["反動体", "はんどう体"]


def test_表記ゆれ程度の違いは同じ語として扱う(db):
    user_terms.add_term(db, "ＮＶＩＤＩＡ")
    user_terms.add_term(db, " NVIDIA ")
    assert [t["term"] for t in user_terms.list_terms(db)] == ["NVIDIA"]


def test_よく確認された語ほど上に並ぶ(db):
    user_terms.add_term(db, "古着")
    user_terms.add_term(db, "半導体")
    user_terms.add_term(db, "半導体")
    user_terms.add_term(db, "はやまる")
    terms = [t["term"] for t in user_terms.list_terms(db)]
    assert terms[0] == "半導体"  # 2回確認された
    # 同じ回数なら新しく足したものが先
    assert terms[1:] == ["はやまる", "古着"]
    assert user_terms.prompt_terms(db) == terms


def test_修正できる(db):
    row = user_terms.add_term(db, "反動体")
    updated = user_terms.update_term(db, row["id"], term="半導体", misrecognitions=["反動体"])
    assert updated["term"] == "半導体"
    assert updated["misrecognitions"] == ["反動体"]


def test_既にある語への修正は重複として断る(db):
    user_terms.add_term(db, "半導体")
    row = user_terms.add_term(db, "反動体")
    with pytest.raises(DuplicateTermError):
        user_terms.update_term(db, row["id"], term="半導体")


def test_存在しない語の修正と削除(db):
    with pytest.raises(KeyError):
        user_terms.update_term(db, 999, term="x")
    assert user_terms.delete_term(db, 999) is False


def test_削除できる(db):
    row = user_terms.add_term(db, "半導体")
    assert user_terms.delete_term(db, row["id"]) is True
    assert user_terms.list_terms(db) == []


def test_辞書はプロジェクトを消しても残る(db):
    """利用者単位(全プロジェクト共通)なので、プロジェクトに紐づけない"""
    pid = db.execute("INSERT INTO projects (name) VALUES ('p')").lastrowid
    user_terms.add_term(db, "半導体")
    db.execute("DELETE FROM projects WHERE id=?", (pid,))
    db.commit()
    assert [t["term"] for t in user_terms.list_terms(db)] == ["半導体"]


# ---- 以前の聞き間違いを本文から探す(純関数) ----

@pytest.mark.parametrize(
    "text, entries, expected",
    [
        ("反動体を作ってる\n反動体って何", [("半導体", ["反動体"])], [("反動体", "半導体", 2)]),
        ("半導体を作ってる", [("半導体", ["反動体"])], []),
        ("", [("半導体", ["反動体"])], []),
        # 聞き間違いが正しい表記の一部なら、正しい表記の中は数えない
        ("ハコストアとハコストに行った", [("ハコストア", ["ハコスト"])],
         [("ハコスト", "ハコストア", 1)]),
        ("ハコストアに行った", [("ハコストア", ["ハコスト"])], []),
        # 複数の語・複数の聞き間違い
        ("反動体と分泌家", [("半導体", ["反動体"]), ("文筆家", ["分泌家", "文筆か"])],
         [("反動体", "半導体", 1), ("分泌家", "文筆家", 1)]),
    ],
)
def test_find_misrecognitions(text, entries, expected):
    assert find_misrecognitions(text, entries) == expected


# ---- 旧データ(プロジェクトの用語集)からの移行 ----

def test_初回だけプロジェクトの用語集を辞書へ移す(tmp_path):
    path = tmp_path / "old.db"
    conn = schema.init_db(path)
    # 辞書が入る前のDBを再現する
    conn.execute("DROP TABLE user_terms")
    pid = conn.execute("INSERT INTO projects (name) VALUES ('p')").lastrowid
    conn.execute(
        "INSERT INTO glossary (project_id, term, description) VALUES (?,?,?)",
        (pid, "半導体", "文字起こしで「反動体」と誤認識されることがある"),
    )
    conn.execute(
        "INSERT INTO glossary (project_id, term, description) VALUES (?,?,?)",
        (pid, "箱ストア", None),
    )
    conn.commit()
    conn.close()

    conn = schema.init_db(path)
    rows = {t["term"]: t for t in user_terms.list_terms(conn)}
    assert set(rows) == {"半導体", "箱ストア"}
    assert rows["半導体"]["misrecognitions"] == ["反動体"]
    assert rows["半導体"]["source"] == "glossary"

    # 利用者が消した語が、次の起動で用語集から戻ってきてはいけない
    user_terms.delete_term(conn, rows["半導体"]["id"])
    conn.close()
    conn = schema.init_db(path)
    assert [t["term"] for t in user_terms.list_terms(conn)] == ["箱ストア"]
    conn.close()


# ---- 回答の適用(聞き間違い → 正しい表記) ----
#
# 聞き間違いが正しい表記の一部のとき(ハコスト → ハコストア)、単純な置換だと
# 既に正しい「ハコストア」まで「ハコストアア」にしてしまう。
@pytest.mark.parametrize("text,wrong,right,expected", [
    ("反動体を作る", "反動体", "半導体", "半導体を作る"),
    ("反動体と反動体", "反動体", "半導体", "半導体と半導体"),
    ("ハコストに行った", "ハコスト", "ハコストア", "ハコストアに行った"),
    ("ハコストアに行った", "ハコスト", "ハコストア", "ハコストアに行った"),
    ("ハコストとハコストア", "ハコスト", "ハコストア", "ハコストアとハコストア"),
    ("ハコストアとハコスト", "ハコスト", "ハコストア", "ハコストアとハコストア"),
    # 正しい表記が聞き間違いの一部(ストア → ハコストア)でも二重にならない
    ("ハコストアのストア", "ストア", "ハコストア", "ハコストアのハコストア"),
    ("関係ない文", "反動体", "半導体", "関係ない文"),
    ("", "反動体", "半導体", ""),
])
def test_replace_misrecognition(text, wrong, right, expected):
    assert replace_misrecognition(text, wrong, right) == expected
