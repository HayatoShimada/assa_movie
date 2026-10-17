"""利用者の辞書(名前・用語)。プロジェクトや動画をまたいで使う。

質問タブで答えた固有名詞の正しい表記を覚えておき、次の文字起こしでWhisperに
ヒントとして渡す(backend/engines/asr/prompt.py)。設定タブの「名前・用語の辞書」で
見て・足して・直して・消せる。

- 1語1行。同じ語(正規化して同じもの)は1件にまとめ、確認された回数(hits)を足す
- 以前どう聞き間違えられたか(misrecognitions)も持つ。次の動画のスキャンで
  同じ聞き間違いが出たら、AIに聞かずに質問として出す(find_misrecognitions)
- 並び順 = Whisperに渡す優先順(よく確認された語 → 最近の語)。
  上限があるので、画面でも「上から順に使う」と説明する

プロジェクトの用語集(glossary)は指示語置換などLLMのプロンプト用として残す。
文字起こしに効くのはこの辞書だけ(画面で消した語が裏で効き続けないように)。
"""

import json
import re
import sqlite3
import unicodedata
from collections.abc import Iterable

# 1語の長さの上限。これより長いものは語ではなく文なので、プロンプトの枠を浪費する
MAX_TERM_LENGTH = 40
# 1語あたり覚えておく聞き間違いの数(古いものから捨てる)
MAX_MISRECOGNITIONS = 10

SOURCES = ("question", "manual", "glossary")

_ORDER = "ORDER BY hits DESC, updated_at DESC, id DESC"


class InvalidTermError(ValueError):
    """空・長すぎる語"""


class DuplicateTermError(ValueError):
    """別の行に同じ語がすでにある"""


# ---- 純関数 ----

def normalize_term(text: str) -> str:
    """表記を揃える: NFKC(全角英数→半角・半角カナ→全角)・前後の空白・連続空白"""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text or "")).strip()


def validate_term(text: str) -> str:
    term = normalize_term(text)
    if not term:
        raise InvalidTermError("語が空です")
    if len(term) > MAX_TERM_LENGTH:
        raise InvalidTermError(f"語が長すぎます({MAX_TERM_LENGTH}文字まで)")
    return term


def merge_misrecognitions(
    existing: Iterable[str], new: Iterable[str], term: str
) -> list[str]:
    """聞き間違いの一覧に新しいものを足す(正規化・重複除去・正しい表記は除く)。

    上限を超えたら古いものから捨てる。
    """
    out: list[str] = []
    for raw in [*existing, *new]:
        wrong = normalize_term(raw)
        if wrong and wrong != term and wrong not in out:
            out.append(wrong)
    return out[-MAX_MISRECOGNITIONS:]


def find_misrecognitions(
    text: str, entries: Iterable[tuple[str, list[str]]]
) -> list[tuple[str, str, int]]:
    """本文に出ている「以前の聞き間違い」を探す。

    entries は (正しい表記, 聞き間違いの一覧)。戻り値は (聞き間違い, 正しい表記, 出現回数)。
    聞き間違いが正しい表記の一部のとき(ハコスト → ハコストア)は、
    正しい表記の中に出ているものは数えない。
    """
    found: list[tuple[str, str, int]] = []
    for term, wrongs in entries:
        rest = text.replace(term, "\0")
        for wrong in wrongs:
            if not wrong or wrong == term:
                continue
            count = rest.count(wrong)
            if count:
                found.append((wrong, term, count))
    return found



def replace_misrecognition(text: str, wrong: str, right: str) -> str:
    """本文の聞き間違いを正しい表記に直す(純関数)。

    既に正しく書けている箇所は触らない。聞き間違いが正しい表記の一部のとき
    (ハコスト → ハコストア)、単純な置換だと「ハコストア」が「ハコストアア」になる。
    正しい表記の出現で区切り、その間だけを置き換える(find_misrecognitions と同じ考え方)。
    """
    if not wrong or wrong == right:
        return text
    return right.join(part.replace(wrong, right) for part in text.split(right))

# ---- DB ----

def _to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["misrecognitions"] = json.loads(d.pop("misrecognitions_json") or "[]")
    return d


def _get(conn: sqlite3.Connection, term_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM user_terms WHERE id=?", (term_id,)).fetchone()
    return _to_dict(row) if row else None


def list_terms(conn: sqlite3.Connection) -> list[dict]:
    """辞書の全語を優先順(=Whisperに渡す順)で返す"""
    return [_to_dict(r) for r in conn.execute(f"SELECT * FROM user_terms {_ORDER}")]


def prompt_terms(conn: sqlite3.Connection) -> list[str]:
    """Whisperに渡す候補の語(優先順)。上限で切るのは prompt.select_prompt_terms"""
    return [r["term"] for r in conn.execute(f"SELECT term FROM user_terms {_ORDER}")]


def add_term(
    conn: sqlite3.Connection,
    term: str,
    misrecognitions: Iterable[str] = (),
    source: str = "manual",
    *,
    commit: bool = True,
) -> dict:
    """語を足す。すでにあれば1件にまとめ、確認回数を足して聞き間違いを合わせる"""
    term = validate_term(term)
    if source not in SOURCES:
        raise ValueError(f"未知の登録元: {source}")
    row = conn.execute("SELECT * FROM user_terms WHERE term=?", (term,)).fetchone()
    if row is None:
        merged = merge_misrecognitions([], misrecognitions, term)
        cur = conn.execute(
            "INSERT INTO user_terms (term, misrecognitions_json, source) VALUES (?,?,?)",
            (term, json.dumps(merged, ensure_ascii=False), source),
        )
        term_id = cur.lastrowid
    else:
        merged = merge_misrecognitions(
            json.loads(row["misrecognitions_json"] or "[]"), misrecognitions, term
        )
        conn.execute(
            "UPDATE user_terms SET hits=hits+1, misrecognitions_json=?,"
            " updated_at=datetime('now') WHERE id=?",
            (json.dumps(merged, ensure_ascii=False), row["id"]),
        )
        term_id = row["id"]
    if commit:
        conn.commit()
    return _get(conn, term_id)


def update_term(
    conn: sqlite3.Connection,
    term_id: int,
    term: str | None = None,
    misrecognitions: Iterable[str] | None = None,
) -> dict:
    """表記や聞き間違いを直す。無ければKeyError、別の行と同じ語になるならDuplicateTermError"""
    current = _get(conn, term_id)
    if current is None:
        raise KeyError(term_id)
    new_term = validate_term(term) if term is not None else current["term"]
    if new_term != current["term"] and conn.execute(
        "SELECT 1 FROM user_terms WHERE term=? AND id<>?", (new_term, term_id)
    ).fetchone():
        raise DuplicateTermError(f"「{new_term}」はすでに辞書にあります")
    wrongs = current["misrecognitions"] if misrecognitions is None else []
    merged = merge_misrecognitions(
        wrongs, misrecognitions if misrecognitions is not None else [], new_term
    )
    conn.execute(
        "UPDATE user_terms SET term=?, misrecognitions_json=?, updated_at=datetime('now')"
        " WHERE id=?",
        (new_term, json.dumps(merged, ensure_ascii=False), term_id),
    )
    conn.commit()
    return _get(conn, term_id)


def delete_term(conn: sqlite3.Connection, term_id: int) -> bool:
    cur = conn.execute("DELETE FROM user_terms WHERE id=?", (term_id,))
    conn.commit()
    return cur.rowcount > 0


# 回答で用語集に登録したときの説明文(terms_job.apply_term_answer)から聞き間違いを取り出す
_GLOSSARY_NOTE = re.compile(r"「(.+?)」と誤認識")


def migrate_from_glossary(conn: sqlite3.Connection) -> int:
    """辞書が無かった頃にプロジェクトの用語集へ入った語を、辞書へ移す。

    schema.init_db が辞書の表を**初めて作ったときだけ**呼ぶ。毎回呼ぶと、
    利用者が辞書から消した語が用語集から戻ってきてしまう。
    """
    moved = 0
    for row in conn.execute("SELECT term, description FROM glossary ORDER BY id").fetchall():
        match = _GLOSSARY_NOTE.search(row["description"] or "")
        try:
            add_term(
                conn, row["term"],
                misrecognitions=[match.group(1)] if match else [],
                source="glossary", commit=False,
            )
            moved += 1
        except InvalidTermError:
            continue
    return moved
