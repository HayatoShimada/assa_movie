"""M22: whisper.cppエンジンのテスト(バイナリ・モデル・GPU不要)"""

from pathlib import Path

import numpy as np
import pytest

from backend.engines.asr.whispercpp import (
    WhisperCppEngine,
    build_command,
    is_available,
    parse_full_json,
)

# whisper-cli --output-json-full の実出力を縮めたもの
SAMPLE = {
    "transcription": [
        {
            "offsets": {"from": 0, "to": 3800},
            "text": "っていう話してると、",
            "tokens": [
                {"text": "[_BEG_]", "offsets": {"from": 0, "to": 0}, "p": 0.93},
                {"text": "っていう", "offsets": {"from": 140, "to": 1420}, "p": 0.11},
                {"text": "話", "offsets": {"from": 1510, "to": 1800}, "p": 0.62},
                {"text": "して", "offsets": {"from": 1800, "to": 2500}, "p": 0.58},
                {"text": "る", "offsets": {"from": 2500, "to": 2880}, "p": 0.82},
                {"text": "と", "offsets": {"from": 2880, "to": 3290}, "p": 1.0},
                {"text": "、", "offsets": {"from": 3290, "to": 3290}, "p": 0.77},
                {"text": "<|endoftext|>", "offsets": {"from": 3800, "to": 3800}, "p": 0.4},
            ],
        }
    ]
}


# ---- parse_full_json(純関数) ----

def test_parse_extracts_words_with_probability():
    words = parse_full_json(SAMPLE)
    assert [w.text for w in words] == ["っていう", "話", "して", "る", "と", "、"]
    # 単語確率はフィラー判定のシグナルなので必ず引き継ぐ
    assert words[0].probability == pytest.approx(0.11)
    assert words[4].probability == pytest.approx(1.0)


def test_parse_converts_ms_to_seconds():
    w = parse_full_json(SAMPLE)[0]
    assert w.start == pytest.approx(0.14)
    assert w.end == pytest.approx(1.42)


def test_parse_drops_special_tokens():
    """[_BEG_] や <|endoftext|> は字幕に出してはいけない"""
    assert all("_BEG_" not in w.text and "endoftext" not in w.text for w in parse_full_json(SAMPLE))


def test_parse_keeps_punctuation():
    """句読点は字幕の文末分割に使うので落とさない(長さ0でも残す)"""
    assert "、" in [w.text for w in parse_full_json(SAMPLE)]


def test_parse_gives_zero_length_tokens_a_duration():
    """from == to のトークンが1割ほど混ざるので、表示時間を持たせる"""
    comma = next(w for w in parse_full_json(SAMPLE) if w.text == "、")
    assert comma.end > comma.start


def test_parse_empty():
    assert parse_full_json({"transcription": []}) == []


# ---- build_command ----

def test_build_command_requests_full_json_and_beam():
    cmd = build_command(
        Path("/bin/whisper-cli"), Path("/m/ggml.bin"), Path("/tmp/a.wav"),
        Path("/tmp/out"), language="ja", beam_size=5, initial_prompt="えーと、",
    )
    assert cmd[0] == "/bin/whisper-cli"
    # -ojf がトークンのタイムスタンプと確率を有効にする(これが要)
    assert "-ojf" in cmd
    # -ml を付けると句読点が落ちるので付けてはいけない
    assert "-ml" not in cmd
    assert cmd[cmd.index("-l") + 1] == "ja"
    assert cmd[cmd.index("-bs") + 1] == "5"
    assert cmd[cmd.index("--prompt") + 1] == "えーと、"


def test_build_command_without_prompt():
    cmd = build_command(
        Path("/bin/whisper-cli"), Path("/m/ggml.bin"), Path("/tmp/a.wav"), Path("/tmp/out"),
    )
    assert "--prompt" not in cmd


# ---- 可用性の判定 ----

def test_is_available_requires_binary_and_model(tmp_path):
    binary, model = tmp_path / "whisper-cli", tmp_path / "ggml.bin"
    assert is_available(binary, model) is False
    binary.write_text("#!/bin/sh")
    binary.chmod(0o755)
    assert is_available(binary, model) is False  # モデルが無い
    model.write_bytes(b"x")
    assert is_available(binary, model) is True


# ---- エンジン統合(CLI実行を差し替え) ----

def test_transcribe_builds_segments_from_tokens(tmp_path):
    import json

    calls = []

    def fake_run(cmd, out_base):
        calls.append(cmd)
        out_base.with_suffix(".json").write_text(json.dumps(SAMPLE), encoding="utf-8")

    engine = WhisperCppEngine(
        binary=tmp_path / "whisper-cli", model=tmp_path / "ggml.bin", runner=fake_run
    )
    progressed = []
    result = engine.transcribe(
        np.zeros(16000 * 4, dtype=np.float32), language="ja", progress=progressed.append
    )
    assert calls, "CLIが呼ばれていない"
    assert result.segments and result.segments[0].text == "っていう話してると、"
    words = result.segments[0].words
    assert words and all(w.probability is not None for w in words)
    assert progressed[-1] == 1.0


def test_unload_is_safe():
    WhisperCppEngine(binary=Path("/x"), model=Path("/y")).unload()
