"""Whisperに渡す初期プロンプトの組み立て(純関数)のテスト。

利用者の辞書(名前・用語)を次回の文字起こしに渡す。Whisperがプロンプトとして
使えるのは直近223トークンまでで、超えた分は**先頭から**黙って捨てられる
(先頭にある言い淀みの文体例から消える)。だから組み立てる側で上限に収める。
"""

from pathlib import Path

import pytest

from backend.engines.asr.prompt import (
    PROMPT_TOKEN_LIMIT,
    VERBATIM_STYLE,
    build_initial_prompt,
    estimate_tokens,
    select_prompt_terms,
)

# ---- 従来と同じ形になること(辞書が空なら何も変わらない) ----

@pytest.mark.parametrize(
    "style, terms, expected",
    [
        # 辞書が空: 文体例だけ(従来の initial_prompt と一字一句同じ)
        (VERBATIM_STYLE, [], "えーと、あのー、そのー、なんか、うん。"),
        # 文体例も辞書も無ければプロンプト自体を渡さない(--prompt を付けない)
        (None, [], None),
        # 語は「、」でつなぎ「。」で閉じ、文体例とは半角空白で区切る(従来の形)
        (VERBATIM_STYLE, ["半導体", "箱ストア"],
         "えーと、あのー、そのー、なんか、うん。 半導体、箱ストア。"),
        (None, ["高田さん"], "高田さん。"),
        # 重複と空白だけの語は除く
        (None, ["半導体", " ", "半導体", "はやまる"], "半導体、はやまる。"),
        # 前後の空白は落とす
        (None, ["  ハッカソン "], "ハッカソン。"),
    ],
)
def test_build_initial_prompt(style, terms, expected):
    assert build_initial_prompt(style, terms) == expected


# ---- 上限に収める ----

def test_上限を超える分は後ろの語から落とす():
    terms = [f"固有名詞{i:03d}番" for i in range(200)]
    prompt = build_initial_prompt(VERBATIM_STYLE, terms)
    assert estimate_tokens(prompt) <= PROMPT_TOKEN_LIMIT
    # 優先順(並び順)の先頭は必ず入り、末尾は入らない
    assert "固有名詞000番" in prompt
    assert "固有名詞199番" not in prompt
    # 文体例は先頭に残る(上限超過で先頭から捨てられる事故が起きない)
    assert prompt.startswith(VERBATIM_STYLE)


def test_入らない長い語は飛ばして後ろの短い語を詰める():
    long_term = "魑魅魍魎" * 10  # 1語で上限近くを食う
    chosen = select_prompt_terms(
        ["半導体", long_term, "古着"], style=VERBATIM_STYLE, max_tokens=60
    )
    assert chosen == ["半導体", "古着"]


def test_語数の上限():
    terms = [f"語{i}" for i in range(50)]
    assert len(select_prompt_terms(terms, style=None, max_terms=30)) == 30


@pytest.mark.parametrize("max_tokens", [10, 30, 60, 120, PROMPT_TOKEN_LIMIT])
def test_どの上限でも見積もりが上限を超えない(max_tokens):
    terms = ["半導体", "株式会社サイバーエージェント", "はやまる", "NVIDIA", "ChatGPT",
             "箱ストア", "ハコストア", "文筆家", "東京都港区", "ゆいちゃん", "生成AI"] * 5
    chosen = select_prompt_terms(terms, style=None, max_tokens=max_tokens)
    prompt = build_initial_prompt(None, chosen)
    if prompt is not None:
        assert estimate_tokens(prompt) <= max_tokens


# ---- トークン数の見積もり ----

@pytest.mark.parametrize(
    "text, at_least",
    [
        # 実測(whisper large-v3 のトークナイザ)より少なく見積もらないこと。
        # 右の値は実測値(先頭に空白を足した形。faster-whisperがそうする)
        ("半導体", 4),
        ("反動体", 4),
        ("はやまる", 4),
        ("箱ストア", 5),
        ("高田さん", 4),
        ("NVIDIA", 3),
        ("文筆家", 5),
        ("魑魅魍魎", 9),
        ("株式会社サイバーエージェント", 14),
        ("えーと、あのー、そのー、なんか、うん。", 15),
        ("ｱｲｳ", 9),  # 半角カナは1文字3トークンになる
        ("𠮷野家", 7),
    ],
)
def test_見積もりは実測を下回らない(text, at_least):
    assert estimate_tokens(text) >= at_least


def test_見積もりは空文字でも先頭の空白ぶんを数える():
    assert estimate_tokens("") == 1


# ---- 本物のトークナイザでの照合(手元にあれば) ----

def _find_tokenizer() -> Path | None:
    hub = Path.home() / ".cache" / "huggingface" / "hub"
    for repo in ("models--openai--whisper-large-v3", "models--Systran--faster-whisper-large-v3"):
        hits = sorted((hub / repo).glob("snapshots/*/tokenizer.json"))
        if hits:
            return hits[0]
    return None


def test_本物のトークナイザでも上限を超えない():
    """見積もりが実際のトークン数以上であることを本物で確かめる。

    トークナイザはモデルと一緒に落ちてくるので、無い機体(CI)では飛ばす。
    1文字1トークンの表(_SINGLE_TOKEN_CHARS)が古くなっていないかもここで分かる。
    """
    path = _find_tokenizer()
    if path is None:
        pytest.skip("whisperのtokenizer.jsonが手元に無い")
    from tokenizers import Tokenizer

    from backend.engines.asr.prompt import _SINGLE_TOKEN_CHARS

    tok = Tokenizer.from_file(str(path))

    def count(text: str) -> int:
        return len(tok.encode(" " + text, add_special_tokens=False).ids)

    for ch in _SINGLE_TOKEN_CHARS:
        assert len(tok.encode(ch, add_special_tokens=False).ids) == 1, ch

    terms = ["半導体", "はやまる", "箱ストア", "高田さん", "NVIDIA", "ChatGPT", "文筆家",
             "株式会社サイバーエージェント", "ゆいちゃん", "東京都港区", "古着", "ハッカソン",
             "生成AI", "切り抜き", "魑魅魍魎", "𠮷野家", "髙島屋", "ｱｲｳｴｵ"] * 6
    prompt = build_initial_prompt(VERBATIM_STYLE, terms)
    assert count(prompt) <= estimate_tokens(prompt) <= PROMPT_TOKEN_LIMIT
