"""字幕採用ジャッジ(選択字幕モード)。

「全てを字幕にするとうるさい」ため、聞き取りにくい・理解に必要な箇所だけを
字幕化する。機械シグナル+LLM評価の合成スコアで判定する(BACKEND_DESIGN.md)。
"""

from dataclasses import dataclass

# 発話速度がこの文字/秒を超えると「耳で追いにくい」とみなす
FAST_SPEECH_CPS = 8.0


@dataclass
class JudgeInput:
    idx: int
    text: str
    duration: float
    confidence: float | None      # ASRのavg_logprob(低い=聞き取りにくい)
    has_term: bool                # 用語集の固有名詞を含む
    llm_important: bool = False   # LLMが「理解の骨格」と判定


def score(inp: JudgeInput) -> float:
    """字幕が必要な度合い(高いほど採用)。重みはヒューリスティック"""
    s = 0.0
    if inp.confidence is not None:
        # avg_logprobは0(確信)〜-1超(不確か)。不確かなほど字幕が必要
        s += min(1.0, max(0.0, -inp.confidence)) * 1.0
    if inp.duration > 0:
        cps = len(inp.text) / inp.duration
        if cps >= FAST_SPEECH_CPS:
            s += 0.5
    if inp.has_term:
        s += 0.7
    if inp.llm_important:
        s += 0.6
    return round(s, 4)


def select_subtitles(inputs: list[JudgeInput], rate: float) -> set[int]:
    """スコア上位 rate 割合の idx を採用として返す(最低1件)"""
    if not inputs:
        return set()
    rate = min(1.0, max(0.0, rate))
    count = max(1, round(len(inputs) * rate))
    ranked = sorted(inputs, key=lambda i: (-score(i), i.idx))
    return {i.idx for i in ranked[:count]}


IMPORTANCE_SCHEMA = {
    "type": "object",
    "properties": {
        "important_lines": {"type": "array", "items": {"type": "integer"}}
    },
    "required": ["important_lines"],
}

IMPORTANCE_PROMPT = """あなたは動画字幕の編集者です。以下の対談の各行から、
**視聴者の理解の骨格になる行**(話題の転換点・結論・重要な主張・決め台詞)を選んでください。

ルール:
1. 全体の2〜3割程度に絞る。相槌・つなぎ・繰り返しは選ばない。
2. 行番号のリストだけを返す。
3. 無ければ {"important_lines": []} を返す。

出力形式: {"important_lines": [3, 10, 15]}"""
