#!/usr/bin/env python3
"""話者分離(ONNX)のモデルを取ってきて置く。3OS共通。

sh版とps1版に分かれていたものを1本にした。「中身は同じ」と称しつつ
`-Force` の有無・リトライの有無が既に食い違っており、CIのキャッシュキーも
片方しか見ていなかった(ps1だけ直してもWindowsは変更を無視した)。

なぜ同梱するか: 配布物には torch を入れていない(11.5GBあるため)。torchを使う
pyannoteはインストール版では動かず、ONNXが唯一使えるエンジンになる。モデルが
無いと設定タブで全エンジンが「未準備」になり、話者分離がまったく使えない。

  python scripts/fetch_diarization_models.py            # 配布物へ同梱する
  python scripts/fetch_diarization_models.py --home DIR # 利用者のキャッシュへ
  python scripts/fetch_diarization_models.py --force    # 取得し直す

標準ライブラリだけで動く(scripts/collect_python_licenses.py と同じ流儀)。
バックエンドの依存を入れる前でも、CIのどのOSでも走る。
"""

import argparse
import shutil
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from backend.core.console import force_utf8_stdio  # noqa: E402
from backend.engines.diarize.model_sources import (  # noqa: E402
    EMBEDDING_REL,
    EMBEDDING_SIZE_MB,
    EMBEDDING_URL,
    SEGMENTATION_REL,
    SEGMENTATION_URL,
)

BUNDLE_DIR = REPO_ROOT / "frontend/src-tauri/resources"
NOTICE_SRC = REPO_ROOT / "licenses/diarization-NOTICE.md"
APACHE_SRC = REPO_ROOT / "licenses/Apache-2.0.txt"
RETRIES = 3


def download(url: str, dest: Path) -> None:
    """URLをdestに保存する。GitHubのリリース配信は稀に落ちるのでリトライする"""
    dest.parent.mkdir(parents=True, exist_ok=True)
    last: Exception | None = None
    for attempt in range(1, RETRIES + 1):
        try:
            with urllib.request.urlopen(url, timeout=60) as resp, dest.open("wb") as f:
                shutil.copyfileobj(resp, f)
            return
        except Exception as e:  # URLError/HTTPError/socket.timeout などをまとめて
            last = e
            print(f"  取得に失敗({attempt}/{RETRIES}): {e}")
    raise SystemExit(f"取得できませんでした: {url}\n  {last}")


def find_one(root: Path, name: str) -> Path | None:
    for path in sorted(root.rglob(name)):
        return path
    return None


def fetch(dest_root: Path, license_dest: Path | None, force: bool) -> None:
    seg_out = dest_root / SEGMENTATION_REL
    emb_out = dest_root / EMBEDDING_REL
    if not force and seg_out.is_file() and emb_out.is_file():
        print(f"=== 既に置いてあります: {dest_root} ===")
        return

    # 完了してから所定の場所へ動かす。中途半端なファイルが残ると
    # is_available() が「使える」と誤判定する
    staging = Path(tempfile.mkdtemp(prefix="ks-diarize-"))
    try:
        print("=== 分離モデルを取得 ===")
        archive = staging / "segmentation.tar.bz2"
        download(SEGMENTATION_URL, archive)
        extracted = staging / "extract"
        with tarfile.open(archive) as tar:
            tar.extractall(extracted, filter="data")

        seg_src = find_one(extracted, "model.onnx")
        if seg_src is None:
            raise SystemExit("model.onnx が見つかりません")
        seg_out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(seg_src, seg_out)

        print(f"=== 埋め込みモデルを取得(約{EMBEDDING_SIZE_MB}MB) ===")
        emb_tmp = staging / "embedding.onnx"
        download(EMBEDDING_URL, emb_tmp)
        emb_out.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(emb_tmp), emb_out)

        if license_dest is not None:
            write_licenses(license_dest, extracted)
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    print("=== できました ===")
    for path in (seg_out, emb_out):
        print(f"  {path} ({path.stat().st_size / 1024 / 1024:.1f}MB)")


def write_licenses(dest: Path, extracted: Path) -> None:
    """再配布に必要な表記を揃える。

    MIT(分離モデル)は配布物に付いてくる本文をそのまま持っていく。
    Apache-2.0(埋め込みモデル)は本文が付いてこないのでリポジトリのものを使う
    (第4条が「ライセンスの写しを添えること」を求めている)。
    """
    dest.mkdir(parents=True, exist_ok=True)
    seg_license = find_one(extracted, "LICENSE")
    if seg_license is None:
        print("⚠ segmentation の LICENSE が見つかりません", file=sys.stderr)
    else:
        shutil.copy2(seg_license, dest / "LICENSE-segmentation.txt")
    shutil.copy2(APACHE_SRC, dest / "LICENSE-embedding-Apache-2.0.txt")
    shutil.copy2(NOTICE_SRC, dest / "NOTICE.md")
    print(f"ライセンス表記: {dest}")


def main() -> None:
    force_utf8_stdio()  # Windowsの既定(cp932/cp1252)だと「⚠」で落ちる
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--home",
        type=Path,
        help="利用者のモデルキャッシュへ置く(省略時は配布物へ同梱する)",
    )
    parser.add_argument("--force", action="store_true", help="取得済みでも取り直す")
    args = parser.parse_args()

    if args.home:
        fetch(args.home, license_dest=None, force=args.force)
    else:
        fetch(BUNDLE_DIR, BUNDLE_DIR / "licenses/diarization", force=args.force)


if __name__ == "__main__":
    main()
