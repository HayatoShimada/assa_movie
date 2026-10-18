"""AI処理の結果の説明文(純関数・テーブル駆動)。

評価で「指示語を解決」「固有名詞をスキャン」が0件のとき「完了」とだけ出て、
動いたのか・何を探したのかが分からなかった。0件のときこそ何を探したかを書く。
"""

import pytest

from backend.pipeline.job_summary import resolve_summary, terms_summary


@pytest.mark.parametrize(
    "level, found, applied, guarded, lines, words",
    [
        ("weak", 0, 0, 0, 120, ["見つかりませんでした", "これ・それ・あれ", "120行"]),
        ("medium", 0, 0, 0, 120, ["見つかりませんでした", "この/その/あの"]),
        # AIは出したが安全確認で全部落ちた → 「見つからなかった」ではなくそう書く
        ("medium", 0, 0, 3, 120, ["3件", "安全確認"]),
        ("medium", 5, 2, 0, 120, ["5件", "2件", "3件", "レビュー"]),
        ("strong", 4, 4, 1, 120, ["4件", "1件", "安全確認"]),
    ],
)
def test_指示語の結果を説明する(level, found, applied, guarded, lines, words):
    out = resolve_summary(level=level, found=found, applied=applied, guarded=guarded, lines=lines)
    assert out["found"] == found
    for word in words:
        assert word in out["message"], f"「{word}」が無い: {out['message']}"


def test_指示語が0件なら範囲の広げ方を案内する():
    out = resolve_summary(level="weak", found=0, applied=0, guarded=0, lines=10)
    assert "積極性" in out["message"]


def test_指示語の対象行が無い():
    out = resolve_summary(level="medium", found=0, applied=0, guarded=0, lines=0)
    assert "対象の行がありません" in out["message"]


@pytest.mark.parametrize(
    "found, lines, words",
    [
        (0, 300, ["見つかりませんでした", "300行", "人名", "質問"]),
        (2, 300, ["2件", "質問に答える"]),
    ],
)
def test_固有名詞の結果を説明する(found, lines, words):
    out = terms_summary(found=found, lines=lines)
    assert out["found"] == found
    for word in words:
        assert word in out["message"], f"「{word}」が無い: {out['message']}"


def test_固有名詞の対象行が無い():
    assert "対象の行がありません" in terms_summary(found=0, lines=0)["message"]
