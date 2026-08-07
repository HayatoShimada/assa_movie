# ROCm環境の実機検証チェックリスト

対象: AMD Radeon RX 7900 XT/XTX(gfx1100)+ ROCm 7.2。
コード側の自動テスト(`uv run pytest -q`)はGPU不要で全て通る前提。
以下はGPU実機でしか確認できない項目。

## 1. システム準備(要sudo・初回のみ)

```bash
# ffmpeg(書き出し・ffprobeに必須)と VAAPI ドライバ(AMDのHWエンコード)
sudo apt install ffmpeg mesa-va-drivers vainfo

# ユーザーがGPUデバイスにアクセスできること(未所属なら追加して再ログイン)
groups | grep -E "render|video" || sudo usermod -aG render,video $USER
```

## 2. Python環境

```bash
./dev.sh sync   # = uv sync(既定でrocmグループ。NVIDIA機は WL_TORCH_GROUP=cu128)
uv run python -c "import torch; print(torch.__version__, torch.version.hip, torch.cuda.is_available(), torch.cuda.get_device_name(0) if torch.cuda.is_available() else '-')"
# 期待: 2.8.0+rocm6.4 / 6.4.x / True / Radeon RX 7900 系
```

## 3. 自動テスト

```bash
uv run pytest -q          # GPU不要テスト全通過
uv run pytest -q --run-gpu  # golden検証(ASRがGPUで動くこと)
```

## 4. アプリでの確認

1. `./dev.sh` で起動(起動ログに「torchがGPUを認識していません」警告が**出ない**こと)
2. 雑談編.mov を文字起こし → transformersエンジンで完走すること
   (設定タブのASRエンジンが「自動」のとき、ROCmでは transformers Whisper が選ばれる)
3. 実行中に `watch -n1 rocm-smi` でVRAM使用が増えること
4. 話者分離(pyannote)がGPUで完走すること。
   MIOpen初回コンパイルで数分かかる場合がある。失敗時はCPUに自動フォールバックし
   「⚠ GPUでの話者分離に失敗したため、CPUで再試行します。」がログに出る
5. `vainfo | grep -i h264` でエンコードentrypointがあること
6. クリップ書き出しが h264_vaapi で完走し、出力mp4が再生できること
   (vaapi不可の環境では自動で libx264 に落ちる)

## 既知の制限(ROCm)

- faster-whisper(CTranslate2)はROCm非対応 → transformersエンジンを使用
- transformersエンジンは initial_prompt(フィラー忠実転写の文体例)非対応
- transformersエンジンの進捗表示は粗い(開始→完了のみ)
