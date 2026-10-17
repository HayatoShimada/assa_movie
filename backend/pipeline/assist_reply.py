"""対話アシストの応答文を、実際の状態から組み立てる(純関数)。

LLMは「変更しました」と返しがちだが、アシストの編集は必ず承認待ち(proposed)で
保存され、その時点では何も変わっていない。LLMの言葉をそのまま見せると
「直ったはずなのに直っていない」になる(v2.0の初心者評価で実際にそう読まれた)。
そこで応答文は、機械側が把握している状態(案が何件できたか・安全確認で
落ちたか)から作り、LLMの返事は「回答」としてだけ添える。
"""

import re

# 「変えた」と言い切る言い回し。案が無いのにこう言われると誤解を招く
_CLAIMS_CHANGE = re.compile(
    r"(変更|修正|置換|置き換え|書き換え|反映|適用|訂正|直|変え)し?(てお(き|い)|てあり)?ました"
)

_DIRECT_EDIT_HINT = "文字を直接直すときは、行の鉛筆ボタンを押してください。"
_NOT_CHANGED = "この行は変わっていません。"


def claims_change(text: str) -> bool:
    """LLMの返事が「変更済み」と言い切っているか"""
    return bool(_CLAIMS_CHANGE.search(text))


def compose_assist_reply(
    llm_reply: str,
    proposals: list[tuple[str, str]],
    rejected_reasons: list[str],
) -> str:
    """アシストの応答文を作る。

    proposals: 保存した案の (変える前の文字列, 承認したときに入る文字列)
    rejected_reasons: 安全確認(pronoun.validate_edit)で落とした案の理由
    """
    if len(proposals) == 1:
        before, after = proposals[0]
        return (
            f"「{before}」を「{after}」に変える案を作りました。"
            "まだ反映していません。「承認」を押すと反映されます。"
        )
    if proposals:
        return (
            f"修正案を{len(proposals)}件作りました。"
            "まだ反映していません。「承認」を押すと反映されます。"
        )
    if rejected_reasons:
        return (
            f"AIの修正案は安全のため採用しませんでした(理由: {rejected_reasons[0]})。"
            f"{_NOT_CHANGED}{_DIRECT_EDIT_HINT}"
        )

    reply = llm_reply.strip()
    if not reply:
        return _NOT_CHANGED
    if claims_change(reply):
        return f"{_NOT_CHANGED}{_DIRECT_EDIT_HINT}"
    return f"{_NOT_CHANGED}AIの回答: {reply}"
