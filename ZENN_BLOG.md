---
title: "Radeon RX 7900 XTX + ROCm で対談動画の文字起こし〜切り抜きアプリを作った(ハマりどころ全部書く)"
emoji: "🎬"
type: "tech"
topics: ["rocm", "whisper", "amd", "pytorch", "fastapi"]
published: false
---

こんにちは。対談動画から文字起こしと切り抜きを作るローカルアプリを個人開発しています。

もともと NVIDIA の RTX PRO 6000 で動かしていたのですが、開発機を **Radeon RX 7900 XTX(ROCm 7.2)** に載せ替えたところ、動くと思っていたものが軒並み動かなくなりました。

「ROCm でも PyTorch は動くんでしょ?」——動きます。動くのですが、**その周辺にある CUDA 前提の資産が静かに壊れます**。しかもエラーメッセージが原因を指してくれないものが多く、実測しないと分からないものばかりでした。

この記事は、その移行で踏んだ地雷と、実測値をひととおり残しておくものです。同じ構成の人の時間が節約できたら嬉しいです。

## 作っているもの

対談・イベント動画を放り込むと、こういう流れで切り抜き動画まで作れるアプリです。

- **文字起こし**(Whisper large-v3、単語タイムスタンプ付き)
- **話者分離**(pyannote.audio + 声の高さで「男性/女性」を自動割り当て)
- **相槌・フィラー除去**(「うん」「あのー」を字幕からだけ消す。原文は保持)
- **指示語の解決**(「それ」が何を指すかを LLM が補足し、`それ(先月のイベント)` の形で注釈)
- **切り抜き候補の提案**(LLM + 機械特徴で「盛り上がっている区間」を推薦)
- **縦横変換つき書き出し**(横動画を 9:16 に。中央クロップ / ぼかし背景 / 顔検出で上下分割)

構成はシンプルで、全部ローカルで完結します。

```
ブラウザ (React 19 + Vite)
        │  同一オリジン(Viteプロキシ)
        ▼
FastAPI ──── ジョブキュー(単一ワーカー・直列)
        │         │
        │         ├── ASR       : Whisper large-v3   (GPU)
        │         ├── 話者分離   : pyannote.audio     (GPU)
        │         ├── LLM       : Ollama / Gemini API
        │         └── 書き出し   : ffmpeg (VAAPI)
        ▼
     SQLite
```

GPU ジョブは VRAM を食い合うので、キューは**単一ワーカーで直列**にしています。Python 側は uv、フロントは Vite + Playwright、テストは backend 389 件 / frontend 41 件 / E2E 27 件です。

以下、ROCm 移行でハマった順に書いていきます。

## 1. faster-whisper は AMD GPU では動かない

いちばん最初に躓いたのがこれでした。faster-whisper は速くて実績もあるので当然使い続けるつもりだったのですが、AMD GPU では初期化の時点で落ちます。

```
RuntimeError: CUDA failed with error CUDA driver version is insufficient for CUDA runtime version
```

faster-whisper の中身は **CTranslate2** で、これは CUDA 専用ビルドです。ROCm 版は提供されていません。

```python
>>> import ctranslate2
>>> ctranslate2.get_cuda_device_count()
RuntimeError: CUDA driver version is insufficient ...
>>> ctranslate2.get_supported_compute_types("cpu")
{'float32', 'int8', 'int16', 'int8_float32'}   # CPUなら動く
```

つまり **「Whisper が使えない」のではなく「faster-whisper が使えない」** だけです。Whisper 本体は PyTorch で動くので、ROCm でも普通に GPU を使えます。

選択肢は3つありました。

| 実装 | AMD GPU | 単語タイムスタンプ | 備考 |
|---|---|---|---|
| faster-whisper | ✗(CUDA専用) | ○ | CPU なら動くが遅い |
| transformers の Whisper | ○ | △(後述) | 最初にこれを選んだ |
| openai-whisper(公式) | ○ | ○ | 最終的にこれ |

最初は transformers 版を選びました。すでに依存に入っていたからです。これが次の地雷を踏むことになります。

## 2. transformers の単語タイムスタンプが日本語で壊れる

transformers 版に切り替えて動くようになり、精度も問題なし。ところが出来上がったデータを検証したら、**1単語が平均34文字、最大1431文字**になっていました。単語タイムスタンプが単語になっていない。

原因は transformers 側の言語判定にありました。

```python
# transformers/models/whisper/tokenization_whisper.py
def _combine_tokens_into_words(tokenizer, tokens, language=None, ...):
    if language is None:
        language = tokenizer.language
    if language is None:
        language = "english"

    if language in {"chinese", "japanese", "thai", "lao", "myanmar", "cantonese"}:
        # 空白で区切らない言語 → 文字単位で分割
        words, ... = _split_tokens_on_unicode(tokenizer, tokens)
    else:
        words, ... = _split_tokens_on_spaces(tokenizer, tokens)
```

判定が **言語の「フルネーム」** なんですね。こちらは ISO コードの `"ja"` を渡していたので、この `if` に入らず**空白分割**にフォールバックしていました。日本語には空白がないので、発話全体がまるごと1単語になる、というわけです。

トークナイザだけで再現できます(モデルのロードは不要)。

```python
from transformers import WhisperTokenizer
from transformers.models.whisper.tokenization_whisper import _combine_tokens_into_words

tok = WhisperTokenizer.from_pretrained("openai/whisper-large-v3")
ids = tok("はい大丈夫ですトーカフェっていつもテーマがあるじゃないですか",
          add_special_tokens=False).input_ids

for lang in (None, "ja", "japanese"):
    words, _, _ = _combine_tokens_into_words(tok, ids, lang)
    print(lang, len(words))
```

```
None       1     # 文まるごと1個
ja         1     # ← これを渡していた
japanese  18     # 正しい
```

`generate_kwargs={"language": "ja"}` は**推論には効く**(ちゃんと日本語で書き起こされる)ので、余計に気づきにくいです。効かないのは後処理の単語分割だけ。

修正は「フルネームを渡す」だけです。

```python
from transformers.models.whisper.tokenization_whisper import LANGUAGES

# LANGUAGES = {"ja": "japanese", "en": "english", ...}
pipe.tokenizer.language = LANGUAGES.get(language.lower(), language.lower())
```

### 地味に痛かった二次被害

このアプリはフィラー(言い淀み)判定に**単語の長さと直後の間**を使っています。

```python
if self.duration is not None and self.duration >= FILLER_MIN_DURATION:
    filler_score += 1
if self.gap_after is not None and self.gap_after >= FILLER_MIN_GAP:
    filler_score += 1
```

1単語 = 発話全体だと、`duration` は常に長く `gap_after` も発話終わりの間になるので、**全部フィラー判定に寄る**。単語タイムスタンプが壊れると、その上に載っている判定ロジックが静かに誤作動するという学びでした。

## 3. 結局 openai-whisper(公式)に落ち着いた

transformers 版のバグを直せば単語分割は正常化します。ただし transformers 版では**どうやっても取れないもの**が2つ残りました。

- **単語確率**(`probability`)……フィラー判定のシグナルの1つ
- **initial_prompt**……「えーと、あのー」を含む文体例を与えて言い淀みを忠実に転写させる機能

そこで **openai-whisper(公式実装)** を試したところ、これが素直に全部揃っていました。同じ音源で実測した比較がこちらです(RX 7900 XTX / large-v3)。

| | **openai-whisper** | transformers |
|---|---|---|
| 転写速度 | 実時間比 3.9〜4.4倍 | 4.9倍 |
| モデルロード | 6〜16秒 | 8秒 |
| 単語の粒度 | 1.7文字 | 1.5文字 |
| **単語確率** | **全単語で取得** | **取得できない** |
| **句読点** | **あり** | **なし** |
| initial_prompt | 対応 | 非対応 |

速度は transformers がわずかに速いのですが、**句読点が出ない**のが致命的でした。実際の出力を並べるとよく分かります。

```
# transformers
違うわけですっていう話してると衝突することもあるわけです

# openai-whisper
っていう話してると、衝突することもあるわけですよ。
```

字幕は文末で区切りたいので、句読点が無いと分割ルールがまったく効きません。10〜20% の速度差より機能の完全性を取って、ROCm では公式実装を既定にしました。

75分の実データで前後比較すると差は歴然でした。

| | 修正前(transformers) | 修正後(公式) |
|---|---|---|
| 単語数 | 640 | **14,445** |
| 単語の粒度 | 平均34.2文字 / 最大1431文字 | **平均1.6文字 / 最大11文字** |
| 単語確率 | なし | **全4,759語**(平均0.874) |
| 句読点を含む行 | 61/490 | **633/1600** |

なお `whisper.load_model()` した後に `model.half()` してはいけません。whisper の `LayerNorm` は入力を `float()` に上げてから重みと突き合わせるので、重みを half にすると型不一致で落ちます。

```python
# whisper/model.py
class LayerNorm(nn.LayerNorm):
    def forward(self, x):
        return super().forward(x.float()).type(x.dtype)
```

```
RuntimeError: expected scalar type Float but found Half
```

fp16 は `transcribe(fp16=True)` 側で面倒を見てくれるので、重みは float32 のままにしておきます。

## 4. モデルのロードに9分かかる(IOMMU の罠)

これが今回いちばん原因が分からなかった問題です。**GPU へのモデル転送が異常に遅い。** 3GB のモデルをロードするのに9分近くかかりました。

まず PCIe を疑いましたが、リンクは正常でした。

```bash
$ cat /sys/class/drm/card1/device/current_link_speed
16.0 GT/s PCIe
$ cat /sys/class/drm/card1/device/current_link_width
16
```

Gen4 x16。問題ないはずです。転送そのものを測ってみます。

```python
x = torch.randn(512, 1024, 1024, dtype=torch.float16)   # 1GB
t0 = time.time(); y = x.to("cuda"); torch.cuda.synchronize()
print(f"{1/(time.time()-t0):.1f} GB/s")
```

```
0.2 GB/s     # ← 遅すぎる
```

念のため pinned memory(page-locked)経由でも測ってみたら、これが決定打でした。

```python
xp = x.pin_memory()
t0 = time.time(); y = xp.to("cuda"); torch.cuda.synchronize()
```

```
0.18秒 → 5.6 GB/s     # 約28倍
```

**通常メモリからの転送だけが極端に遅い。** IOMMU 構成が絡んでいる可能性が高そうです(`HSA_ENABLE_SDMA=0` は効きませんでした)。

モデルは「重みテンソルを1000個ほど順番に GPU へ送る」という処理なので、1回あたりのオーバーヘッドがそのまま効いてきます。というわけで、**ロード時だけ pinned memory を経由**するようにしました。

```python
model = whisper.load_model(self.model_size, device="cpu")
for p in model.parameters():
    p.data = p.data.pin_memory()
for b in model.buffers():
    b.data = b.data.pin_memory()
self._model = model.to(self.device)
```

これで **9分 → 7秒**。ROCm 特有の事情なので、`detect_accel() == "rocm"` のときだけ有効にしています(CUDA では pinned 化のコストが無駄になるため)。

システム全体を直すなら GRUB に `iommu=pt` を足して再起動、というのが本筋だと思います。

## 5. 話者分離が GPU で動かない(MIOpen)

pyannote.audio を GPU に載せたら、モデルの一部でカーネルのビルドに失敗しました。

```
/tmp/comgr-xxxxx/include/miopen_rocrand.hpp:45:10: fatal error:
      'rocrand/rocrand_xorwow.h' file not found
MIOpen Error: ... Code object build failed. Source: MIOpenDropoutHIP.cpp
```

torch の rocm wheel に同梱されている MIOpen が、**Dropout カーネルを実行時コンパイルするときに rocRAND のヘッダを見つけられない**、というものです。`sudo apt install rocrand-dev` でヘッダを入れても解決しませんでした。

pyannote が使うのは LSTM で、cuDNN(ROCm では MIOpen)API 経由だとこの Dropout カーネルを踏みます。そこで **cuDNN API を切って、通常の HIP カーネルで LSTM を回す**ようにしました。

```python
if getattr(torch.version, "hip", None):
    torch.backends.cudnn.enabled = False
```

結果は次のとおりで、精度は変わらず(turns 数も一致)速くなりました。

| | 実行時間(音声120秒) |
|---|---|
| CPU フォールバック | 46.9秒 |
| **GPU(MIOpen 迂回)** | **16.6秒** |

念のため、GPU で `RuntimeError` が出たら CPU で1回だけ再試行するフォールバックも入れてあります。

## 6. OpenCV 5 で顔検出が消えていた

縦型レイアウトで「1人なら顔中心にクロップ、2人なら上下分割」をやるために OpenCV の Haar カスケードを使っています。これが実行時に落ちました。

```
AttributeError: module 'cv2' has no attribute 'CascadeClassifier'
```

`opencv-python-headless>=4.10` と書いていたら **5.0.0 が入っていた**のが原因です。OpenCV 5 では `CascadeClassifier` も同梱の Haar XML も削除されていました(`cv2/data/` が空)。代替の `FaceDetectorYN` は ONNX モデルを別途置く必要があります。

```toml
# OpenCV 5はCascadeClassifierと同梱Haarカスケードxmlが削除されているため4系固定
"opencv-python-headless>=4.10,<5",
```

**単体テストをすり抜けた**のも反省点でした。純関数(顔ボックス → クロップ位置の決定)だけをテストしていて、検出器そのものを1度も実行していなかったからです。こういう I/O 境界こそスモークテストを置くべきでした。

```python
def test_detect_faces_smoke():
    """検出器が実際にロード・実行できること"""
    assert detect_faces(np.zeros((480, 640, 3), dtype=np.uint8)) == []
```

## 7. OpenCV と torch(ROCm)を同時に読むとプロセスごと落ちる

これも謎めいたやつでした。単体では動くのに、torch を先に import すると死にます。

```bash
$ python -c "import cv2; ..."                # OK
$ python -c "import torch, cv2; ..."         # 落ちる
python3: symbol lookup error: /opt/rocm-7.2.0/lib/libamdocl64.so:
  undefined symbol: hsa_amd_memory_get_preferred_copy_engine, version ROCR_1
```

torch(rocm wheel が同梱するランタイム)が先にロードされた状態で、OpenCV がシステム側 ROCm の OpenCL を遅延ロードしにいってシンボル不整合を起こす、という組み合わせ事故でした。例外ではなく**プロセスごと落ちる**のでテストが原因不明で中断します。

顔検出に OpenCL は要らないので、無効化して回避しています。

```python
# cv2 の import より前に設定する必要がある
os.environ.setdefault("OPENCV_OPENCL_RUNTIME", "disabled")
```

## 8. サーバーの起動が5秒遅い(GIL の話)

起動時に「GPU は何か・VRAM はいくつか・エンコーダは何が使えるか」をスキャンして表示する、という親切機能を入れたら、開発が地味に苦しくなりました。`uvicorn --reload` を使っているので、**ファイルを保存するたびに5秒間サーバーが応答しません**。

計測するとこうでした。

| 処理 | 時間 |
|---|---|
| `torch.cuda.is_available()` | **5.04秒** |
| `import torch` | 0.57秒 |
| `ffmpeg -encoders` | 0.03秒 |
| Ollama へのプローブ | 0.001秒 |

**ROCm の GPU 初期化が5秒**。ffmpeg や Ollama は誤差でした。

「じゃあバックグラウンドスレッドに逃がせばいい」と思ったのですが、**まったく速くなりませんでした**。torch の HIP 初期化は C 側で GIL を握り続けるので、別スレッドにしても本体が止まります。

最終的に **子プロセスで調べる**ようにしました。プロセスが別なら GIL は無関係です。

```python
@lru_cache(maxsize=1)
def probe_gpu() -> dict:
    code = (
        "import json,torch\n"
        "d={'accel':'cpu','name':'','vram_total_mb':0,'vram_free_mb':0}\n"
        "if torch.cuda.is_available():\n"
        "    d['accel']='rocm' if getattr(torch.version,'hip',None) else 'cuda'\n"
        "    free,total=torch.cuda.mem_get_info()\n"
        "    d.update(name=torch.cuda.get_device_name(0), ...)\n"
        "print(json.dumps(d))"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120)
    return json.loads(out.stdout.strip().splitlines()[-1])
```

起動直後にバックグラウンドスレッドから叩いて暖めておけば、設定画面を開いた時にはもう結果があります(子プロセスなので暖機中もサーバーは応答します)。

**起動 5.72秒 → 0.07秒。** リロード地獄から解放されました。

## 9. 書き出しは VAAPI で動く

NVENC が使えないので、ffmpeg のエンコーダも切り替えが必要です。ここは素直で、`h264_vaapi` がそのまま動きました。

```bash
sudo apt install ffmpeg mesa-va-drivers vainfo
```

```
$ vainfo | grep -i h264
VAProfileH264Main : VAEntrypointEncSlice   # エンコード対応OK
```

エンコーダは自動検出にしています。ffmpeg は NVIDIA 機でなくても `h264_nvenc` を「対応コーデック」として列挙してくるので、**実デバイスの有無まで見る**のがポイントでした。

```python
def _pick_encoder(encoders_output: str, has_nvidia: bool, has_dri: bool) -> str:
    if "h264_nvenc" in encoders_output and has_nvidia:
        return "h264_nvenc"
    if "h264_vaapi" in encoders_output and has_dri:
        return "h264_vaapi"
    return "libx264"
```

VAAPI ではフィルタ列の**最後**に `format=nv12,hwupload` を足して、`-vaapi_device` を入力より前に置く必要があります。字幕焼き込みや縦横変換のフィルタと組み合わせる場合、この順序を間違えると動きません。

```bash
ffmpeg -vaapi_device /dev/dri/renderD128 -ss 0 -i in.mov -t 5 \
  -filter_complex "[0:v]crop=1654:2940:129:0,scale=1080:1920[vlay];[vlay]format=nv12,hwupload[vhw]" \
  -map "[vhw]" -map 0:a -c:v h264_vaapi -qp 23 -c:a aac out.mp4
```

## つまずいた点まとめ

散らばったので表にしておきます。

| 症状 | 原因 | 対処 |
|---|---|---|
| faster-whisper が初期化で落ちる | CTranslate2 が CUDA 専用ビルド | PyTorch 実装の Whisper に変更 |
| 単語タイムスタンプが1単語34文字 | 言語判定がフルネーム比較(`"ja"` ✗) | `"japanese"` を渡す |
| モデルロードに9分 | 通常メモリ→GPU 転送が 0.2GB/s | pinned memory 経由(→7秒) |
| 話者分離が GPU で落ちる | MIOpen の Dropout カーネルがビルド不能 | `cudnn.enabled = False`(→2.8倍速) |
| `cv2.CascadeClassifier` が無い | OpenCV 5 で削除 | 4系に固定 |
| プロセスごと落ちる | torch(ROCm)と cv2 の OpenCL 衝突 | `OPENCV_OPENCL_RUNTIME=disabled` |
| 起動が5秒遅い | torch の GPU 初期化が GIL を握る | 子プロセスで調べる(→0.07秒) |
| `rocm-smi` が assert で落ちる | ROCm 6.2 のツールに 7.2 のドライバ | apt リポジトリを 7.2 に統一 |

ROCm 環境で個人的にいちばん効いた教訓は、**「動いた」と「正しく動いた」の間にかなり距離がある**ということでした。ASR は最初から「動いて」いましたが、出力データを検証するまで単語タイムスタンプが壊れていることには気づけませんでした。エラーが出ないぶん質が悪いです。

もうひとつは、**推測せずに測る**こと。「PCIe が遅いのでは」「バックグラウンドスレッドにすれば解決するのでは」はどちらも外れで、1行測ったら答えが出ました。ROCm はまだ情報が少ないので、手元で測るのがいちばん速い、というのが結論です。

## 最終的な実測値

RX 7900 XTX(VRAM 24GB) / ROCm 7.2 / torch 2.8.0+rocm6.4 での数字です。

| 処理 | 実測 |
|---|---|
| 文字起こし(large-v3) | 実時間比 **4.4倍**(75分動画 ≈ 17分) |
| モデルロード | 7秒(pinned 経由) |
| 話者分離 | CPU 比 **2.8倍** |
| 書き出し | h264_vaapi(GPU エンコード) |
| サーバー起動 | 0.07秒 |

NVIDIA + faster-whisper なら文字起こしはもっと速いはずですが(large-v3 で実時間比 25倍程度)、**実用上は困らない**ところまでは来ました。75分の対談が17分で文字起こしできて、そのまま字幕付き切り抜きまで作れるなら十分です。

## まとめ

- 動かないのは **Whisper ではなく faster-whisper**(CTranslate2 が CUDA 専用)
- ROCm では **openai-whisper(公式実装)** が素直。単語確率も initial_prompt も揃う
- 日本語の単語タイムスタンプは **言語をフルネームで渡す**
- ROCm 特有の性能問題は **pinned memory** と **cudnn 無効化** で大きく改善する
- torch の GPU 初期化は **GIL を握る**ので、起動パスに置かない

ROCm は「動かない」より「動くけど何かがおかしい」の方が多い印象でした。逆に言うと、原因さえ分かればどれも回避できるものばかりです。同じ構成で詰まっている方の助けになれば幸いです。
