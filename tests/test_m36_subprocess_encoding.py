"""M36: 子プロセスの出力をロケール依存で復号しない。

`subprocess.run(..., text=True)` は encoding を指定しないと、その環境の
既定コーデックで復号する。日本語Windowsはcp932、CIの英語Windowsはcp1252で、
ffmpegやwhisper-cliの出力に含まれるバイトで UnicodeDecodeError になる。

同じ根(Windowsのロケール依存エンコーディング)で4回踏んでいる:

  v0.9.2  アプリ起動時のprintが cp932 で落ちる          (出力側)
  v0.9.3  CIビルド中のprintが cp1252 で落ちる           (出力側)
  v0.9.6  whisper-cliの出力読み取りが cp932 で落ちる    (入力側)

出力側は backend/core/console.py の force_utf8_stdio() で塞いだ。
入力側はここで見張る。テストにしておかないと、次に subprocess を足す人が
同じ書き方をしてまた踏む。
"""

import ast
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1] / "backend"
SUBPROCESS_CALLS = {"run", "Popen", "check_output", "call", "check_call"}


def _text_mode_calls_without_encoding(tree: ast.AST) -> list[int]:
    """text=True(またはuniversal_newlines=True)なのに encoding を渡していない行"""
    bad = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr not in SUBPROCESS_CALLS:
            continue
        # subprocess.run(...) の形だけを見る(自作関数の run は対象外)
        target = node.func.value
        if not (isinstance(target, ast.Name) and target.id == "subprocess"):
            continue

        kwargs = {kw.arg for kw in node.keywords if kw.arg}
        text_mode = any(
            kw.arg in ("text", "universal_newlines")
            and isinstance(kw.value, ast.Constant)
            and kw.value.value is True
            for kw in node.keywords
        )
        # **SUBPROCESS_TEXT のような展開があれば指定済みとみなす
        has_unpack = any(kw.arg is None for kw in node.keywords)
        if text_mode and "encoding" not in kwargs and not has_unpack:
            bad.append(node.lineno)
    return bad


@pytest.mark.parametrize(
    "path", sorted(BACKEND.rglob("*.py")), ids=lambda p: p.name
)
def test_子プロセスの出力はエンコーディングを明示して読む(path):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    bad = _text_mode_calls_without_encoding(tree)
    assert not bad, (
        f"{path.relative_to(BACKEND.parent)} の {bad} 行目: "
        "text=True だけではロケール依存で復号され、日本語Windows(cp932)や "
        "英語Windows(cp1252)で UnicodeDecodeError になる。"
        "backend/core/console.py の SUBPROCESS_TEXT を展開して渡すこと"
    )


# ---- 検出そのものが効いているかの確認 ----
def test_検出できることを確かめる():
    """このテスト自身が素通りしていないことを担保する"""
    bad = ast.parse("import subprocess\nsubprocess.run(['x'], text=True)\n")
    assert _text_mode_calls_without_encoding(bad) == [2]


def test_encodingを指定していれば通す():
    ok = ast.parse("import subprocess\nsubprocess.run(['x'], text=True, encoding='utf-8')\n")
    assert _text_mode_calls_without_encoding(ok) == []


def test_展開して渡していても通す():
    ok = ast.parse("import subprocess\nsubprocess.run(['x'], **SUBPROCESS_TEXT)\n")
    assert _text_mode_calls_without_encoding(ok) == []


def test_bytesで読むなら対象外():
    """text=Trueでなければ復号しないので問題にならない"""
    ok = ast.parse("import subprocess\nsubprocess.run(['x'], capture_output=True)\n")
    assert _text_mode_calls_without_encoding(ok) == []
