"""M39: 配布中のまま残っていた不具合。

戦略的リファクタリングの調査で見つかったもの。いずれも「特定の環境でしか
踏まない」型で、開発機では再現しないためテストで固定する。

  0-2 セットアップのダウンロードが存在しないジョブ状態を待って固まった
  0-4 APIキーのファイルが cp932 だと例外が漏れた
  0-5 非ASCIIパスで顔検出が空の分類器になった
  0-6 Windows で字幕フォントが列挙できなかった
  0-7 AppImage 版に ffmpeg の案内が無かった

0-1(ROCmのフォールバック先)と0-3(EnvironmentPanelのエンジン固定)は、
エンジン選択がプロファイル固定方式になった2026-08-10に構造ごと無くなった
(多段フォールバック自体が存在しない。tests/core/test_hwprofile.py が対応表を見る)。
"""

import platform
import re
from pathlib import Path

import pytest


# ---- 0-2 ジョブの終端状態がPythonとTSでずれていた ----
#
# SetupPanel は j.status === 'succeeded' を待っていたが、その状態は存在しない。
# ダウンロードが終わってもボタンが「取得中…」のまま固まっていた。
# 状態名の一覧が2言語に分かれている以上、突き合わせないと必ずまた乖離する。
class TestジョブJの終端状態:
    def test_フロントと同じ集合を持つ(self):
        from backend.jobs.queue import TERMINAL_STATUSES

        source = Path("frontend/src/api/client.ts").read_text(encoding="utf-8")
        match = re.search(r"JOB_TERMINAL_STATUSES = \[(.*?)\]", source, re.S)
        assert match, "client.ts に JOB_TERMINAL_STATUSES が無い"
        front = set(re.findall(r"'([a-z]+)'", match.group(1)))
        assert front == set(TERMINAL_STATUSES), (
            f"終端状態がずれている: backend={set(TERMINAL_STATUSES)} frontend={front}"
        )

    def test_フロントに状態名の直書きが残っていない(self):
        """判定が分散すると、また片方だけ直して取りこぼす"""
        hits = []
        for path in Path("frontend/src").rglob("*.ts*"):
            if path.name.endswith(".test.ts") or path.name.endswith(".test.tsx"):
                continue
            for num, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if "succeeded" in line:
                    hits.append(f"{path}:{num}")
        assert not hits, f"存在しない状態 'succeeded' を参照している: {hits}"


# ---- 0-4 APIキーのファイルが cp932 ----
#
# メモ帳(既定cp932)でキーファイルを作り全角が混ざると、
# read_text(encoding="utf-8") が UnicodeDecodeError を投げ、
# None を返すべきところでプロセスに例外が漏れていた。
CP932_TEXT = "ここにAPIキーを貼り付けてください\n"


@pytest.mark.parametrize(
    "module_path,func_name",
    [
        ("backend.engines.llm.gemini", "load_api_key"),
        ("backend.engines.llm.claude", "load_api_key"),
    ],
)
def test_cp932のキーファイルでも例外を漏らさない(tmp_path, monkeypatch, module_path, func_name):
    import importlib

    # 環境変数が入っているとファイルを読まないので必ず消す
    for var in ("GEMINI_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(var, raising=False)

    path = tmp_path / "key.txt"
    path.write_text(CP932_TEXT, encoding="cp932")

    module = importlib.import_module(module_path)
    assert getattr(module, func_name)(path) is None


@pytest.mark.parametrize(
    "module_path,func_name,valid",
    [
        ("backend.engines.llm.gemini", "load_api_key", "AIzaSyTESTKEY0123456789"),
        ("backend.engines.llm.claude", "load_api_key", "sk-ant-api03-testkey"),
    ],
)
def test_正しいキーは今までどおり読める(tmp_path, monkeypatch, module_path, func_name, valid):
    import importlib

    for var in ("GEMINI_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(var, raising=False)

    path = tmp_path / "key.txt"
    path.write_text(valid + "\n", encoding="utf-8")

    module = importlib.import_module(module_path)
    assert getattr(module, func_name)(path) == valid


# ---- 0-5 非ASCIIパスでの顔検出 ----
#
# cv2.CascadeClassifier(str) は OpenCV の C++ 層が ANSI コードページで
# fopen するため、パスに非ASCIIが入ると空の分類器を返す(例外は出ない)。
# PyInstaller の展開先はユーザー名依存なので、日本語ユーザー名のWindows機で
# 顔検出が落ちる。このリポジトリ自身が「ドキュメント」配下にあるため、
# テスト実行時にも踏む。
def test_非ASCIIパスでも分類器を読める(tmp_path):
    from backend.pipeline import face

    target = tmp_path / "日本語ディレクトリ"
    target.mkdir()
    copied = target / "haarcascade_frontalface_default.xml"
    copied.write_bytes(Path(face.cascade_path()).read_bytes())

    classifier = face.load_cascade(copied)
    assert not classifier.empty(), "空の分類器が返っている(ANSI経路で読んでいる)"


def test_分類器の読み込みは1箇所に集約されている():
    """cv2.CascadeClassifier を直接呼ぶ箇所が増えると同じ罠を踏む"""
    import ast

    src = Path("backend/pipeline/face.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    direct = [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "CascadeClassifier"
    ]
    assert len(direct) <= 1, f"CascadeClassifier の直接呼び出しが複数ある: {direct}"


# ---- 0-6 Windows のフォント列挙 ----
#
# fc-list は Linux 専用。無い場合 ["Noto Sans JP"] を返していたが、
# そのフォントは Windows に標準搭載されていない。存在しないフォントだけを
# 提示する = 字幕フォントが実質選べない状態だった。
class TestフォントOS別:
    def test_Windowsは実在するフォントを返す(self):
        from backend.api.settings_api import fallback_fonts

        fonts = fallback_fonts("Windows")
        assert fonts, "候補が空"
        # Windows標準の日本語フォント。どれか1つは必ず入っている
        assert any(f in fonts for f in ("Yu Gothic", "Meiryo", "MS Gothic"))

    def test_Linuxは従来どおり(self):
        from backend.api.settings_api import fallback_fonts

        assert "Noto Sans JP" in fallback_fonts("Linux")

    def test_macOSはヒラギノを含む(self):
        from backend.api.settings_api import fallback_fonts

        assert any("Hiragino" in f for f in fallback_fonts("Darwin"))

    def test_どのOSでも空にしない(self):
        from backend.api.settings_api import fallback_fonts

        for os_name in ("Windows", "Linux", "Darwin", "SomethingElse"):
            assert fallback_fonts(os_name), os_name


# ---- 0-7 ffmpeg が無いときの案内 ----
#
# linux.deb.depends は .deb にしか効かない。AppImage は依存宣言の仕組みが
# 無く ffmpeg も同梱していないため、未導入だと書き出しが無案内で失敗する。
class TestFFmpegの案内:
    def test_AppImageには導入手順を出す(self):
        from backend.core.ffmpeg import missing_message

        message = missing_message("Linux", appimage=True)
        assert "apt" in message or "インストール" in message
        assert message != missing_message("Linux", appimage=False), (
            "AppImage向けの案内が通常のLinuxと同じになっている"
        )

    def test_既存の案内は変えない(self):
        from backend.core.ffmpeg import missing_message

        assert "同梱" in missing_message("Windows")
        assert "brew" in missing_message("Darwin")
        assert "apt" in missing_message("Linux")


@pytest.mark.skipif(platform.system() != "Windows", reason="Windowsの実機でのみ意味がある")
def test_この機体でフォントが1つ以上列挙される():
    """0-6 の実地確認。fc-listが無い環境で候補が空にならないこと"""
    from backend.api.settings_api import list_fonts

    assert list_fonts()["fonts"]
