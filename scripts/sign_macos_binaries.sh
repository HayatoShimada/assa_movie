#!/usr/bin/env bash
# 同梱バイナリ(ffmpeg / ffprobe / whisper-cli)にDeveloper ID署名を付ける。
#
# Tauriのバンドラは .app 本体とサイドカー(externalBin)には署名するが、
# resources/ に置いたバイナリには署名しない。公証(notarization)は
# バンドル内の全Mach-Oに「Developer ID署名+secure timestamp+
# Hardened Runtime」を要求するので、バンドル前にここで署名しておく。
# (実測: 3つとも "not signed with a valid Developer ID certificate" で
#  公証がInvalidになった)
#
# ./dev.sh package と release.yml が「パッケージを作る」直前に呼ぶ。
# APPLE_SIGNING_IDENTITY が無ければ何もしない(無署名ビルドはそのまま通る)。
set -euo pipefail
cd "$(dirname "$0")/.."

[ "$(uname -s)" = "Darwin" ] || exit 0
if [ -z "${APPLE_SIGNING_IDENTITY:-}" ]; then
  echo "APPLE_SIGNING_IDENTITY が無いので同梱バイナリは署名しません"
  exit 0
fi

# CI用: 証明書が環境変数で渡されていて、キーチェーンにまだ無ければ取り込む。
# (ローカルはログインキーチェーンの証明書をそのまま使う)
# grep -q は一致した時点で抜けるので、パイプのままだとpipefailで
# securityのSIGPIPEが失敗扱いになる。出力を受けてから調べる
IDENTITIES="$(security find-identity -v -p codesigning)"
if ! grep -qF "$APPLE_SIGNING_IDENTITY" <<< "$IDENTITIES"; then
  if [ -z "${APPLE_CERTIFICATE:-}" ]; then
    echo "✗ 証明書 '$APPLE_SIGNING_IDENTITY' がキーチェーンに無く、APPLE_CERTIFICATE も未設定です" >&2
    exit 1
  fi
  # 一時キーチェーンへの差し替えはCI専用。手元で実行するとログインキーチェーン
  # 以外の検索リストを消してしまうので、ローカルでは取り込みを案内して止める
  if [ -z "${RUNNER_TEMP:-}" ]; then
    echo "✗ 証明書 '$APPLE_SIGNING_IDENTITY' がキーチェーンにありません。" >&2
    echo "  手元ではキーチェーンアクセスで .p12 をログインキーチェーンに取り込んでください" >&2
    exit 1
  fi
  echo "=== 証明書を一時キーチェーンへ取り込む ==="
  KEYCHAIN="$RUNNER_TEMP/ks-sign.keychain-db"
  KEYCHAIN_PASS="$(openssl rand -hex 16)"
  security create-keychain -p "$KEYCHAIN_PASS" "$KEYCHAIN"
  security set-keychain-settings -lut 3600 "$KEYCHAIN"
  security unlock-keychain -p "$KEYCHAIN_PASS" "$KEYCHAIN"
  echo "$APPLE_CERTIFICATE" | base64 -d > "$RUNNER_TEMP/ks-cert.p12"
  security import "$RUNNER_TEMP/ks-cert.p12" -k "$KEYCHAIN" \
    -P "${APPLE_CERTIFICATE_PASSWORD:-}" -T /usr/bin/codesign
  rm -f "$RUNNER_TEMP/ks-cert.p12"
  security set-key-partition-list -S apple-tool:,apple: -k "$KEYCHAIN_PASS" "$KEYCHAIN" > /dev/null
  security list-keychains -d user -s "$KEYCHAIN" login.keychain
fi

echo "=== 同梱バイナリに署名 ==="
for bin in frontend/src-tauri/resources/bin/ffmpeg \
           frontend/src-tauri/resources/bin/ffprobe \
           frontend/src-tauri/resources/bin/whisper-cli; do
  [ -f "$bin" ] || { echo "✗ 無い: $bin(先にビルドスクリプトを回す)" >&2; exit 1; }
  codesign --force --options runtime --timestamp \
    --sign "$APPLE_SIGNING_IDENTITY" "$bin"
  # 署名の不備は公証で弾かれるまで気付けない(バンドル後なので遅い)。ここで全部確かめる
  codesign --verify --strict "$bin"
  echo "  署名: $bin"
done
echo "=== できました ==="
