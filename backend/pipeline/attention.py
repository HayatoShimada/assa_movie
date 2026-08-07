"""切り抜き候補のスコアリング(アテンション機能)。

LLMが提案した候補範囲に、機械特徴(発話密度・話者交替・笑い)を合成して
最終スコアと根拠タグを付ける。BACKEND_DESIGN.md「クリップ生成・再調整」参照。
"""

import re
from dataclasses import dataclass

# 盛り上がりとみなす表現(文字起こしに現れる笑いの痕跡)
_LAUGH = re.compile(r"(笑|ww|ハハ|ははは|あはは)")

# 発話密度がこの文字/秒以上なら「テンポが良い」
DENSE_CPS = 6.0
# 1分あたりの話者交替がこの回数以上なら「掛け合い」
TURNS_PER_MIN = 6.0


@dataclass
class ClipFeatures:
    duration: float
    density_cps: float      # 発話密度(文字/秒)
    turns_per_min: float    # 話者交替回数/分
    laugh_count: int


def clip_features(segments: list[dict], start: float, end: float) -> ClipFeatures:
    """クリップ範囲内のセグメントから機械特徴を計算する(相槌は密度から除外)"""
    inside = [s for s in segments if s["start"] < end and s["end"] > start]
    duration = max(end - start, 0.1)
    chars = sum(len(s["text"]) for s in inside if not s.get("is_aizuchi"))
    turns = sum(
        1 for a, b in zip(inside, inside[1:])
        if a.get("speaker") and b.get("speaker") and a["speaker"] != b["speaker"]
    )
    laughs = sum(len(_LAUGH.findall(s["text"])) for s in inside)
    return ClipFeatures(
        duration=duration,
        density_cps=chars / duration,
        turns_per_min=turns / duration * 60,
        laugh_count=laughs,
    )


def combined_score(
    llm_score: float,
    features: ClipFeatures,
    target_duration: float | None = None,
) -> tuple[float, list[str]]:
    """LLMスコア(1-10)と機械特徴を合成し、(スコア, 根拠タグ) を返す"""
    score = max(0.0, min(10.0, llm_score))
    reasons: list[str] = []

    if features.laugh_count > 0:
        score += 0.8
        reasons.append("笑いあり")
    if features.density_cps >= DENSE_CPS:
        score += 0.5
        reasons.append("テンポが良い")
    if features.turns_per_min >= TURNS_PER_MIN:
        score += 0.5
        reasons.append("掛け合い")

    if target_duration:
        ratio = features.duration / target_duration
        if 0.8 <= ratio <= 1.2:
            score += 0.7
            reasons.append("目標尺に合う")
        elif ratio > 2.0 or ratio < 0.4:
            score -= 1.0

    return round(score, 2), reasons


ATTENTION_SCHEMA = {
    "type": "object",
    "properties": {
        "candidates": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "start_line": {"type": "integer"},
                    "end_line": {"type": "integer"},
                    "title": {"type": "string"},
                    "hook": {"type": "string"},
                    "score": {"type": "integer"},
                    "reasons": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["start_line", "end_line", "title", "hook", "score", "reasons"],
            },
        }
    },
    "required": ["candidates"],
}

ATTENTION_PROMPT = """あなたは切り抜き動画のプロ編集者です。対談の文字起こしから、
**単体の短尺動画として成立する切り抜き候補**を探してください。

良い候補の条件:
1. 話題がその範囲内で自己完結している(前後の文脈が無くても分かる)
2. 冒頭にフック(続きが気になる発言・意外な主張)がある
3. 結論・オチ・学びがある
{duration_hint}

各候補について:
- start_line/end_line: 範囲の行番号(話題の自然な始まりと終わりを選ぶ)
- title: 内容を表す短いタイトル案
- hook: 冒頭に載せる釣りテロップ案(20文字以内)
- score: 切り抜きとしての魅力(1〜10)
- reasons: 根拠タグ(例: 「完結した話題」「意外な主張」「フック強い」)を1〜3個

候補は多くても8個まで。無理に作らず、弱い候補は出さない。
出力形式: {{"candidates": [{{"start_line": 10, "end_line": 45, "title": "...",
"hook": "...", "score": 8, "reasons": ["完結した話題"]}}]}}"""


def build_attention_prompt(target_duration: float | None) -> str:
    hint = ""
    if target_duration:
        hint = f"4. 目標の長さは約{int(target_duration)}秒(多少の前後は可)"
    return ATTENTION_PROMPT.format(duration_hint=hint)


META_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "hooks": {"type": "array", "items": {"type": "string"}},
        "description": {"type": "string"},
        "hashtags": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["title", "hooks", "description", "hashtags"],
}

META_PROMPT = """あなたは切り抜き動画の投稿を最適化する編集者です。
与えられたクリップの文字起こしから、投稿用のメタ情報を作ってください。

- title: 動画タイトル(30文字以内、内容が分かり引きがある)
- hooks: 冒頭テロップ案を3つ(各20文字以内、視聴継続を促す)
- description: 概要欄の文章(2〜3文)
- hashtags: ハッシュタグ5個以内(#付き)

出力形式: {"title": "...", "hooks": ["...", "...", "..."],
"description": "...", "hashtags": ["#..."]}"""


def parse_silences(ffmpeg_stderr: str, offset: float = 0.0) -> list[tuple[float, float]]:
    """ffmpeg silencedetect の出力から (開始, 終了) のリストを取り出す"""
    starts = [float(m) for m in re.findall(r"silence_start: ([\d.]+)", ffmpeg_stderr)]
    ends = [float(m) for m in re.findall(r"silence_end: ([\d.]+)", ffmpeg_stderr)]
    return [(offset + s, offset + e) for s, e in zip(starts, ends)]
