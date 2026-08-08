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

## 実測値(RX 7900 XTX / ROCm 7.2 / torch 2.8+rocm6.4, 2026-08-08)

### ASRエンジンの比較(同一音源・large-v3)

| | **openai-whisper(既定)** | transformers |
|---|---|---|
| 転写速度 | 実時間比 3.9〜4.4倍 | 4.9倍 |
| モデルロード | 6〜16秒 | 8秒 |
| 単語の粒度 | 1.7文字 | 1.5文字 |
| **単語確率** | **全単語で取得** | **取得できない** |
| **句読点** | **あり**(「〜わけですよ。」) | **なし** |
| initial_prompt | 対応 | 非対応 |

speed は transformers がわずかに速いが、**句読点が出ないため字幕の文末分割が
効かず**、単語確率も無いためフィラー自動判定のシグナルが1つ欠ける。
機能が揃う openai-whisper を ROCm の既定にしている。

### whisper.cpp(hipBLAS)の検証結果 ※採用は保留

同じ音源・同じ large-v3 で比較した(2026-08-08)。**速度は明確に速いが、
このアプリが必要とする情報をCLIから同時に取り出せない**ため採用を見送っている。

| 条件 | 速度(実時間比) | 句読点 | 単語TS | 単語確率 |
|---|---|---|---|---|
| 既定(greedy) | 18.5倍 | **なし** | なし | なし |
| `-bs 5 --prompt`(公式版と同条件) | **11.6倍** | **あり(41/41)** | なし | なし |
| `-bs 5 -dtw large.v3 -ml 1` | 14.9倍 | **なし** | あり(1.5文字) | JSONに出ない |
| (参考)openai-whisper | 4.4倍 | あり | あり | **あり** |

- **速度は openai-whisper の約2.6倍**(75分の動画なら約17分→約6.5分)
- しかし単語タイムスタンプを得る `-ml 1` を付けると**句読点が消える**。
  字幕の文末分割に句読点が要るので、CLI経由では両立できない
- `--print-confidence` は端末出力の着色のみで、JSONに確率は含まれない
  (フィラー判定は単語確率をシグナルに使う)
- 両立させるにはC API(pywhispercpp等)で組み込む必要があり、
  外部バイナリとggml版モデル(2.9GB)の管理も増える

ビルド手順(再現用):

```bash
sudo apt install cmake
# ROCm 6.2時代の rocprofiler-register が残っているとリンクに失敗する
#   undefined reference to `rocprofiler_register_error_string'
sudo apt install rocprofiler-register   # 7.2系に更新する
git clone --depth 1 https://github.com/ggml-org/whisper.cpp && cd whisper.cpp
HIPCXX="$(hipconfig -l)/clang" HIP_PATH="$(hipconfig -R)" \
  cmake -S . -B build -DGGML_HIP=ON -DAMDGPU_TARGETS=gfx1100 -DCMAKE_BUILD_TYPE=Release
cmake --build build -j 20
```

### その他

- 話者分離(pyannote): GPU実行でCPU比 約2.8倍(MIOpen迂回)
- 書き出し: h264_vaapi ハードウェアエンコード動作確認済み

## 既知の制限(ROCm)

- faster-whisper(CTranslate2)は**CUDA専用ビルド**でAMD GPUでは初期化に失敗する
  (`CUDA driver version is insufficient`)。PyTorch実装のWhisperに切り替えて回避
- transformersエンジンを明示選択した場合は initial_prompt と単語確率が使えない
- 通常メモリ→GPU転送が約0.2GB/sと極端に遅い環境がある(IOMMU起因の可能性)。
  アプリはpinnedメモリ経由でロードするため影響を回避済みだが、システム全体を
  改善したい場合はGRUBのカーネルオプションに `iommu=pt` を追加して再起動
  (`/etc/default/grub` の GRUB_CMDLINE_LINUX_DEFAULT → `sudo update-grub`)
- ROCm 6.2 SDK等の追加インストールは不要(torch wheelがランタイム同梱。
  システムROCm 7.2と混ぜるとaptの依存が壊れるため入れないこと)
