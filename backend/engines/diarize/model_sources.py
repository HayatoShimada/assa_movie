"""話者分離モデルの取得元と置き場所。**ここが唯一の定義**。

同じURLが4箇所(取得スクリプトのsh/ps1、dev.sh、setup_job.py)に重複していて、
片方だけ直しても気付けない状態だった。標準ライブラリだけに依存させ、
バックエンドからも取得スクリプトからも同じものを見る。

ライセンス: segmentation=MIT (c) 2022 CNRS / embedding=Apache-2.0 (3D-Speaker)
詳細は licenses/diarization-NOTICE.md
"""

SEGMENTATION_URL = (
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-segmentation-models/"
    "sherpa-onnx-pyannote-segmentation-3-0.tar.bz2"
)
EMBEDDING_URL = (
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models/"
    "3dspeaker_speech_eres2netv2_sv_zh-cn_16k-common.onnx"
)

# 置き場所(モデルのルートからの相対)。同梱先と利用者のキャッシュで共通
SEGMENTATION_REL = "models/sherpa-onnx-pyannote-segmentation-3-0/model.onnx"
EMBEDDING_REL = "models/speaker-embedding.onnx"

# 取得の進捗表示に使う目安(実サイズ)
SEGMENTATION_SIZE_MB = 8
EMBEDDING_SIZE_MB = 68
TOTAL_SIZE_MB = SEGMENTATION_SIZE_MB + EMBEDDING_SIZE_MB
# 分離モデルの取得が全体の何割か(残りが埋め込みモデル)
SEGMENTATION_SHARE = SEGMENTATION_SIZE_MB / TOTAL_SIZE_MB
