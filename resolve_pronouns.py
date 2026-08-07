#!/usr/bin/env python3
"""
指示語(これ・それ・あれ等)を指す内容に置き換える後処理スクリプト(CLI)。
ローカルLLM(Ollama)で文脈から参照先を解決し、変更ログを出力する。

使い方:
  uv run python resolve_pronouns.py <ベース名>                # 例: 雑談編
  uv run python resolve_pronouns.py <ベース名> --limit 100    # 冒頭100行だけ(試験用)
  uv run python resolve_pronouns.py <ベース名> --form replace # 表現形式を指定
  uv run python resolve_pronouns.py <ベース名> --level strong # 積極性を指定

入力:  <ベース名>.txt / <ベース名>.srt (transcribe.pyの出力。行とブロックが1対1対応)
出力:  <ベース名>_置換済.txt / <ベース名>_置換済.srt / <ベース名>_置換ログ.txt
       (元ファイルは変更しない)

表現形式(--form):
  annotate 発言を変えずカッコで補足(既定・最も安全)
  replace  指示語を参照先に置き換える
  complete 置換した上でカッコでも補足する(意訳寄り)

処理の実体は backend/ 配下のモジュールにあり、このスクリプトはCLIラッパ。
事前に Ollama サーバーが起動していること: ollama serve
"""

import argparse
import re
import sys
from pathlib import Path

from backend.core.config import settings
from backend.engines.llm.registry import build_client
from backend.pipeline import pronoun


def parse_srt(path: Path) -> list[tuple[str, str, str]]:
    """SRTを (番号行, 時刻行, 本文) のリストにパースする"""
    blocks = []
    raw = path.read_text(encoding="utf-8").strip()
    for block in re.split(r"\n\n+", raw):
        lines = block.split("\n")
        if len(lines) < 3:
            continue
        blocks.append((lines[0], lines[1], "\n".join(lines[2:])))
    return blocks


def main() -> None:
    ap = argparse.ArgumentParser(description="指示語を指す内容に置き換える")
    ap.add_argument("base", help="拡張子なしのベース名(例: 雑談編)")
    ap.add_argument("--limit", type=int, help="冒頭N行だけ処理する(試験用)")
    ap.add_argument("--level", default=settings.pronoun_level,
                    choices=list(pronoun.LEVELS), help="積極性")
    ap.add_argument("--form", default=settings.pronoun_form,
                    choices=["annotate", "replace", "complete"], help="表現形式")
    args = ap.parse_args()

    base = Path(args.base.removesuffix(".txt").removesuffix(".srt"))
    txt_path, srt_path = base.with_suffix(".txt"), base.with_suffix(".srt")
    lines = txt_path.read_text(encoding="utf-8").rstrip("\n").split("\n")
    srt_blocks = parse_srt(srt_path)

    if len(lines) != len(srt_blocks):
        print(f"エラー: {txt_path}({len(lines)}行)と{srt_path}({len(srt_blocks)}ブロック)が対応していません。")
        sys.exit(1)
    mismatch = sum(1 for l, b in zip(lines, srt_blocks) if l != b[2])
    if mismatch:
        print(f"エラー: .txtと.srtで本文が一致しない行が{mismatch}件あります。"
              "同じ実行で生成されたペアを指定してください。")
        sys.exit(1)

    total = min(args.limit, len(lines)) if args.limit else len(lines)
    print(f"モデル: {settings.ollama_model} / 対象: {total}行(全{len(lines)}行)"
          f" / 積極性: {args.level} / 形式: {args.form}")

    client = build_client(settings)
    system = pronoun.build_system_prompt(pronoun.PromptParts(level=args.level))
    edited = list(lines)
    applied, skipped = [], []
    chunk_size = settings.llm_chunk_size

    for start in range(0, total, chunk_size):
        end = min(start + chunk_size, total)
        print(f"処理中: {start + 1}〜{end}行目...", flush=True)
        target_lines = list(range(start + 1, end + 1))
        user = pronoun.build_user_prompt(lines, target_lines, settings.llm_context_size)
        payload = client.complete_json(system, user, pronoun.EDITS_SCHEMA)

        for edit in pronoun.parse_edits(payload):
            v = pronoun.validate_edit(
                edit, edited[edit.line - 1] if 1 <= edit.line <= len(edited) else "",
                level=args.level, line_range=(start + 1, end),
            )
            if not v.ok:
                skipped.append((edit, v.reason))
                continue
            edited[edit.line - 1] = pronoun.apply_edit(
                edited[edit.line - 1], edit, form=args.form
            )
            applied.append(edit)

    # ---- 出力 ----
    out_txt = base.parent / f"{base.name}_置換済.txt"
    out_srt = base.parent / f"{base.name}_置換済.srt"
    out_log = base.parent / f"{base.name}_置換ログ.txt"

    out_txt.write_text("\n".join(edited) + "\n", encoding="utf-8")
    with open(out_srt, "w", encoding="utf-8") as f:
        for (num, ts, _), text in zip(srt_blocks, edited):
            f.write(f"{num}\n{ts}\n{text}\n\n")

    with open(out_log, "w", encoding="utf-8") as f:
        f.write(f"# 置換ログ: {base.name} (モデル: {settings.ollama_model},"
                f" 対象: {total}行, 積極性: {args.level}, 形式: {args.form})\n\n")
        f.write(f"## 適用した置換: {len(applied)}件\n")
        for e in applied:
            f.write(f"{e.line}行目: {e.original} → {e.replacement}"
                    f"(参照先: {e.referent}, 確信度: {e.confidence})\n")
        f.write(f"\n## スキップした編集案: {len(skipped)}件\n")
        for e, reason in skipped:
            f.write(f"{e.line}行目: {e.original} → {e.replacement} [{reason}]\n")

    print(f"\n完了しました。適用 {len(applied)}件 / スキップ {len(skipped)}件")
    print(f"出力: {out_txt}\n      {out_srt}\n      {out_log}")


if __name__ == "__main__":
    main()
