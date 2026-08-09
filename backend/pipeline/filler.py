"""フィラー(言い淀み)の排除。

BACKEND_DESIGN.md「フィラー排除」参照。
- 安全群: 意味を持つ用法がほぼ無い間投詞。正規表現で機械的に除去できる
- 文脈依存群(なんか・まあ・その 等): 意味を持つ用法があるためLLM判定必須(kind='filler'のedits)

適用は字幕・書き出しテキストのみ。original_textは常に保持する。
"""

import re
from dataclasses import dataclass

# 安全群: これらが独立して現れた場合は除去してよい
# (「えっと」「あのー」等は日本語で他の意味を持たない。
#  「そのー」「あのー」のように長音で伸びる場合はほぼフィラー)
_SAFE_STANDALONE = (
    r"(?:えーっと|えっとー|えっと|えーと|ええと|ええっと|"
    r"あのー+|あのう|そのー+|そのう)"
)
# 単独では意味を持ちうるため、直後に読点がある場合のみ除去する語
# (「うーんと唸る」「んーと考える」のような動作表現があるため読点必須)
_SAFE_WITH_COMMA = r"(?:あー|えー|うーん|うーんと|んーと|んー|まあ|あの|その)"

_RE_STANDALONE = re.compile(rf"{_SAFE_STANDALONE}[、,]?")
_RE_WITH_COMMA = re.compile(rf"(?:^|(?<=[、,。 ])){_SAFE_WITH_COMMA}[、,]")
_RE_DUP_COMMA = re.compile(r"[、,]{2,}")

# 文脈依存群(LLMに判定させる候補。この語以外の削除提案は受け付けない)
CONTEXTUAL_FILLERS = ("なんか", "まあ", "その", "あの", "こう", "なんだろう", "やっぱ", "やっぱり")


def remove_fillers_weak(text: str) -> str:
    """安全群のフィラーだけを機械的に除去する(弱モード)"""
    out = _RE_STANDALONE.sub("", text)
    out = _RE_WITH_COMMA.sub("", out)
    out = _RE_DUP_COMMA.sub("、", out)
    out = out.lstrip("、,")
    return out


FILLER_SCHEMA = {
    "type": "object",
    "properties": {
        "fillers": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "line": {"type": "integer"},
                    "word": {"type": "string"},
                    "judgment": {"type": "string", "enum": ["filler", "ambiguous"]},
                },
                "required": ["line", "word", "judgment"],
            },
        }
    },
    "required": ["fillers"],
}

FILLER_PROMPT = """あなたは対談の文字起こしから、フィラー(言い淀み)を特定する編集者です。
各行の中で、フィラーとして使われている可能性がある語を挙げ、judgment を付けてください。

対象になりうる語: なんか・まあ・その・あの・こう・なんだろう・やっぱ・やっぱり

judgment の基準:
- "filler": フィラーであることが文脈から明白(例:「あの、それでですね」の あの)
  - 「そのー」「あのー」のように長音で伸びている場合はフィラーの可能性が高い
- "ambiguous": フィラーか意味のある語(指示語など)か判断が割れうる
  (例:「その、人と話すとき」の その — フィラーにも「その人」の言いかけにも読める)

厳守するルール:
1. 明らかに意味を持つ用法は挙げない。
   - 「なんかあった?」の なんか は「何か」の意味なので対象外
   - 「その本」の その は指示語なので対象外
   - 「こうやって」の こう は様態を表すので対象外
2. word はその行に実際に含まれる表記のまま書く(読点は含めない)。
3. 同じ行に同じ語が複数回ある場合は挙げない(どれを指すか曖昧になるため)。
4. 削除してよいか迷う場合は "ambiguous" とする(勝手に削除しない)。
5. 無ければ {"fillers": []} を返す。

出力形式: {"fillers": [{"line": 行番号, "word": "なんか", "judgment": "filler"}]}"""


# ---- 言語学ベースの判別シグナル ----
# 根拠(BACKEND_DESIGN.md参照):
# 1. 統語: 指示語の「その/あの」は連体詞で必ず名詞句を修飾する。
#    後続が名詞でない(読点・ひらがな機能語・ポーズ)ならフィラー寄り
# 2. 音声: フィラーは長音化(そのー)・直後のポーズを伴いやすい
#    → 単語タイムスタンプの持続時間と直後ギャップで測定できる
# 3. 系列: 「あの(ー)」はフィラー化の制約が弱く、「その(ー)」はソ系指示詞の
#    性質を残すため文脈依存が強い(指示詞系フィラー研究)

# フィラーと判断する音響しきい値(秒)
FILLER_MIN_DURATION = 0.35   # 「その」単体でこれ以上伸びていれば言い淀みの可能性大
FILLER_MIN_GAP = 0.30        # 直後にこれ以上のポーズがあれば言い淀みの可能性大


@dataclass
class FillerSignals:
    duration: float | None = None       # 語の持続時間(秒)
    gap_after: float | None = None      # 直後のポーズ(秒)
    elongated: bool = False             # 表記上の長音(そのー)
    followed_by_comma: bool = False     # 直後が読点
    next_is_kanji_katakana: bool = False  # 直後が漢字/カタカナ(名詞の可能性大)
    probability: float | None = None    # Whisperの単語確率(低い=聞き取りが曖昧)

    def classify(self) -> str:
        """'filler_likely' | 'demonstrative_likely' | 'ambiguous'"""
        filler_score = 0
        if self.elongated:
            filler_score += 2
        if self.duration is not None and self.duration >= FILLER_MIN_DURATION:
            filler_score += 1
        if self.gap_after is not None and self.gap_after >= FILLER_MIN_GAP:
            filler_score += 1
        if self.followed_by_comma:
            filler_score += 1
        if self.probability is not None and self.probability < 0.5:
            filler_score += 1  # デコード確率が低い=言い淀みで音が崩れている可能性
        if self.next_is_kanji_katakana:
            # 連体詞用法(その+名詞)の可能性が高い
            return "demonstrative_likely" if filler_score < 2 else "ambiguous"
        return "filler_likely" if filler_score >= 2 else "ambiguous"


_KANJI_KATAKANA = re.compile(r"[一-鿿ァ-ヶA-ZA-Z0-90-9]")


def collect_signals(
    word: str,
    line_text: str,
    words: list[dict] | None = None,
) -> FillerSignals:
    """行テキストと単語タイムスタンプ(words_json)から判別シグナルを集める"""
    s = FillerSignals()
    pos = line_text.find(word)
    if pos >= 0:
        after = line_text[pos + len(word):]
        s.elongated = after.startswith("ー") or word.endswith("ー")
        stripped = after.lstrip("ー")
        s.followed_by_comma = stripped.startswith(("、", ","))
        # 読点は連体詞(その+名詞)の連続性を切るので、読点なしの場合だけ名詞判定する
        if not s.followed_by_comma:
            s.next_is_kanji_katakana = bool(stripped) and bool(
                _KANJI_KATAKANA.match(stripped[0])
            )

    if words:
        for i, w in enumerate(words):
            if word in w.get("text", ""):
                s.duration = round(w["end"] - w["start"], 3)
                s.probability = w.get("probability")
                if i + 1 < len(words):
                    s.gap_after = round(max(0.0, words[i + 1]["start"] - w["end"]), 3)
                break
    return s


def analyze_line(text: str, words: list[dict] | None = None) -> list[dict]:
    """Whisper段階の一次判定。行内のフィラー候補語を音響+表記シグナルで分類する。

    文字起こしジョブがこの結果を segments.filler_candidates_json に保存し、
    弱モードはLLMなしで 'filler_likely' を適用、強モードは 'ambiguous' だけを
    LLM・ユーザー質問に回す。
    """
    out = []
    for word in CONTEXTUAL_FILLERS:
        if text.count(word) != 1:
            continue
        sig = collect_signals(word, text, words)
        out.append({
            "word": word,
            "class": sig.classify(),
            "duration": sig.duration,
            "gap_after": sig.gap_after,
            "elongated": sig.elongated,
        })
    return out


def validate_filler(word: str, line_text: str) -> bool:
    """LLMのフィラー削除案が適用可能か(候補語リスト内・行内に1回だけ存在)"""
    return word in CONTEXTUAL_FILLERS and line_text.count(word) == 1


def remove_filler(text: str, word: str) -> str:
    """行からフィラー1語を除去する(後続の読点も一緒に、二重読点は整理)"""
    out = text.replace(f"{word}、", "", 1) if f"{word}、" in text else text.replace(word, "", 1)
    out = _RE_DUP_COMMA.sub("、", out)
    return out
