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
./dev.sh sync   # = uv sync(既定でrocmグループ。NVIDIA機は KS_TORCH_GROUP=cu128)
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

### whisper.cpp(hipBLAS)の検証結果

同じ音源・同じ large-v3 で比較した(2026-08-08)。
**`--output-json-full`(`-ojf`)を使えば、必要な情報が全て同時に取れる。**

| 条件 | 速度(実時間比) | 句読点 | 単語TS | 単語確率 |
|---|---|---|---|---|
| 既定(greedy) | 18.5倍 | なし | なし | なし |
| `-bs 5 -ml 1`(トークン分割) | 14.9倍 | **なし** | あり | なし |
| **`-bs 5 -ojf --prompt`** | **11.6倍** | **あり(151個)** | **あり** | **あり** |
| (参考)openai-whisper | 4.4倍 | あり | あり | あり |

`-ojf` は `token_timestamps` を有効化し、セグメントごとに全トークンを
`{text, offsets, p}` で返す。セグメント分割は粗い(20秒超もある)が、
トークンのタイムスタンプがあるので `words_to_segments`(ポーズ・句読点・
最大長で切る既存の純関数)でこちら側で分割すればよい。

- **速度は openai-whisper の約2.6倍**(75分の動画なら約17分→約6.5分)
- トークン粒度1.5文字・確率平均0.888(公式版は1.7文字・0.874)とほぼ同等
- 注意: 10%ほど長さ0のトークン(`from == to`)が混ざるので取り込み側で潰す
- `-ml 1` を付けると句読点が落ちるので**付けない**(分割は自前で行う)

**採用済み。** `./dev.sh whispercpp` でビルドとモデル取得を行うと、
ROCmのエンジン自動選択がこれを使う。用意していない環境では公式Whisperに
落ちるので、他マシンへ持っていっても壊れない。

置き場所は `~/.cache/kirinuki-studio`(`KS_WHISPERCPP_HOME` で変更可。
旧名 `~/.cache/whisper-local` が残っている環境はそちらを使い続ける)。
CLIは音声をファイルで受け取るため、ジョブ側で一時WAVを書き出している。

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

## whisper.cpp: Vulkan と HIP の比較(2026-08-08 実測)

Windows対応の下調べ。**Vulkanで実用速度が出るなら、ベンダーを問わない
1つのビルドで済む**ので、まずそれを確かめた(V1_PLAN M28 の `[要検証]`)。

同一機(RX 7900 XTX / RADV)・同一モデル(ggml-large-v3)・同一音源で計測。
300秒音源を3回ずつ回し、ばらつきは0.1秒以内だった。

| | 実時間比 | 300秒音源の所要 | ROCm依存 | 配布サイズ(共有ライブラリ) |
|---|---|---|---|---|
| HIP (`GGML_HIP=ON`) | **18.6倍** | 16.1秒 | **あり**(hipblas / rocblas / amdhip64 / rocsolver) | 215MB + ROCm本体 |
| Vulkan (`GGML_VULKAN=ON`) | 16.2倍 | 18.5秒 | **なし**(`libvulkan.so.1` のみ) | **976KB** |

**速度差は13%しかなく、配布のしやすさは桁違いに違う。**
Vulkan版は `ldd` でROCmのライブラリを一切引かない。GPUドライバに付いてくる
Vulkanローダーだけで動くので、ユーザーにROCm/HIP SDKの導入を求めずに済む。

### 書き起こしの中身

全文の文字単位一致率は**74.1%**(Vulkan 1615文字 / HIP 1409文字)。
バックエンドが変わると浮動小数点の結果が僅かに変わり、デコードの経路が
分岐するため完全一致はしない。差分の多くは相槌・フィラー
(「そうそうそう」「まあ」)で、**Vulkan版の方が多く拾っている**。
このアプリはフィラーを検出して扱う設計なので不利ではない。

語の取り違え(「余ってる」↔「待ってる」など)も双方にあり、
正解データが無いためどちらが優れているかは判定していない。

### ビルド手順(Vulkan)

ROCmは不要。HIP版と別ディレクトリに作れば共存できる。

```bash
sudo apt install libvulkan-dev glslc glslang-tools spirv-headers vulkan-tools
vulkaninfo --summary | grep deviceName   # GPUが見えるか確認
cd whisper.cpp
cmake -S . -B build-vulkan -DGGML_VULKAN=ON -DCMAKE_BUILD_TYPE=Release
cmake --build build-vulkan -j "$(nproc)"
```

### この結果の意味

1. **Windows対応はVulkan 1本で足りる見込み。** AMD/NVIDIA/Intelを1ビルドで賄え、
   HIP SDK for Windows は不要になる
2. **whisper.cppをアプリに同梱できる。** 976KBならM28で「ビルドが要るので
   アプリからは入れられない」とした制限が消える(現状のggmlモデル3.1GBの
   ダウンロードは別途必要)
3. Linuxで最速を求めるならHIP版が13%速い。既存の `./dev.sh whispercpp` は
   HIP版のままでよい

**未検証**: NVIDIA/Intel GPUでのVulkan動作(この機にはAMDしかない)、
Windows上での速度。

## llama.cpp: Vulkan と HIP の比較(2026-08-08 実測)

whisper.cppに続き、LLM側もVulkanで足りるかを確認した。
同一機(RX 7900 XTX / RADV)・qwen2.5-coder:32b(Q4_K_M / 18.48GiB)・
`llama-bench` で計測。llama.cpp 69bf643。

### 素の性能

| | プロンプト処理 | 生成 |
|---|---|---|
| HIP | **823.4 t/s** | 32.8 t/s |
| Vulkan | 573.7 t/s | **38.2 t/s** |

**whisper.cppと違い、勝敗が割れる。** HIPはプロンプト処理が44%速く、
Vulkanは生成が16%速い。どちらが有利かは**プロンプトと生成の比率**で決まる。

損益分岐は **プロンプトが生成の8.2倍**。これを超えるとHIPが有利になる。

### このアプリの実ワークロード

実データ(メディア4の45セグメント)で指示語解決のプロンプトを組み立てて計測:

- プロンプト **1494トークン**(システム1182文字 + 本文1085文字)
- 出力 **423トークン**(編集案12件)
- 比率は **3.5:1** で、損益分岐の8.2倍を大きく下回る

| | プロンプト | 生成 | 1回あたり |
|---|---|---|---|
| Vulkan | 2.60秒 | 11.08秒 | **13.69秒** |
| HIP | 1.81秒 | 12.91秒 | 14.73秒 |

**このアプリではVulkanの方が7.1%速い。** 生成が支配的なワークロードだから。
75分動画(約50回の呼び出し)で Vulkan 11.4分 / HIP 12.3分。

### この結果の意味

whisper.cppでは「HIPが13%速いが配布のしやすさでVulkan」だったが、
llama.cppでは**速度でもVulkanが勝つ**(このアプリの使い方に限れば)。

- LLM側もROCm非依存にできる。Windows対応がVulkan 1本で揃う
- Ollamaは `rocm` と `vulkan` の両ランナーを同梱しており、
  Vulkanを選ばせることも可能(要確認: Ollamaのランナー選択方法)
- プロンプトが極端に長い使い方(長文要約など)に広げるなら、
  損益分岐8.2倍を思い出して測り直すこと

**未検証**: NVIDIA/Intel GPUでのVulkan動作、Windows上での速度、
Ollama経由(直接llama.cppではなく)での差。
