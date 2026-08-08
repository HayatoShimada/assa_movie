"""標準出力の文字コードを固定する。

日本語Windowsの既定の文字コードはcp932で、起動ログに使っている「⚠」(U+26A0)を
エンコードできない。v0.9.2のWindows版はこれで起動に失敗していた
(lifespan内のprintがUnicodeEncodeErrorを投げ、FastAPIのstartupごと落ちる)。

PYTHONIOENCODINGでは直せない。PyInstallerで固めた実行ファイルは
isolated configでPythonを起動するため、環境変数を読まないため。
だからコード側で付け替える。
"""

import sys
from typing import Any


def force_utf8(*streams: Any) -> None:
    """渡されたテキストストリームをUTF-8に付け替える。

    `errors="replace"` にするのは、ログが出せないことでアプリを止めないため。
    表示が「?」に化けても、起動しないよりはるかにましだった。
    """
    for stream in streams:
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:  # 差し替えられたストリーム(テストやpytest)は触らない
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            # 付け替えられなくてもアプリは動かす(ログが化けるだけ)
            pass


def force_utf8_stdio() -> None:
    """このプロセスの標準出力・標準エラーをUTF-8にする"""
    force_utf8(sys.stdout, sys.stderr)
