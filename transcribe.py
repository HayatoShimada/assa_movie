#!/usr/bin/env python3
"""
RTX PRO 6000 Blackwell Max-Q 向け faster-whisper 文字起こしスクリプト
話者分離(pyannote.audio)+ 相槌除外つき

使い方: uv run python transcribe.py <動画/音声ファイル> [言語コード(例: ja)]
出力: 同名の .srt / .txt ファイル(話者ラベル付き)

話者分離を使うには hf_token.txt に HuggingFace トークンを記述してください
(取得手順は hf_token.txt 内に記載)。トークンが無い場合は話者分離を
スキップし、文字起こし+相槌除外のみ実行します。

処理の実体は backend/ 配下のモジュールにあり、このスクリプトはCLIラッパ。
"""

import sys
from pathlib import Path

from backend.engines.asr.fasterwhisper import FasterWhisperEngine
from backend.engines.diarize import pyannote as diarize
from backend.pipeline import audio as audio_io
from backend.pipeline.aizuchi import is_aizuchi
from backend.pipeline.subtitle import format_timestamp

# ---- モデル設定 ----
# 96GB VRAMがあるので large-v3 をフル精度float16で余裕で動かせます。
# 速度を最優先したい場合は "large-v3-turbo" に変更してください。
MODEL_SIZE = "large-v3"

# ---- 話者分離の設定 ----
NUM_SPEAKERS = 2  # 対談の人数。人数が不明な場合は None(自動推定)
# community-1(最新)は規約未同意のため、同意済みの3.1を使用。
DIARIZATION_MODEL = "pyannote/speaker-diarization-3.1"
TOKEN_FILE = Path(__file__).parent / "hf_token.txt"
# 話者ラベルの表示名を直接指定する場合(通常は不要。下の自動判定が優先される)
# 例: SPEAKER_NAMES = {"SPEAKER_00": "しまだ", "SPEAKER_01": "ゲスト"}
SPEAKER_NAMES = {}

# 2人対談で男女1名ずつの場合、声の高さ(基本周波数)で自動的に名前を割り当てる。
# 使わない場合は両方 None にする(話者1/話者2 表示になる)。
MALE_NAME = "はやまる"
FEMALE_NAME = "高田さん"


def main():
    if len(sys.argv) < 2:
        print("使い方: uv run python transcribe.py <ファイルパス> [言語コード(省略可 例: ja)]")
        sys.exit(1)

    input_path = Path(sys.argv[1])
    language = sys.argv[2] if len(sys.argv) > 2 else None  # Noneなら自動検出

    # 動画/音声を16kHzモノラルにデコード(PyAV使用なので.movもそのまま扱える)
    print(f"音声をデコード中: {input_path}")
    audio = audio_io.decode(input_path)

    # ---- 話者分離 ----
    turns = []
    token = diarize.load_hf_token(TOKEN_FILE)
    if token:
        print(f"話者分離を実行中... (モデル: {DIARIZATION_MODEL})")
        turns = diarize.run_diarization(
            audio, token, model=DIARIZATION_MODEL, num_speakers=NUM_SPEAKERS
        )
        speakers = sorted({label for _, _, label in turns})
        print(f"検出された話者: {len(speakers)}人 ({', '.join(speakers)})")
    else:
        print("hf_token.txt にトークンが無いため話者分離をスキップします。")

    label_map = (
        diarize.build_label_map(
            audio, turns, male_name=MALE_NAME, female_name=FEMALE_NAME,
            speaker_names=SPEAKER_NAMES,
        )
        if turns
        else {}
    )

    # ---- 文字起こし ----
    print(f"モデル {MODEL_SIZE} を読み込み中... (初回はダウンロードに数分かかります)")
    engine = FasterWhisperEngine(model_size=MODEL_SIZE)

    print("文字起こし開始")
    result = engine.transcribe(audio, language=language)
    print(f"検出言語: {result.language} (確度 {result.language_probability:.2f})")

    srt_path = input_path.with_suffix(".srt")
    txt_path = input_path.with_suffix(".txt")
    aizuchi_count = 0
    index = 0

    with open(srt_path, "w", encoding="utf-8") as srt_f, \
         open(txt_path, "w", encoding="utf-8") as txt_f:

        for seg in result.segments:
            text = seg.text
            if is_aizuchi(text, seg.end - seg.start):
                aizuchi_count += 1
                continue

            speaker = diarize.assign_speaker(seg, turns) if turns else None
            prefix = f"{label_map[speaker]}: " if speaker else ""
            start = format_timestamp(seg.start)
            end = format_timestamp(seg.end)

            index += 1
            srt_f.write(f"{index}\n{start} --> {end}\n{prefix}{text}\n\n")
            txt_f.write(f"{prefix}{text}\n")
            print(f"[{start} - {end}] {prefix}{text}")

    print("\n完了しました。")
    print(f"除外した相槌: {aizuchi_count}件")
    print(f"字幕ファイル: {srt_path}")
    print(f"テキストファイル: {txt_path}")


if __name__ == "__main__":
    main()
