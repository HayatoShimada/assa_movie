"""ライセンスキーの発行ツール(発行側専用)。

秘密鍵はこのリポジトリに置かない。生成した `issuer_private.key` は
オフラインの安全な場所に保管する(漏れると誰でもキーを発行できる)。

    # 1回だけ: 鍵ペアを作る
    uv run python tools/license_tool.py keygen --out ~/kirinuki-issuer

    # 公開鍵を backend/core/license_key.py に貼る
    uv run python tools/license_tool.py pubkey --key ~/kirinuki-issuer/issuer_private.key

    # キーを発行する
    uv run python tools/license_tool.py issue \\
        --key ~/kirinuki-issuer/issuer_private.key \\
        --licensee "株式会社ほげ" --edition pro --years 1

    # 発行したキーを確認する
    uv run python tools/license_tool.py check "KS1.xxx.yyy"
"""

import argparse
import sys
from datetime import date
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.core import license as lic  # noqa: E402
from backend.core.license_key import PUBLIC_KEY  # noqa: E402

PRIVATE_NAME = "issuer_private.key"


def load_private(path: Path) -> Ed25519PrivateKey:
    return Ed25519PrivateKey.from_private_bytes(bytes.fromhex(path.read_text(encoding="utf-8").strip()))


def cmd_keygen(args) -> int:
    out = Path(args.out).expanduser()
    out.mkdir(parents=True, exist_ok=True)
    private_path = out / PRIVATE_NAME
    if private_path.exists() and not args.force:
        print(f"既に鍵があります: {private_path}(上書きするなら --force)")
        return 1

    private = Ed25519PrivateKey.generate()
    raw = private.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
    private_path.write_text(raw.hex() + "\n", encoding="utf-8")
    private_path.chmod(0o600)

    print(f"秘密鍵を書き出しました: {private_path}")
    print("この鍵が漏れると誰でもキーを発行できます。オフラインで保管してください。")
    print()
    print("backend/core/license_key.py に貼る公開鍵:")
    print(f'PUBLIC_KEY = "{lic.public_key_to_text(private.public_key())}"')
    return 0


def cmd_pubkey(args) -> int:
    private = load_private(Path(args.key).expanduser())
    print(lic.public_key_to_text(private.public_key()))
    return 0


def cmd_issue(args) -> int:
    private = load_private(Path(args.key).expanduser())
    today = date.today()
    expires = None
    if args.years:
        expires = today.replace(year=today.year + args.years).isoformat()

    payload = {
        "p": lic.PRODUCT,
        "e": args.edition,
        "i": today.isoformat(),
        "x": expires,
        "l": args.licensee,
        "s": args.seats,
    }
    key = lic.sign_payload(payload, private)
    print(key)
    print(f"\n宛先: {args.licensee} / エディション: {args.edition} / 期限: {expires or 'なし'}",
          file=sys.stderr)
    return 0


def cmd_check(args) -> int:
    result = lic.verify(args.key, args.public_key or PUBLIC_KEY)
    print(f"状態      : {result.status}")
    if result.status in ("invalid", "missing"):
        return 1
    print(f"宛先      : {result.licensee}")
    print(f"エディション: {result.edition}")
    print(f"発行日    : {result.issued}")
    print(f"有効期限  : {result.expires or 'なし'}")
    if result.days_left is not None:
        print(f"残り      : {result.days_left}日")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="ライセンスキーの発行ツール")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("keygen", help="鍵ペアを作る(1回だけ)")
    p.add_argument("--out", required=True, help="秘密鍵の保存先ディレクトリ")
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_keygen)

    p = sub.add_parser("pubkey", help="秘密鍵から公開鍵を出す")
    p.add_argument("--key", required=True)
    p.set_defaults(func=cmd_pubkey)

    p = sub.add_parser("issue", help="キーを1本発行する")
    p.add_argument("--key", required=True, help="秘密鍵のパス")
    p.add_argument("--licensee", required=True, help="ライセンシー名")
    p.add_argument("--edition", default="pro")
    p.add_argument("--years", type=int, default=1, help="有効年数(0で無期限)")
    p.add_argument("--seats", type=int, default=1, help="台数の目安(制限はしない)")
    p.set_defaults(func=cmd_issue)

    p = sub.add_parser("check", help="キーを検証する")
    p.add_argument("key")
    p.add_argument("--public-key", help="既定はアプリに埋め込まれた公開鍵")
    p.set_defaults(func=cmd_check)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
