"""M26: ライセンスキーのオフライン検証。

改竄・期限切れ・別製品のキーを弾けることをテーブル駆動で確かめる。
署名の生成はテスト内で行う(発行側の秘密鍵はリポジトリに置かない)。
"""

from datetime import date, timedelta

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from backend.core import license as lic


@pytest.fixture(scope="module")
def issuer():
    """テスト用の発行者(鍵ペア)。本番の秘密鍵とは無関係"""
    private = Ed25519PrivateKey.generate()
    return private, lic.public_key_to_text(private.public_key())


def issue(private, **overrides) -> str:
    payload = {
        "p": lic.PRODUCT,
        "e": "pro",
        "i": "2026-01-01",
        "x": "2027-01-01",
        "l": "85-Store",
        "s": 3,
    }
    payload.update(overrides)
    return lic.sign_payload(payload, private)


# ---- 正常系 ----
def test_正規のキーは有効(issuer):
    private, public = issuer
    result = lic.verify(issue(private), public, today=date(2026, 8, 8))
    assert result.status == "valid"
    assert result.edition == "pro"
    assert result.licensee == "85-Store"
    assert result.expires == date(2027, 1, 1)
    assert result.is_usable


def test_期限なしのキーは無期限に有効(issuer):
    private, public = issuer
    result = lic.verify(issue(private, x=None), public, today=date(2099, 1, 1))
    assert result.status == "valid"
    assert result.expires is None


def test_期限当日はまだ有効(issuer):
    private, public = issuer
    result = lic.verify(issue(private), public, today=date(2027, 1, 1))
    assert result.status == "valid"


# ---- 期限切れと猶予 ----
def test_期限切れ直後は猶予期間として使える(issuer):
    """更新の行き違いで作業中のユーザーを締め出さないための猶予"""
    private, public = issuer
    result = lic.verify(issue(private), public, today=date(2027, 1, 15))
    assert result.status == "grace"
    assert result.is_usable
    assert result.days_left is not None and result.days_left < 0


def test_猶予期間を過ぎたら使えない(issuer):
    private, public = issuer
    after_grace = date(2027, 1, 1) + timedelta(days=lic.GRACE_DAYS + 1)
    result = lic.verify(issue(private), public, today=after_grace)
    assert result.status == "expired"
    assert not result.is_usable


def test_期限が近いと残り日数が分かる(issuer):
    private, public = issuer
    result = lic.verify(issue(private), public, today=date(2026, 12, 25))
    assert result.status == "valid"
    assert result.days_left == 7
    assert result.expiring_soon


def test_余裕があるうちは通知しない(issuer):
    private, public = issuer
    result = lic.verify(issue(private), public, today=date(2026, 1, 2))
    assert not result.expiring_soon


# ---- 異常系 ----
def test_署名を改竄したキーは無効(issuer):
    private, public = issuer
    key = issue(private)
    head, payload, sig = key.split(".")
    broken = f"{head}.{payload}.{'A' * len(sig)}"
    assert lic.verify(broken, public).status == "invalid"


def test_中身を書き換えたキーは無効(issuer):
    """有効期限を伸ばしても署名が合わなくなる"""
    private, public = issuer
    key = issue(private)
    tampered = lic.sign_payload({"p": lic.PRODUCT, "e": "pro", "x": "2099-01-01"}, private)
    # 別の秘密鍵で作り直したものは当然通らない
    other = Ed25519PrivateKey.generate()
    assert lic.verify(lic.sign_payload({"p": lic.PRODUCT}, other), public).status == "invalid"
    # 正しい鍵で署名し直せば通る(=検証しているのは署名であってペイロードではない)
    assert lic.verify(tampered, public).status == "valid"
    assert lic.verify(key, public).status == "valid"


def test_別製品のキーは無効(issuer):
    private, public = issuer
    assert lic.verify(issue(private, p="other-app"), public).status == "invalid"


@pytest.mark.parametrize(
    "text",
    [
        "ただの文字列",
        "KS1.abc",                 # 部品が足りない
        "KS1.abc.def.ghi",         # 部品が多い
        "KS9.abc.def",             # 知らない形式
        "KS1.@@@.def",             # base64ではない
    ],
)
def test_壊れたキーは無効(issuer, text):
    _, public = issuer
    assert lic.verify(text, public).status == "invalid"


@pytest.mark.parametrize("empty", [None, "", "   ", "\n"])
def test_未登録は未登録として扱う(issuer, empty):
    """キーが無いのと壊れているのは、ユーザーへの案内が違うので区別する"""
    _, public = issuer
    result = lic.verify(empty, public)
    assert result.status == "missing"
    assert not result.is_usable


# ---- 保存と読み出し ----
def test_保存したキーを読み戻せる(tmp_path, issuer):
    private, _ = issuer
    key = issue(private)
    path = tmp_path / "license.key"
    lic.save_key(key, path)
    assert lic.load_key(path) == key
    # 空白や改行が混ざっても読める(コピペを想定)
    path.write_text(f"  {key}\n\n", encoding="utf-8")
    assert lic.load_key(path) == key


def test_キーが無ければNone(tmp_path):
    assert lic.load_key(tmp_path / "none.key") is None


def test_保存は上書きする(tmp_path, issuer):
    private, _ = issuer
    path = tmp_path / "license.key"
    lic.save_key(issue(private, l="旧"), path)
    lic.save_key(issue(private, l="新"), path)
    assert path.read_text(encoding="utf-8").count(".") == 2
