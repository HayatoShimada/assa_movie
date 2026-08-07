"""字幕・テキストの書き出し(折返し・禁則処理・SRT/ASS生成)。

すべて純関数。折返しロジックはフロントのCSSプレビューでも同一のテストケースを
通すこと(FRONTEND_DESIGN.md)。
"""

from dataclasses import dataclass, field
from pathlib import Path

# 行頭に来てはいけない文字(句読点・閉じ括弧・小書き仮名・長音など)
KINSOKU_HEAD = set(
    "、。,,..!!??)〕]}」』〉》ー・:;゛゜ゝゞ々"
    "ぁぃぅぇぉっゃゅょゎァィゥェォッャュョヮ…‥"
)
# 行末に来てはいけない文字(開き括弧)
KINSOKU_TAIL = set("「『((〔[{〈《")

# ぶら下げで1行に収める超過許容文字数
HANG_ALLOWANCE = 2


def wrap_subtitle(text: str, max_chars: int = 15) -> list[str]:
    """日本語向けの字幕折返し。

    - 最大文字数で折り返す
    - 行頭禁則文字は前の行にぶら下げる(最大 HANG_ALLOWANCE 文字超過)
    - 行末禁則文字(開き括弧)は次の行へ追い出す
    """
    if max_chars < 2:
        max_chars = 2
    lines: list[str] = []
    i, n = 0, len(text)
    while i < n:
        end = min(i + max_chars, n)
        # ぶら下げ: 次の文字が行頭禁則なら行末に含める(上限あり)
        while end < n and text[end] in KINSOKU_HEAD and (end - i) < max_chars + HANG_ALLOWANCE:
            end += 1
        # ぶら下げ上限でも次行頭が禁則のままなら、安全な切れ目まで戻す(追い出し)
        if end < n and text[end] in KINSOKU_HEAD:
            back = end
            while back > i + 1 and text[back] in KINSOKU_HEAD:
                back -= 1
            if text[back] not in KINSOKU_HEAD:
                end = back
        # 行末禁則: 開き括弧は次の行へ送る
        while end > i + 1 and text[end - 1] in KINSOKU_TAIL:
            end -= 1
        lines.append(text[i:end])
        i = end
    return lines or [""]


def min_display_duration(text: str, per_char: float = 0.15, minimum: float = 1.0) -> float:
    """読み切れる最短表示時間(秒)。文字数×0.15秒、下限1秒"""
    return max(minimum, len(text) * per_char)


def format_timestamp(seconds: float) -> str:
    ms = int((seconds - int(seconds)) * 1000)
    s = int(seconds)
    h, rem = divmod(s, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def format_ass_time(seconds: float) -> str:
    cs = int(round((seconds - int(seconds)) * 100))
    s = int(seconds)
    if cs == 100:  # 丸めで繰り上がった場合
        cs = 0
        s += 1
    h, rem = divmod(s, 3600)
    m, s = divmod(rem, 60)
    return f"{h:d}:{m:02d}:{s:02d}.{cs:02d}"


def srt_block(index: int, start: float, end: float, text: str) -> str:
    return f"{index}\n{format_timestamp(start)} --> {format_timestamp(end)}\n{text}\n\n"


def write_srt(path: Path, entries: list[tuple[float, float, str]]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for i, (start, end, text) in enumerate(entries, start=1):
            f.write(srt_block(i, start, end, text))


def write_txt(path: Path, texts: list[str]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for text in texts:
            f.write(text + "\n")


# ---- ASS生成 ----

# 話者に順番に割り当てる文字色(ASSは &HBBGGRR)
SPEAKER_ASS_COLORS = [
    "&H00FFFFFF",  # 白
    "&H0000D7FF",  # 黄(金)
    "&H00FFD700",  # 水色
    "&H00B469FF",  # ピンク
]


@dataclass
class SubtitleStyle:
    font_name: str = "Noto Sans JP"
    font_size: int = 48
    alignment: int = 2          # ASSの1-9(テンキー配置)。2=下中央
    margin_v: int = 40
    outline: int = 2
    max_chars_per_line: int = 15
    play_res_x: int = 1920
    play_res_y: int = 1080


@dataclass
class AssEvent:
    start: float
    end: float
    text: str
    speaker: str | None = None


def build_ass(events: list[AssEvent], style: SubtitleStyle = SubtitleStyle()) -> str:
    """字幕イベント列からASSファイルの内容を生成する。

    - 折返し・禁則は wrap_subtitle を適用(ASSの改行は \\N)
    - 話者ごとにスタイル(文字色)を割り当てる
    """
    speakers = sorted({e.speaker for e in events if e.speaker})
    style_of = {
        sp: (f"S{i}", SPEAKER_ASS_COLORS[i % len(SPEAKER_ASS_COLORS)])
        for i, sp in enumerate(speakers)
    }

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {style.play_res_x}
PlayResY: {style.play_res_y}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
"""
    style_lines = [
        f"Style: Default,{style.font_name},{style.font_size},&H00FFFFFF,&H000000FF,"
        f"&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,{style.outline},1,"
        f"{style.alignment},60,60,{style.margin_v},1"
    ]
    for sp in speakers:
        name, color = style_of[sp]
        style_lines.append(
            f"Style: {name},{style.font_name},{style.font_size},{color},&H000000FF,"
            f"&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,{style.outline},1,"
            f"{style.alignment},60,60,{style.margin_v},1"
        )

    event_lines = [
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    for e in events:
        wrapped = "\\N".join(wrap_subtitle(e.text, style.max_chars_per_line))
        style_name = style_of.get(e.speaker, ("Default", ""))[0] if e.speaker else "Default"
        event_lines.append(
            f"Dialogue: 0,{format_ass_time(e.start)},{format_ass_time(e.end)},"
            f"{style_name},{e.speaker or ''},0,0,0,,{wrapped}"
        )

    return header + "\n".join(style_lines) + "\n".join([""] + event_lines[1:]) + "\n"


def segments_to_events(
    segments: list[dict],
    clip_start: float = 0.0,
    clip_end: float | None = None,
    strip_speaker_prefix: bool = True,
) -> list[AssEvent]:
    """DBのセグメント行(dict)を、クリップ相対時刻のASSイベントに変換する。

    - 相槌(is_aizuchi)と非採用(subtitle_show が *hide)は除外
    - 表示時間は min_display_duration まで自動延長(次のイベント開始は超えない)
    """
    visible = [
        s for s in segments
        if not s.get("is_aizuchi")
        and s.get("subtitle_show", "auto_show") in ("auto_show", "user_show")
        and (clip_end is None or s["start"] < clip_end)
        and s["end"] > clip_start
    ]
    events: list[AssEvent] = []
    for i, s in enumerate(visible):
        text = s["text"]
        if strip_speaker_prefix and s.get("speaker") and text.startswith(f"{s['speaker']}: "):
            text = text[len(s["speaker"]) + 2:]
        start = max(s["start"] - clip_start, 0.0)
        end = s["end"] - clip_start
        end = max(end, start + min_display_duration(text))
        if i + 1 < len(visible):
            next_start = visible[i + 1]["start"] - clip_start
            if next_start > start:
                end = min(end, next_start)
        if clip_end is not None:
            end = min(end, clip_end - clip_start)
        events.append(AssEvent(start=start, end=end, text=text, speaker=s.get("speaker")))
    return events
