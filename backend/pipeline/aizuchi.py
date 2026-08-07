"""相槌判定。

下記パターン「だけ」で構成される短いセグメントを相槌とみなす。
誤って本編を削らないよう、意味を持ちうる語はパターンに入れないこと。
"""

import re

AIZUCHI_WORDS = (
    "うん|うーん|ううん|うんうん|はい|はいはい|ええ|えー|えっ|あー|ああ|"
    "おー|おお|ほう|へえ|へー|ふーん|ふん|ん|んー|なるほど|なるほどなるほど|"
    "たしかに|確かに|そう|そうそう|そうですね|そうですよね|そうなんですね|"
    "そうなんだ|ですよね|よね|ね|まあ|うわー|おっけー|OK|オッケー"
)
AIZUCHI_PATTERN = re.compile(f"^({AIZUCHI_WORDS})+$")
DEFAULT_MAX_DURATION = 2.0  # 秒。これより長い発話は相槌パターンでも残す

_PUNCT = re.compile(r"[、。,,..!!??\s・…〜]")


def is_aizuchi(text: str, duration: float, max_duration: float = DEFAULT_MAX_DURATION) -> bool:
    if duration > max_duration:
        return False
    normalized = _PUNCT.sub("", text)
    if not normalized:
        return True  # 記号だけのセグメントも除外
    return bool(AIZUCHI_PATTERN.match(normalized))
