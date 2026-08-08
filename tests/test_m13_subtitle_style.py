"""M13: 字幕スタイル拡張(フォント・色・背景)と解像度相対スケーリングのテスト"""

import pytest

from backend.core.config import Settings
from backend.pipeline.subtitle import (
    AssEvent,
    SubtitleStyle,
    build_ass,
    hex_to_ass,
    scaled_style,
)


# ---- hex_to_ass(テーブル駆動) ----

@pytest.mark.parametrize(
    "hex_color, transparency, expected",
    [
        ("#FFFFFF", 0.0, "&H00FFFFFF"),   # 白・不透明
        ("#000000", 0.5, "&H80000000"),   # 半透明黒(従来のBackColourと同値)
        ("#FF0000", 0.0, "&H000000FF"),   # 赤はBGR反転
        ("#00D7FF", 0.0, "&H00FFD700"),   # 金色
        ("ffffff", 0.0, "&H00FFFFFF"),    # #なし・小文字も許容
        ("#FFFFFF", 1.0, "&HFFFFFFFF"),   # 完全透明
    ],
)
def test_hex_to_ass_table(hex_color, transparency, expected):
    assert hex_to_ass(hex_color, transparency) == expected


def test_hex_to_ass_invalid_falls_back_to_white():
    assert hex_to_ass("赤", 0.0) == "&H00FFFFFF"


# ---- scaled_style: 解像度相対化 ----

def test_scaled_style_1080p_matches_legacy_values():
    """1920×1080では従来のハードコード値と完全一致(後方互換の要)"""
    s = Settings(_env_file=None)
    st = scaled_style(s, 1920, 1080, "bottom", 0)
    assert st.font_size == 48
    assert st.margin_v == 40
    assert st.margin_l == 60 and st.margin_r == 60
    assert st.outline == 2
    assert st.alignment == 2
    assert st.play_res_x == 1920 and st.play_res_y == 1080


def test_scaled_style_portrait_keeps_width_ratio():
    """縦動画(1080×1920)ではフォントは幅比率で縮む(48*1080/1920=27)"""
    s = Settings(_env_file=None)
    st = scaled_style(s, 1080, 1920, "bottom", 0)
    assert st.font_size == 27          # 幅に対する比率が横と同じ2.5%
    assert st.margin_l == 34           # 60*1080/1920=33.75→34
    assert st.margin_v == 71           # 高さ基準 40*1920/1080=71.1→71
    assert st.play_res_x == 1080 and st.play_res_y == 1920


@pytest.mark.parametrize(
    "position, offset, alignment, margin_v",
    [
        ("top", 0, 8, 40),
        ("top", 20, 8, 60),      # +は下方向 → topでは余白が増える
        ("center", 50, 5, 0),    # centerはMarginVを使わない(\posでずらす)
        ("bottom", 0, 2, 40),
        ("bottom", 30, 2, 10),   # +は下方向 → bottomでは余白が減る
        ("bottom", 300, 2, 0),   # クランプ(±120)後に下限0
    ],
)
def test_scaled_style_position_table(position, offset, alignment, margin_v):
    s = Settings(_env_file=None)
    st = scaled_style(s, 1920, 1080, position, offset)
    assert st.alignment == alignment
    assert st.margin_v == margin_v


def test_center_offset_is_carried_and_scaled():
    """中央配置のずらし量は margin_v ではなく center_offset_y に入る"""
    s = Settings(_env_file=None)
    st = scaled_style(s, 1920, 1080, "center", 54)
    assert st.margin_v == 0  # ASSは中央揃えでMarginVを無視する
    assert st.center_offset_y == 54
    # 縦出力では高さ比率でスケールする(1920/1080=約1.78倍)
    assert scaled_style(s, 1080, 1920, "center", 54).center_offset_y == 96
    # 中央以外では使わない
    assert scaled_style(s, 1920, 1080, "bottom", 54).center_offset_y == 0


def test_build_ass_center_offset_emits_pos():
    """中央でずらす場合は \\pos で位置を明示する(MarginVが効かないため)"""
    style = SubtitleStyle(alignment=5, center_offset_y=54, play_res_x=1080, play_res_y=1920)
    out = build_ass(EVENTS, style)
    # 画面中央(540, 960)から54px下
    assert "{\\pos(540,1014)}" in out
    dialogues = [l for l in out.splitlines() if l.startswith("Dialogue:")]
    assert all("{\\pos(540,1014)}" in l for l in dialogues)


def test_build_ass_center_without_offset_has_no_pos():
    out = build_ass(EVENTS, SubtitleStyle(alignment=5, center_offset_y=0))
    assert "\\pos(" not in out


def test_build_ass_non_center_has_no_pos():
    """上下配置はMarginVで動くので\\posは出さない"""
    out = build_ass(EVENTS, SubtitleStyle(alignment=2, center_offset_y=54))
    assert "\\pos(" not in out


def test_scaled_style_carries_style_settings():
    s = Settings(_env_file=None)
    s.subtitle_font_family = "BIZ UDGothic"
    s.subtitle_text_color = "#FFEE00"
    s.subtitle_bg = "box"
    s.subtitle_bg_color = "#112233"
    s.subtitle_bg_opacity = 0.8
    s.subtitle_speaker_colors = False
    st = scaled_style(s, 1920, 1080, "bottom", 0)
    assert st.font_name == "BIZ UDGothic"
    assert st.text_color == "#FFEE00"
    assert st.bg == "box" and st.bg_color == "#112233" and st.bg_opacity == 0.8
    assert st.speaker_colors is False


# ---- build_ass: 背景ボックス・文字色・話者色オフ ----

EVENTS = [
    AssEvent(start=0.0, end=2.0, text="こんにちは", speaker="話者A"),
    AssEvent(start=2.0, end=4.0, text="どうも", speaker="話者B"),
]


def test_build_ass_default_is_outline_style():
    out = build_ass(EVENTS, SubtitleStyle())
    # BorderStyle=1(縁取り)・従来と同じ色構成
    assert ",1,2,1,2,60,60,40,1" in out.replace(" ", "")
    assert "&H00FFFFFF" in out


def test_build_ass_box_background():
    style = SubtitleStyle(bg="box", bg_color="#000000", bg_opacity=0.7)
    out = build_ass(EVENTS, style)
    # BorderStyle=3(背景ボックス)とBackColour(透明度0.3→0x4D)
    line = next(l for l in out.splitlines() if l.startswith("Style: Default"))
    fields = line.split(",")
    assert fields[15] == "3"           # BorderStyle
    assert fields[6] == "&H4D000000"   # BackColour(alpha=1-0.7)


def test_build_ass_text_color_applied():
    out = build_ass(EVENTS, SubtitleStyle(text_color="#FF0000", speaker_colors=False))
    line = next(l for l in out.splitlines() if l.startswith("Style: Default"))
    assert line.split(",")[3] == "&H000000FF"


def test_build_ass_speaker_colors_off_uses_default_style():
    out = build_ass(EVENTS, SubtitleStyle(speaker_colors=False))
    assert "Style: S0" not in out
    assert all(",Default," in l for l in out.splitlines() if l.startswith("Dialogue:"))


def test_build_ass_font_family():
    out = build_ass(EVENTS, SubtitleStyle(font_name="Noto Serif JP"))
    assert "Style: Default,Noto Serif JP," in out


# ---- フォント列挙 ----

def test_parse_fc_list():
    from backend.api.settings_api import parse_fc_list

    raw = "\n".join([
        "Noto Sans CJK JP,Noto Sans CJK JP Bold",
        "Noto Sans JP",
        "Noto Sans JP",  # 重複
        "BIZ UDGothic,BIZ UDゴシック",
        "",
    ])
    fonts = parse_fc_list(raw)
    assert fonts == sorted(set(fonts))  # 重複なし・ソート済み
    assert "Noto Sans JP" in fonts
    assert "BIZ UDGothic" in fonts  # カンマ区切りの先頭ファミリ名を使う
