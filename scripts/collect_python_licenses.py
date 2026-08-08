"""配布するPythonバックエンドが取り込むパッケージのライセンス表記を集める。

PyInstallerは依存を1つの実行ファイルに取り込むので、これらは実質的に再配布に
あたる。MIT/BSD/Apache-2.0 はいずれも「著作権表示とライセンス文を添えること」を
求めるため、機械的に集めて1つのファイルにまとめる。

    build/sidecar-venv/Scripts/python scripts/collect_python_licenses.py \
        --out licenses/python-THIRD-PARTY-NOTICES.txt

**この venv で動かすこと。** 配布物に入るのは pyproject の
[project.dependencies] だけを入れた専用の仮想環境(scripts/build_sidecar.sh が作る)で、
開発用の .venv には torch など配布しないものが入っている。
"""

from __future__ import annotations

import argparse
import sys
from importlib import metadata
from pathlib import Path

# PyInstaller自身は成果物に入らない(入るのはブートローダだけ)。
# ビルドのためだけに仮想環境へ入っているものは表記の対象から外す
BUILD_ONLY = {
    "pyinstaller",
    "pyinstaller-hooks-contrib",
    "altgraph",
    "pefile",
    "pywin32-ctypes",
    "macholib",
    "setuptools",
    "pip",
    "wheel",
}

# ライセンス本文が入っていそうなファイル名(dist-info直下 / licenses/ 配下)
LICENSE_NAMES = ("LICENSE", "LICENCE", "COPYING", "NOTICE", "COPYRIGHT")

PYINSTALLER_NOTE = """\
■ PyInstaller のブートローダについて

この実行ファイルは PyInstaller で1ファイルに固めています。PyInstaller 本体は
成果物に含まれませんが、起動処理を行うブートローダのバイナリが含まれます。
ブートローダは GPL 2.0 に「これを用いて固めた成果物は任意のライセンスで配布して
よい」という例外条項が付いたライセンスで提供されています。
  https://github.com/pyinstaller/pyinstaller/blob/develop/COPYING.txt
"""


def _license_name(dist: metadata.Distribution) -> str:
    """ライセンス名を拾う。書き方がパッケージごとにばらばらなので順に当たる"""
    meta = dist.metadata
    # 新しい書き方(PEP 639)。License-Expression が最も信頼できる
    expression = meta.get("License-Expression")
    if expression:
        return expression.strip()
    # 分類子。"License :: OSI Approved :: MIT License" の末尾を使う
    classifiers = [c for c in meta.get_all("Classifier") or [] if c.startswith("License ::")]
    if classifiers:
        return " / ".join(c.split(" :: ")[-1] for c in classifiers)
    # 古い License フィールド。全文が丸ごと入っていることがあるので1行目だけ
    legacy = (meta.get("License") or "").strip()
    if legacy:
        first = legacy.splitlines()[0].strip()
        return first if len(first) <= 60 else "(下の本文を参照)"
    return "不明"


def _homepage(dist: metadata.Distribution) -> str:
    meta = dist.metadata
    for key in ("Home-page", "Download-URL"):
        if value := (meta.get(key) or "").strip():
            return value
    for entry in meta.get_all("Project-URL") or []:
        label, _, url = entry.partition(",")
        if label.strip().lower() in ("homepage", "source", "repository"):
            return url.strip()
    return ""


def _license_texts(dist: metadata.Distribution) -> list[tuple[str, str]]:
    """(ファイル名, 本文) の一覧。dist-infoに同梱されているものを拾う"""
    found: list[tuple[str, str]] = []
    for file in dist.files or []:
        name = Path(str(file)).name
        if not name.upper().startswith(LICENSE_NAMES):
            continue
        # PackagePath.read_text は errors を受け付けないので実体のパスで読む
        path = Path(dist.locate_file(file))
        try:
            found.append((name, path.read_text(encoding="utf-8", errors="replace")))
        except OSError:
            continue
    return found


def build_notice(dists: list[metadata.Distribution]) -> str:
    lines: list[str] = []
    lines.append("KirinukiStudio バックエンドが取り込んでいるソフトウェアのライセンス表記")
    lines.append("=" * 72)
    lines.append("")
    lines.append("KirinukiStudio 本体は MIT ライセンスです。バックエンドの実行ファイルには")
    lines.append("次のパッケージが取り込まれており、それぞれのライセンスに従います。")
    lines.append("")
    lines.append(PYINSTALLER_NOTE)
    lines.append("")
    lines.append("■ 一覧")
    lines.append("")
    for dist in dists:
        name = dist.metadata["Name"]
        home = _homepage(dist)
        lines.append(f"  {name} {dist.version}")
        lines.append(f"      ライセンス: {_license_name(dist)}")
        if home:
            lines.append(f"      入手先: {home}")
    lines.append("")
    lines.append("")
    lines.append("■ ライセンス本文")

    missing: list[str] = []
    for dist in dists:
        name = dist.metadata["Name"]
        texts = _license_texts(dist)
        if not texts:
            home = _homepage(dist)
            missing.append(
                f"{name} {dist.version} — {_license_name(dist)}"
                + (f" — {home}" if home else "")
            )
            continue
        for filename, body in texts:
            lines.append("")
            lines.append("-" * 72)
            lines.append(f"{name} {dist.version} — {filename}")
            lines.append("-" * 72)
            lines.append(body.rstrip())

    if missing:
        lines.append("")
        lines.append("-" * 72)
        lines.append("本文がパッケージに同梱されていないもの")
        lines.append("-" * 72)
        lines.append("次のパッケージは配布物にライセンス本文を含めていません。")
        lines.append("ライセンスの種類と入手先は下記のとおりで、本文は配布元で参照できます。")
        lines.append("")
        for item in missing:
            lines.append(f"  - {item}")

    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    dists = [
        d
        for d in metadata.distributions()
        if (d.metadata["Name"] or "").lower() not in BUILD_ONLY
    ]
    if not dists:
        print("パッケージが1つも見つかりません。仮想環境のpythonで実行してください", file=sys.stderr)
        return 1
    dists.sort(key=lambda d: (d.metadata["Name"] or "").lower())

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(build_notice(dists), encoding="utf-8")
    print(f"{len(dists)}件のパッケージを {args.out} にまとめました")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
