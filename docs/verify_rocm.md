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

## 実測値(RX 7900 XTX / ROCm 7.2 / torch 2.8+rocm6.4, 2026-08-07)

- ASR(transformers Whisper large-v3): モデルロード 7〜15秒、転写 実時間比 約4.4倍
  (75分動画 ≈ 17分)。60秒スライス逐次処理でVRAMピーク一定
- 話者分離(pyannote): GPU実行でCPU比 約2.8倍(MIOpen迂回)
- 書き出し: h264_vaapi ハードウェアエンコード動作確認済み

## 既知の制限(ROCm)

- faster-whisper(CTranslate2)はROCm非対応 → transformersエンジンを使用
- transformersエンジンは initial_prompt(フィラー忠実転写の文体例)非対応
- 通常メモリ→GPU転送が約0.2GB/sと極端に遅い環境がある(IOMMU起因の可能性)。
  アプリはpinnedメモリ経由でロードするため影響を回避済みだが、システム全体を
  改善したい場合はGRUBのカーネルオプションに `iommu=pt` を追加して再起動
  (`/etc/default/grub` の GRUB_CMDLINE_LINUX_DEFAULT → `sudo update-grub`)
- ROCm 6.2 SDK等の追加インストールは不要(torch wheelがランタイム同梱。
  システムROCm 7.2と混ぜるとaptの依存が壊れるため入れないこと)
