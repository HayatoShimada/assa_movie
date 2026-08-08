"""配布版バックエンドの入口(Tauriシェルが子プロセスとして起動する)。

`uvicorn backend.app:app --port N` と同じことを、1ファイルに固めた実行ファイルで行う。
Tauri側は `--port` だけを渡す(frontend/src-tauri/src/backend.rs)。
"""

import argparse
import sys
from pathlib import Path

# PyInstallerで固めたときも backend パッケージを解決できるようにする
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main() -> int:
    parser = argparse.ArgumentParser(description="KirinukiStudio バックエンド")
    # 待ち受けはループバックのみ。ローカルアプリなので外部には開かない
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    # uvicornより先に付け替える。uvicorn自身のログも同じ標準出力に流れるため
    from backend.core.console import force_utf8_stdio

    force_utf8_stdio()

    import uvicorn

    from backend.app import app

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
