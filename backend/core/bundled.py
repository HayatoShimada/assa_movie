"""配布物に同梱したもの(バイナリ・モデル・ライセンス)の置き場所。

同じ実装が ffmpeg.py / whispercpp.py / onnx.py に3つあった。テストやE2Eで
差し替えるとき1つしか差し替えず、残り2つは本物を見たままになる
(backend/e2e_server.py が実際にそうなっていた)。ここ1箇所にする。
"""

import os
import sys
from pathlib import Path


def bundled_dir() -> Path:
    """同梱物のルート。

    実際の場所はパッケージ形式で変わる(.debなら /usr/lib/KirinukiStudio、
    AppImageなら展開先、.appならBundle内)。自分で組み立てず、Tauriシェルが
    KS_RESOURCE_DIR で教えてくれた場所を使う(frontend/src-tauri/src/lib.rs)。
    開発中は実行ファイルの隣を見る。
    """
    resource_dir = os.environ.get("KS_RESOURCE_DIR", "").strip()
    return Path(resource_dir) if resource_dir else Path(sys.executable).parent
