"""字幕・テキストの書き出し。

M1時点では現行スクリプトのフォーマット移植のみ。
折返し・禁則処理・ASS出力はM7で追加する。
"""

from pathlib import Path


def format_timestamp(seconds: float) -> str:
    ms = int((seconds - int(seconds)) * 1000)
    s = int(seconds)
    h, rem = divmod(s, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def srt_block(index: int, start: float, end: float, text: str) -> str:
    return f"{index}\n{format_timestamp(start)} --> {format_timestamp(end)}\n{text}\n\n"


def write_srt(path: Path, entries: list[tuple[float, float, str]]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for i, (start, end, text) in enumerate(entries, start=1):
            f.write(srt_block(i, start, end, text))


def write_txt(path: Path, texts: list[str]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for text in texts:
            f.write(text + "\n")
