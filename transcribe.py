#!/usr/bin/env python3
"""
RTX PRO 6000 Blackwell Max-Q 向け faster-whisper 文字起こしスクリプト
話者分離(pyannote.audio)+ 相槌除外つき

使い方: uv run python transcribe.py <動画/音声ファイル> [言語コード(例: ja)]
出力: 同名の .srt / .txt ファイル(話者ラベル付き)

話者分離を使うには hf_token.txt に HuggingFace トークンを記述してください
(取得手順は hf_token.txt 内に記載)。トークンが無い場合は話者分離を
スキップし、文字起こし+相槌除外のみ実行します。
"""

import os
import re
import sys
from pathlib import Path

from faster_whisper import WhisperModel
from faster_whisper.audio import decode_audio

# ---- モデル設定 ----
# 96GB VRAMがあるので large-v3 をフル精度float16で余裕で動かせます。
# 速度を最優先したい場合は "large-v3-turbo" に変更してください。
MODEL_SIZE = "large-v3"

# ---- 話者分離の設定 ----
NUM_SPEAKERS = 2  # 対談の人数。人数が不明な場合は None(自動推定)
# community-1(最新)は規約未同意のため、同意済みの3.1を使用。
# https://huggingface.co/pyannote/speaker-diarization-community-1 に同意すれば切り替え可。
DIARIZATION_MODEL = "pyannote/speaker-diarization-3.1"
TOKEN_FILE = Path(__file__).parent / "hf_token.txt"
# 話者ラベルの表示名を直接指定する場合(通常は不要。下の自動判定が優先されない)
# 例: SPEAKER_NAMES = {"SPEAKER_00": "しまだ", "SPEAKER_01": "ゲスト"}
SPEAKER_NAMES = {}

# 2人対談で男女1名ずつの場合、声の高さ(基本周波数)で自動的に名前を割り当てる。
# pyannoteのラベル順はファイルごとに変わるため、ラベル直接指定より確実。
# 使わない場合は両方 None にする(話者1/話者2 表示になる)。
MALE_NAME = "はやまる"
FEMALE_NAME = "高田さん"

# ---- 相槌除外の設定 ----
# 下記パターン「だけ」で構成される短いセグメントを相槌とみなして除外する。
# 誤って本編を削らないよう、意味を持ちうる語は入れないこと。
AIZUCHI_WORDS = (
    "うん|うーん|ううん|うんうん|はい|はいはい|ええ|えー|えっ|あー|ああ|"
    "おー|おお|ほう|へえ|へー|ふーん|ふん|ん|んー|なるほど|なるほどなるほど|"
    "たしかに|確かに|そう|そうそう|そうですね|そうですよね|そうなんですね|"
    "そうなんだ|ですよね|よね|ね|まあ|うわー|おっけー|OK|オッケー"
)
AIZUCHI_PATTERN = re.compile(f"^({AIZUCHI_WORDS})+$")
AIZUCHI_MAX_DURATION = 2.0  # 秒。これより長い発話は相槌パターンでも残す


def is_aizuchi(text: str, duration: float) -> bool:
    if duration > AIZUCHI_MAX_DURATION:
        return False
    normalized = re.sub(r"[、。,,..!!??\s・…〜]", "", text)
    if not normalized:
        return True  # 記号だけのセグメントも除外
    return bool(AIZUCHI_PATTERN.match(normalized))


def load_hf_token() -> str | None:
    token = os.environ.get("HF_TOKEN", "").strip()
    if token.startswith("hf_"):
        return token
    if TOKEN_FILE.exists():
        token = TOKEN_FILE.read_text(encoding="utf-8").strip()
        if token.startswith("hf_") and "\n" not in token:
            return token
    return None


def run_diarization(audio, token: str):
    """pyannoteで話者分離を実行し、(開始秒, 終了秒, 話者ラベル) のリストを返す"""
    import warnings

    import torch

    # torchcodec未対応の警告を抑制(音声はメモリ上で直接渡すため不要)
    warnings.filterwarnings("ignore", category=UserWarning, module=r"pyannote\.audio\.core\.io")
    from pyannote.audio import Pipeline

    # torch 2.6以降のweights_only=Trueデフォルトで、pyannote公式チェックポイントの
    # 読み込みに必要なクラスを許可リストに追加(モデル提供元を信頼している前提)
    from pyannote.audio.core.task import Problem, Resolution, Specifications

    torch.serialization.add_safe_globals(
        [torch.torch_version.TorchVersion, Specifications, Problem, Resolution]
    )

    try:
        pipeline = Pipeline.from_pretrained(DIARIZATION_MODEL, token=token)
    except TypeError:
        # pyannote.audio 3.x は引数名が use_auth_token
        pipeline = Pipeline.from_pretrained(DIARIZATION_MODEL, use_auth_token=token)
    pipeline.to(torch.device("cuda"))

    waveform = torch.from_numpy(audio).unsqueeze(0)
    inputs = {"waveform": waveform, "sample_rate": 16000}
    if NUM_SPEAKERS is not None:
        result = pipeline(inputs, num_speakers=NUM_SPEAKERS)
    else:
        result = pipeline(inputs)

    # pyannote.audio 4.x はコンテナ型、3.x はAnnotationを直接返す
    annotation = getattr(result, "speaker_diarization", result)
    return [
        (turn.start, turn.end, label)
        for turn, _, label in annotation.itertracks(yield_label=True)
    ]


def estimate_pitch(audio, turns, label) -> float | None:
    """指定話者の区間から声の基本周波数(Hz)の中央値を推定する"""
    import torch
    import torchaudio

    wave = torch.from_numpy(audio)
    chunks = []
    total = 0
    for start, end, turn_label in turns:
        if turn_label != label:
            continue
        seg = wave[int(start * 16000):int(end * 16000)]
        if len(seg) >= 16000 // 2:  # 0.5秒未満の断片は精度が低いので除く
            chunks.append(seg)
            total += len(seg)
        if total >= 16000 * 60:  # 60秒分あれば十分
            break
    if not chunks:
        return None
    x = torch.cat(chunks).unsqueeze(0)
    f0 = torchaudio.functional.detect_pitch_frequency(
        x, 16000, freq_low=60, freq_high=400
    )
    f0 = f0[f0 > 0]
    if f0.numel() == 0:
        return None
    return float(f0.median())


def build_label_map(audio, turns) -> dict:
    """話者ラベル → 表示名の対応表を作る"""
    speakers = sorted({label for _, _, label in turns})
    if SPEAKER_NAMES:
        return {l: SPEAKER_NAMES.get(l, l) for l in speakers}

    # 男女2人の対談なら声の高さで自動判定
    if len(speakers) == 2 and MALE_NAME and FEMALE_NAME:
        pitches = {l: estimate_pitch(audio, turns, l) for l in speakers}
        if all(p is not None for p in pitches.values()):
            low, high = sorted(speakers, key=lambda l: pitches[l])
            print(
                f"声の高さで話者を判定: {low}={pitches[low]:.0f}Hz → {MALE_NAME}, "
                f"{high}={pitches[high]:.0f}Hz → {FEMALE_NAME}"
            )
            if abs(pitches[low] - pitches[high]) < 30:
                print("⚠ 2人の声の高さが近いため、判定が誤っている可能性があります。")
            return {low: MALE_NAME, high: FEMALE_NAME}
        print("⚠ ピッチ推定に失敗したため、話者1/話者2 表示にフォールバックします。")

    return {label: f"話者{i}" for i, label in enumerate(speakers, start=1)}


def assign_speaker(segment, turns) -> str | None:
    """Whisperのセグメントに、時間の重なりが最大の話者を割り当てる"""
    words = getattr(segment, "words", None) or []
    spans = [(w.start, w.end) for w in words] or [(segment.start, segment.end)]
    overlap_by_speaker: dict[str, float] = {}
    for start, end in spans:
        for t_start, t_end, label in turns:
            overlap = min(end, t_end) - max(start, t_start)
            if overlap > 0:
                overlap_by_speaker[label] = overlap_by_speaker.get(label, 0.0) + overlap
    if not overlap_by_speaker:
        return None
    return max(overlap_by_speaker, key=overlap_by_speaker.get)


def format_timestamp(seconds: float) -> str:
    ms = int((seconds - int(seconds)) * 1000)
    s = int(seconds)
    h, rem = divmod(s, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def main():
    if len(sys.argv) < 2:
        print("使い方: uv run python transcribe.py <ファイルパス> [言語コード(省略可 例: ja)]")
        sys.exit(1)

    input_path = Path(sys.argv[1])
    language = sys.argv[2] if len(sys.argv) > 2 else None  # Noneなら自動検出

    # 動画/音声を16kHzモノラルにデコード(PyAV使用なので.movもそのまま扱える)
    print(f"音声をデコード中: {input_path}")
    audio = decode_audio(str(input_path), sampling_rate=16000)

    # ---- 話者分離 ----
    turns = []
    token = load_hf_token()
    if token:
        print(f"話者分離を実行中... (モデル: {DIARIZATION_MODEL})")
        turns = run_diarization(audio, token)
        speakers = sorted({label for _, _, label in turns})
        print(f"検出された話者: {len(speakers)}人 ({', '.join(speakers)})")
    else:
        print("hf_token.txt にトークンが無いため話者分離をスキップします。")

    label_map = build_label_map(audio, turns) if turns else {}

    # ---- 文字起こし ----
    # ★ Blackwell(RTX 50/RTX PRO 6000)ではint8がCUBLAS_STATUS_NOT_SUPPORTEDで
    #   クラッシュする既知の不具合があるため、必ず float16 を使用する
    print(f"モデル {MODEL_SIZE} を読み込み中... (初回はダウンロードに数分かかります)")
    model = WhisperModel(MODEL_SIZE, device="cuda", compute_type="float16")

    print("文字起こし開始")
    segments, info = model.transcribe(
        audio,
        language=language,
        beam_size=5,
        vad_filter=True,       # 無音区間を自動でスキップ
        word_timestamps=True,  # 話者割り当てと字幕同期の精度向上に必要
    )
    print(f"検出言語: {info.language} (確度 {info.language_probability:.2f})")

    srt_path = input_path.with_suffix(".srt")
    txt_path = input_path.with_suffix(".txt")
    aizuchi_count = 0
    index = 0

    with open(srt_path, "w", encoding="utf-8") as srt_f, \
         open(txt_path, "w", encoding="utf-8") as txt_f:

        for seg in segments:
            text = seg.text.strip()
            if is_aizuchi(text, seg.end - seg.start):
                aizuchi_count += 1
                continue

            speaker = assign_speaker(seg, turns) if turns else None
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
