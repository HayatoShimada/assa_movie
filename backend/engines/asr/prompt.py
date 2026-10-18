"""Whisperに渡す初期プロンプトの組み立て(純関数)。

利用者の辞書(名前・用語。backend/core/user_terms.py)の語を、次の文字起こしで
Whisperに「この語が出てくる」というヒントとして渡す。whisper.cppは `--prompt`、
faster-whisperは `initial_prompt` に、ここで組み立てた同じ文字列を渡す。

**上限**: Whisperがプロンプトとして使えるのは直近223トークンまで
(faster-whisper: `previous_tokens[-(448 // 2 - 1):]`、whisper.cpp: `n_text_ctx / 2` から
直前を示す印の1トークンを引いた分)。超えた分は**先頭から**黙って捨てられるので、
先頭に置いた言い淀みの文体例から消えていく。だから組み立てる側で上限に収める。

トークン数はモデルのトークナイザが無いと正確には数えられない(GPU機のwhisper.cppは
ggmlモデルの中に持っていて、Pythonからは読めない)。そこで「実際より少なく
見積もらない」上限値で数える(estimate_tokens)。根拠と照合は
tests/engines/test_asr_prompt.py(手元にtokenizer.jsonがあれば本物と突き合わせる)。

**hotwordsは使わない**: faster-whisperの `hotwords` は30秒ごとの窓すべてで、直前の文脈
(最大223トークン)に上乗せされる。1窓はプロンプトと出力を合わせて448トークンなので、
早口の日本語では出力側の枠が足りなくなり発話を取りこぼしうる。whisper.cppに同じ仕組みが
無いこともあり、両エンジンとも初期プロンプトだけで渡す。
"""

from collections.abc import Iterable

# プロンプトとして使われる最大トークン数(上の説明を参照)
PROMPT_TOKEN_LIMIT = 223
# 語数の上限。並べすぎると語の羅列を出力に混ぜる(幻覚)恐れが増える。
# 辞書導入前の用語集(terms[:30])と同じ値にして、従来の挙動を変えない
MAX_PROMPT_TERMS = 30
# フィラーを含む文体例。与えるとWhisperが言い淀みを忠実に転写する(asr_verbatim_style)
VERBATIM_STYLE = "えーと、あのー、そのー、なんか、うん。"
TERM_SEPARATOR = "、"
TERM_TERMINATOR = "。"

# whisper large-v3 のトークナイザで1文字が1トークンになる日本語の文字(1083字)。
# よく使うかな・漢字・約物はほぼここに入る。表に無い文字は多めに見積もる。
# 生成元: tokenizer.json で `len(encode(ch)) == 1` の文字を U+3000-30FF・
# U+4E00-9FFF・U+FF00-FFEF から集めた(照合は test_本物のトークナイザでも上限を超えない)
_SINGLE_TOKEN_CHARS = frozenset(
    "、。々《》「」『』【】〜ぁあいうぇえぉおかがきぎくぐけげこごさざしじすずせぜそぞ"
    "ただちっつてでとどなにねのはばひびふぶへべほまみむめもゃやゆょよらりるれろわをん"
    "゚ァアィイウェエオカガキクグケゲコゴサシジスズセソタダチッツテデトドナニノハバパ"
    "ヒビピフブプベホボポマミムメモャヤュョラリルレロワン・ー一七万丈三上下不且世东两"
    "並个中为主久么之乐九也乾了事二于五井些亞交享京亮亲人什今介从仔他付代令以们件任份"
    "伊休会但位低住佐体何作你使來例便係保信俺個倍們倒候值假做停健備傳傷像僕價億儿元兄"
    "先光克兒入內全兩八公六共关其具内円再况冷出分切列刚初別利别到制刻則前剛力办功加动"
    "助動務勝包化北區十千升午半单南卡印危即原厲去參又及友反发叔取受口古句另只叫可台史"
    "右号司吃各合吉同名后向吗君否吧听吸呀告呢周味呵呼命和品哇哈哎員哥哦哪唉唱商啊問啦"
    "喂喔喜喝單嗎嗯嘉嘛嘿器囉四回因国國團土在地场坐块型城基報場塊塔境壓士声変夏外多夜"
    "夠夢大天太夫失头奇女奶她好如妈妳妹始姐姑委娘婆媽子字存学孩學它守安完官定实実客宮"
    "害家容密富察實对対将將專對導小少就局展山島川州工左巧差己已巴市布师希師帶常幕幫干"
    "平年幸幹幾应底店府度建开式引弟张張強当形影往待很後得從微德心必志忘忙快念怎怕怖思"
    "急性怪总恐恩恭息您情惜想意愛感態慢懂應成我或戰戲房所手才打找技把抓投报抱抽拉拍拜"
    "括拿持指按挑挺掉排接控推掰提換搞播擊據支收改攻放政故效救教敢数整數文料斯新方於无"
    "日早时明易星春昨是時晚普景曲更書曾最會月有朋服望朝期木未本机李村束条来杯東松板林"
    "果染查校样根格案條棒楚業楽概構様樂標模樣樹橋機權次欢欸款歌歡止正此步武歲死段殺母"
    "每毒比毛民气気氣水永求江決沒没油治況法波注洗洲活流海消深混清港源準滿漂演澤灣火点"
    "為無然照熱爆爱父爷爸爾片版牛物特率王玩现班現球理瓜甚甜生產用田由电男画界留番畫當"
    "疫病痛発登發白百的皆皇皮目直相看真眼眾着睡知石破確示社神票福私秋种科秒程種稱究空"
    "突立站笑第等答算管節簡米粉精糖系紀約紅級素累細紹終組結給統經続網緊線練總繼續经结"
    "给置羅美義習翻老考者而耶聊聞聯聲聽肉背胡能腳自至與興舉舒舞般良色节花苦英茶菜華萬"
    "落葉著處號蛋血行街表被裝裡西要見視親覺觀见观视觉角解言訂計記設許訴評試話該認語說"
    "誰調談請論講謝識警議護變讓讚让记讲诉话该说请谁谢豆象買費資質賽走起超越趣足跑跟路"
    "跳身車軍較輕轉辛辦边过迎近还这进追退送透這通速造連週進遊運過道達違遠選還邊那部都"
    "配酒醒醫里重野量金鉄錢錯録鐘钟钱错長长門開間閱關问间防阿降限院除陳陽隊際隨險隻难"
    "集離難雨雪電需青非面音預頭頻顆題願類顯频题風风飛食飯首香馬马體高髙鬼魔魚麻麼黃黑"
    "點黨龍"
)


def _is_kana(ch: str) -> bool:
    return 0x3040 <= ord(ch) <= 0x30FF


def estimate_tokens(text: str) -> int:
    """プロンプトのトークン数を、実際より少なくならないように見積もる。

    - 先頭に1(faster-whisperは先頭に空白を足してからトークン化する)
    - ASCII・表にある日本語の文字は1文字1トークン
    - 表に無いかなは2(全かなの実測の最大)
    - それ以外はUTF-8のバイト数(バイト単位のBPEはバイト数を超えない)

    文字ごとの上限の足し算なので、実測(whisper large-v3)の1.1〜1.3倍程度になる。
    """
    n = 1
    for ch in text:
        if ord(ch) < 0x80 or ch in _SINGLE_TOKEN_CHARS:
            n += 1
        elif _is_kana(ch):
            n += 2
        else:
            n += len(ch.encode("utf-8"))
    return n


def _compose(style: str | None, terms: list[str]) -> str | None:
    """文体例と語の並びからプロンプト文字列を作る(辞書導入前と同じ形)"""
    parts = []
    if style:
        parts.append(style)
    if terms:
        parts.append(TERM_SEPARATOR.join(terms) + TERM_TERMINATOR)
    return " ".join(parts) or None


def select_prompt_terms(
    terms: Iterable[str],
    style: str | None = None,
    *,
    max_tokens: int = PROMPT_TOKEN_LIMIT,
    max_terms: int = MAX_PROMPT_TERMS,
) -> list[str]:
    """上限に収まる語を、並び順(=優先順)に選ぶ。

    入らない長い語は飛ばして、後ろの短い語で残りを詰める。重複・空は除く。
    """
    chosen: list[str] = []
    seen: set[str] = set()
    for raw in terms:
        term = raw.strip()
        if not term or term in seen:
            continue
        seen.add(term)
        if len(chosen) >= max_terms:
            break
        prompt = _compose(style, [*chosen, term])
        if prompt is not None and estimate_tokens(prompt) <= max_tokens:
            chosen.append(term)
    return chosen


def build_initial_prompt(
    style: str | None,
    terms: Iterable[str],
    *,
    max_tokens: int = PROMPT_TOKEN_LIMIT,
    max_terms: int = MAX_PROMPT_TERMS,
) -> str | None:
    """Whisperに渡す初期プロンプト。何も渡すものが無ければNone(--promptを付けない)。

    辞書が空なら文体例だけになり、辞書導入前と一字一句同じになる。
    """
    chosen = select_prompt_terms(terms, style, max_tokens=max_tokens, max_terms=max_terms)
    return _compose(style, chosen)
