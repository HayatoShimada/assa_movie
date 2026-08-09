"""APIキー・トークンをファイルから読む。

利用者が手で作るファイルなので、文字コードを信用できない。日本語Windowsの
メモ帳は既定がcp932で、雛形の説明文(全角)を消し忘れたまま保存されると
UTF-8として読めず UnicodeDecodeError がそのまま呼び出し元へ漏れていた。
「キーが読めなかった」だけなので例外ではなく None を返す。
"""

from pathlib import Path


def read(path: Path | None) -> str | None:
    """キーファイルの中身(前後の空白を除いたもの)。読めなければ None"""
    if not path or not path.exists():
        return None
    try:
        return path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError):
        return None
