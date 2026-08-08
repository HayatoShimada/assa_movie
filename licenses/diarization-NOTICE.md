# 話者分離モデルについて

KirinukiStudio には話者分離(だれが話しているかの判定)のためのモデルを2つ同梱しています。
どちらも ONNX 形式で、CPU だけで動きます。

| ファイル | 用途 | ライセンス |
|---|---|---|
| `models/sherpa-onnx-pyannote-segmentation-3-0/model.onnx` | 発話区間の検出 | MIT |
| `models/speaker-embedding.onnx` | 話者の声の特徴量 | Apache-2.0 |

## 発話区間の検出 (MIT)

pyannote の `segmentation-3.0` を ONNX に変換したものです。ライセンス本文は
同じフォルダの `LICENSE-segmentation.txt`(MIT License, Copyright (c) 2022 CNRS)。

- 元モデル: <https://huggingface.co/pyannote/segmentation-3.0>
- 変換・配布: <https://github.com/k2-fsa/sherpa-onnx/releases/tag/speaker-segmentation-models>

## 話者の特徴量 (Apache-2.0)

3D-Speaker の `eres2netv2` を ONNX に変換したものです。

- 元プロジェクト: <https://github.com/modelscope/3D-Speaker>(Apache License 2.0)
- 変換・配布: <https://github.com/k2-fsa/sherpa-onnx/releases/tag/speaker-recongition-models>

## 実行に使うライブラリ

モデルの実行には [sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx)(Apache-2.0)と
ONNX Runtime(MIT)を使います。これらはバックエンドの実行ファイルに取り込まれており、
表記は `licenses/python/THIRD-PARTY-NOTICES.txt` に含まれます。

## なぜ同梱しているか

配布物には PyTorch を入れていません(11.5GB あるため)。torch を使う pyannote は
インストール版では動かず、ONNX が唯一使えるエンジンです。モデルが無いと話者分離が
まったく使えなくなるため、77MB を同梱しています。
