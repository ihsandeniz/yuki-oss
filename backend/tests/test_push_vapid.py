"""VAPID public key üretimi — telefon bildiriminin ilk adımı (2026-09-18).

🔴 Neden var: `_get_or_create_vapid_keys` `v.public_key_urlsafe_base64` diye bir
üye okuyordu ve py_vapid'de **öyle bir üye yok** — `Vapid.from_file` bir
`Vapid02` döndürür (üyeler: `public_key` · `public_pem` · `sign` · `verify` …).
Uç 500 veriyordu, yani tarayıcı `applicationServerKey`i hiç alamıyordu ve
**abone olma adımı en başta ölüyordu**. Kimse fark etmemişti çünkü uç hiçbir
testte çağrılmıyordu; kusur Dalga 4/1'in kademe turunda, uç uçtan uca
ölçülünce ortaya çıktı.

Bu dosya *"anahtar üretiliyor"* demez — üretilen değerin **Web Push'un kabul
edeceği biçimde** olduğunu ölçer (RFC 8292 / uncompressed point).
"""
from __future__ import annotations

import base64

import pytest

from app.api import push as push_api


@pytest.fixture()
def gecici_anahtar_dizini(tmp_path, monkeypatch):
    """Gerçek kullanıcı anahtarına DOKUNMA — her tur kendi dizininde üretsin."""
    monkeypatch.setattr(push_api, "_PRIV_KEY", tmp_path / "vapid_private.pem")
    monkeypatch.setattr(push_api, "_PUB_KEY", tmp_path / "vapid_public.pem")
    return tmp_path


def test_anahtar_uretiliyor_ve_okunuyor(gecici_anahtar_dizini):
    yol, pub = push_api._get_or_create_vapid_keys()
    assert (gecici_anahtar_dizini / "vapid_private.pem").exists()
    assert isinstance(pub, str) and pub


def test_bicim_web_push_uyumlu(gecici_anahtar_dizini):
    """87 karakter · padding YOK · 'B' ile başlar (0x04 uncompressed point öneki).

    Tarayıcı bu değeri `applicationServerKey` olarak alır; biçim bozuksa
    `pushManager.subscribe()` sessizce reddeder.
    """
    _, pub = push_api._get_or_create_vapid_keys()
    assert "=" not in pub, "padding var — urlsafe base64 padding'siz olmalı"
    assert "+" not in pub and "/" not in pub, "urlsafe alfabe değil"
    assert len(pub) == 87, f"87 karakter bekleniyordu, {len(pub)} geldi"
    assert pub.startswith("B"), "0x04 öneki yok — uncompressed point değil"


def test_ham_bayt_65(gecici_anahtar_dizini):
    """Çözülmüş hâli tam 65 bayt olmalı (1 önek + 32 X + 32 Y)."""
    _, pub = push_api._get_or_create_vapid_keys()
    ham = base64.urlsafe_b64decode(pub + "=" * (-len(pub) % 4))
    assert len(ham) == 65, f"65 bayt bekleniyordu, {len(ham)} geldi"
    assert ham[0] == 0x04, "ilk bayt 0x04 değil"


def test_ikinci_cagri_ayni_anahtari_doner(gecici_anahtar_dizini):
    """Her çağrıda yeni anahtar üretilseydi mevcut aboneliklerin hepsi ölürdü."""
    _, ilk = push_api._get_or_create_vapid_keys()
    _, ikinci = push_api._get_or_create_vapid_keys()
    assert ilk == ikinci


def test_tarayici_aboneligi_sunucuya_yeniden_bildiriliyor():
    """2026-09-27 ölçüldü (olcum/push_abone_olc.py): tarayıcıda abonelik varken `_subscribeToPush`
    hemen dönüyordu → sunucu aboneyi 410/404 temizliğiyle silmişse cihaz bir daha kaydolmuyordu
    (tarayıcı "aboneyim", sunucu 0). Sonra: açılışta POST /subscribe, sayaç 0→1, tekrarda 1 (upsert)."""
    from pathlib import Path
    kod = (Path(__file__).resolve().parents[2] / "frontend" / "js" / "core.js").read_text(encoding="utf-8")
    govde = kod[kod.index("async function _subscribeToPush"):]
    govde = govde[: govde.index("\n}\n")]
    assert "if (existing && !isNew) return" not in govde, "var olan abonelikte erken dönüş geri gelmiş"
    assert govde.index("if (!sub) {") < govde.index("authFetch('/api/push/subscribe'"), \
        "abonelik yalnız yeni oluşturulunca gönderiliyor"
    assert "Bearer ${_authToken}" not in govde, "düz fetch: kilitli kurulumda açılışta sessizce 401"
