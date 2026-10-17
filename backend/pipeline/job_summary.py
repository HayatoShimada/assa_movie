"""AI処理(指示語の解決・固有名詞のスキャン)の結果を一文で説明する(純関数)。

ジョブの戻り値(jobs.result_json)に入り、画面が完了時に表示する。
0件で「完了」とだけ出ると、動いたのか・何を探したのかが分からない
(評価での指摘)。0件のときこそ、何を対象に探したかを書く。
"""

from backend.pipeline.pronoun import LEVELS


def resolve_summary(*, level: str, found: int, applied: int, guarded: int, lines: int) -> dict:
    """指示語の解決の結果。

    found: 保存した候補の数(安全確認を通ったもの)
    applied: そのうち自動で適用した数
    guarded: AIが出したが安全確認(発言を変えすぎない等)で除外した数
    lines: 対象にした行数
    """
    if lines == 0:
        message = "解決する対象の行がありません(未解決の行はもう残っていません)。"
        return {"found": 0, "message": message}

    targets = (LEVELS.get(level) or LEVELS["medium"]).targets
    guard_note = (
        f"AIの提案のうち{guarded}件は、発言を変えすぎるなどの理由で安全確認により除外しました。"
        if guarded else ""
    )
    if found == 0:
        if guarded:
            message = f"使える置き換え候補はありませんでした({lines}行を確認)。{guard_note}"
        else:
            message = (
                f"置き換えが必要な指示語は見つかりませんでした(対象: {targets} / {lines}行を確認)。"
                "参照先がはっきりしない指示語は、発言を変えないようそのまま残します。"
                "対象を広げるには、設定の「指示語置換の積極性」を上げてください。"
            )
        return {"found": 0, "message": message}

    review = found - applied
    parts = [f"指示語の候補が{found}件見つかりました"]
    detail = []
    if applied:
        detail.append(f"自動で適用{applied}件")
    if review:
        detail.append(f"レビュー待ち{review}件")
    message = f"{parts[0]}({'・'.join(detail)})。{guard_note}"
    if review:
        message += "下の一覧で承認・却下してください。"
    return {"found": found, "message": message}


def terms_summary(*, found: int, lines: int) -> dict:
    """固有名詞スキャンの結果。found: 新しく作った質問の数"""
    if lines == 0:
        return {"found": 0, "message": "スキャンする対象の行がありません。先に文字起こしをしてください。"}
    if found == 0:
        return {"found": 0, "message": (
            f"表記の確認が必要な固有名詞は見つかりませんでした({lines}行を確認)。"
            "対象は、音は合っていても漢字が怪しい人名・会社名・製品名・専門用語です。"
            "見つかった場合は、ここにAIからの質問として並びます。"
        )}
    return {"found": found, "message": (
        f"表記の確認が必要な語が{found}件見つかりました。"
        "下の質問に答えると、同じ語がすべての行で一括で直ります。"
    )}
