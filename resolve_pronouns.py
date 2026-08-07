#!/usr/bin/env python3
"""
指示語(これ・それ・あれ等)を指す内容に置き換える後処理スクリプト。
ローカルLLM(Ollama)で文脈から参照先を解決し、完全置換+変更ログを出力する。

使い方:
  uv run python resolve_pronouns.py <ベース名>          # 例: uv run python resolve_pronouns.py 雑談編
  uv run python resolve_pronouns.py <ベース名> --limit 100  # 冒頭100行だけ処理(試験用)

入力:  <ベース名>.txt / <ベース名>.srt (transcribe.pyの出力。行とブロックが1対1対応)
出力:  <ベース名>_置換済.txt / <ベース名>_置換済.srt / <ベース名>_置換ログ.txt
       (元ファイルは変更しない)

事前に Ollama サーバーが起動していること: ollama serve
"""

import difflib
import json
import re
import sys
import time
from pathlib import Path

import requests

# ---- 設定 ----
OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL = "qwen3:32b"          # より高精度を試すなら "gpt-oss:120b" 等に変更
CHUNK_SIZE = 30              # 一度にLLMへ渡す編集対象の行数
CONTEXT_SIZE = 15            # 参照用として前置する直前の行数
MAX_REPLACEMENT_LEN = 40     # これより長い置換文字列は暴走とみなしてスキップ
RETRIES = 3

# 指示語を含むが置換対象にしない慣用表現・複合語
IDIOM_WORDS = (
    "この世", "この間", "このように", "この前", "この後", "このまま",
    "これから", "これまで", "これで", "それぞれ", "それなり", "それでも",
    "それに", "そのまま", "その後", "そのうち", "その通り", "その分",
    "あれこれ", "あれから",
)

EDITS_SCHEMA = {
    "type": "object",
    "properties": {
        "edits": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "line": {"type": "integer"},
                    "original": {"type": "string"},
                    "replacement": {"type": "string"},
                },
                "required": ["line", "original", "replacement"],
            },
        }
    },
    "required": ["edits"],
}

SYSTEM_PROMPT = """あなたは対談の文字起こしを校正する編集者です。
与えられた発言の中の指示語(これ・それ・あれ・この・その・あの・ここ・そこ・こういう・そういう・ああいう 等)のうち、
**指している内容が文脈から明確に特定できるものだけ**を、指す内容に置き換える編集案をJSONで出力してください。

厳守するルール:
1. 参照先が文脈から一意に明確な指示語だけを置き換える。少しでも曖昧なら編集を出さない。
2. 言い淀み・フィラーとしての「あの」「その」「なんかこう」「こう」は絶対に置き換えない。
   (例:「あの、それでですね」の「あの」はフィラー)
3. 画面・スライド・その場の物など、映像を見ないと分からないものを指す指示語は置き換えない。
4. original は対象行に実際に含まれる連続した文字列を、指示語を含む最小限の範囲で指定する。
5. replacement は置き換えても文が自然につながる表現にする。発言の意味を変えない。
6. 指示語の解決以外の編集(言い回しの修正、誤字修正など)は一切しない。
7. **指示語を単に削除するだけの編集は禁止**。replacement には指している内容を表す具体的な語句を必ず含めること。
   (悪い例: 「そのAI」→「AI」、「その人」→「人」 … 参照先を明示していないので出さない)
8. 慣用表現・複合語(この世・この間・これから・これまで・それぞれ・そのまま・その後・そのうち 等)は指示語として扱わない。
9. 人称代名詞(僕・私・俺・あなた・彼・彼女)は置き換えない。話者の名前への置き換えも禁止。
10. 参照先の語が同じ行の中に既に出ている場合は置き換えない(重複した文になるため)。
7. 「編集対象」とマークされた行だけを編集する。「文脈(参照用)」の行は編集しない。
8. 置き換えるべきものが無ければ {"edits": []} を返す。

出力形式: {"edits": [{"line": 行番号, "original": "置換前", "replacement": "置換後"}]}"""


def inserted_chunks(orig: str, repl: str) -> list[str]:
    """origをreplに変えたとき新たに挿入される文字列の一覧"""
    sm = difflib.SequenceMatcher(None, orig, repl)
    return [
        repl[j1:j2]
        for tag, _, _, j1, j2 in sm.get_opcodes()
        if tag in ("replace", "insert")
    ]


def parse_srt(path: Path):
    """SRTを (番号行, 時刻行, 本文) のリストにパースする"""
    blocks = []
    raw = path.read_text(encoding="utf-8").strip()
    for block in re.split(r"\n\n+", raw):
        lines = block.split("\n")
        if len(lines) < 3:
            continue
        blocks.append((lines[0], lines[1], "\n".join(lines[2:])))
    return blocks


def call_ollama(messages, retries=RETRIES):
    last_error = None
    for attempt in range(retries):
        try:
            resp = requests.post(
                OLLAMA_URL,
                json={
                    "model": MODEL,
                    "messages": messages,
                    "stream": False,
                    "format": EDITS_SCHEMA,
                    "think": False,
                    "options": {"temperature": 0, "num_ctx": 8192},
                },
                timeout=600,
            )
            resp.raise_for_status()
            content = resp.json()["message"]["content"]
            return json.loads(content)["edits"]
        except Exception as e:  # 接続断・JSON不正など。リトライで解消することが多い
            last_error = e
            time.sleep(2)
    raise RuntimeError(f"Ollama呼び出しに{retries}回失敗: {last_error}")


def build_chunk_prompt(lines, start, end):
    """start〜end-1行目(0始まり)を編集対象、その直前を文脈としてプロンプトを組む"""
    parts = []
    ctx_start = max(0, start - CONTEXT_SIZE)
    if ctx_start < start:
        parts.append("## 文脈(参照用・編集禁止)")
        for i in range(ctx_start, start):
            parts.append(f"{i + 1}: {lines[i]}")
    parts.append("## 編集対象")
    for i in range(start, end):
        parts.append(f"{i + 1}: {lines[i]}")
    return "\n".join(parts)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        print("使い方: uv run python resolve_pronouns.py <ベース名> [--limit N]")
        sys.exit(1)
    base = Path(args[0].removesuffix(".txt").removesuffix(".srt"))
    limit = None
    for a in sys.argv[1:]:
        if a.startswith("--limit"):
            limit = int(a.split("=")[1]) if "=" in a else int(sys.argv[sys.argv.index(a) + 1])

    txt_path = base.with_suffix(".txt")
    srt_path = base.with_suffix(".srt")
    lines = txt_path.read_text(encoding="utf-8").rstrip("\n").split("\n")
    srt_blocks = parse_srt(srt_path)

    if len(lines) != len(srt_blocks):
        print(f"エラー: {txt_path}({len(lines)}行)と{srt_path}({len(srt_blocks)}ブロック)が対応していません。")
        sys.exit(1)
    mismatch = sum(1 for l, b in zip(lines, srt_blocks) if l != b[2])
    if mismatch:
        print(f"エラー: .txtと.srtで本文が一致しない行が{mismatch}件あります。同じ実行で生成されたペアを指定してください。")
        sys.exit(1)

    total = min(limit, len(lines)) if limit else len(lines)
    print(f"モデル: {MODEL} / 対象: {total}行(全{len(lines)}行)")

    edited = list(lines)
    applied, skipped = [], []

    for start in range(0, total, CHUNK_SIZE):
        end = min(start + CHUNK_SIZE, total)
        print(f"処理中: {start + 1}〜{end}行目...", flush=True)
        prompt = build_chunk_prompt(lines, start, end)
        edits = call_ollama([
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ])

        for e in edits:
            n = e.get("line", 0)
            orig, repl = str(e.get("original", "")), str(e.get("replacement", ""))
            reason = None
            if not (start + 1 <= n <= end):
                reason = "編集対象範囲外の行番号"
            elif not orig or not repl or orig == repl:
                reason = "空または無変更の編集"
            elif len(repl) > MAX_REPLACEMENT_LEN:
                reason = f"置換文字列が長すぎる({len(repl)}文字)"
            elif any(w in orig for w in IDIOM_WORDS):
                reason = "慣用表現のため対象外"
            elif orig not in edited[n - 1]:
                reason = "置換前文字列が行内に存在しない"
            else:
                inserted = [c for c in inserted_chunks(orig, repl) if len(c) >= 2]
                rest_of_line = edited[n - 1].replace(orig, "", 1)
                # 挿入文字列の3文字窓が行内に既出なら、参照先が重複する編集とみなす
                windows = [
                    c[i:i + 3] if len(c) > 3 else c
                    for c in inserted
                    for i in range(max(1, len(c) - 2))
                ]
                if not inserted:
                    reason = "指示語の削除のみ(参照先の明示がない)"
                elif any(w in rest_of_line for w in windows):
                    reason = "参照先が同じ行に既出(重複になる)"
            if reason:
                skipped.append((n, orig, repl, reason))
                continue
            edited[n - 1] = edited[n - 1].replace(orig, repl, 1)
            applied.append((n, orig, repl))

    # ---- 出力 ----
    out_txt = base.parent / f"{base.name}_置換済.txt"
    out_srt = base.parent / f"{base.name}_置換済.srt"
    out_log = base.parent / f"{base.name}_置換ログ.txt"

    out_txt.write_text("\n".join(edited) + "\n", encoding="utf-8")
    with open(out_srt, "w", encoding="utf-8") as f:
        for (num, ts, _), text in zip(srt_blocks, edited):
            f.write(f"{num}\n{ts}\n{text}\n\n")

    with open(out_log, "w", encoding="utf-8") as f:
        f.write(f"# 置換ログ: {base.name} (モデル: {MODEL}, 対象: {total}行)\n\n")
        f.write(f"## 適用した置換: {len(applied)}件\n")
        for n, orig, repl in applied:
            f.write(f"{n}行目: {orig} → {repl}\n")
        f.write(f"\n## スキップした編集案: {len(skipped)}件\n")
        for n, orig, repl, reason in skipped:
            f.write(f"{n}行目: {orig} → {repl} [{reason}]\n")

    print(f"\n完了しました。適用 {len(applied)}件 / スキップ {len(skipped)}件")
    print(f"出力: {out_txt}\n      {out_srt}\n      {out_log}")


if __name__ == "__main__":
    main()
