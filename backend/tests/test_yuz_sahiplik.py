"""Sahiplik kaydı ile yüz kaydı AYRIŞMAMALI.

🔴 **Sahada bulundu (2026-09-06, ipek'ın kurulumu).** Yüzle giriş şöyle
başarısız oluyordu:

    Canlılık GEÇTİ: 3/2 kırpma, 40 kare
    Yüzle giriş: ✗ (tanınan=ipek verdict=high dist=0.1852)

Canlılık geçmiş, yüz `verdict=high` ile tanınmış — giriş yine reddedilmiş.
Depoya bakınca sebep göründü:

    owner : "sahip"      ← sahiplik bu ada bağlı
    faces : ["ipek"]    ← ama o adla kayıtlı yüz YOK

Kronoloji: sahibin yüzü silinmiş (`delete_face("sahip")`), `owner` alanı
öksüz kalmış. `owner_enrolled()` yalnız adın varlığına baktığı için
`/api/face/login-status` **enrolled:true** demiş, kilit ekranında "Yüzümle gir"
düğmesi çıkmış, kullanıcı göz kırpmış — ve hiçbir yerde yazmayan bir sebeple
reddedilmiş.

📏 İki ders, ikisi de test edilir:
  ① Bir yeteneği ilan eden bayrak, yeteneğin kendisini değil bir **kaydın
     varlığını** ölçüyorsa er geç yalan söyler.
  ② Silme işlemi, sildiği şeye bağlı **türetilmiş durumu** da düşürmelidir.
"""

import numpy as np
import pytest

from app.services import face_multi_auth as fma
from app.services import face_store


@pytest.fixture(autouse=True)
def temiz_depo(tmp_path, monkeypatch):
    # Gerçek ad `_DOSYA` — eskiden olmayan adlar `raising=False` ile yamalanıyordu ve
    # `_sifirla()` depo kökündeki faces.json'u boşaltıyordu (09-27 ölçüldü).
    monkeypatch.setattr(face_store, "_DOSYA", tmp_path / "faces.json")
    face_store._sifirla()
    yield
    face_store._sifirla()


def _embedding(tohum: int) -> np.ndarray:
    rng = np.random.default_rng(tohum)
    v = rng.normal(size=512).astype(np.float32)
    return v / np.linalg.norm(v)


def test_sahip_adi_varken_yuzu_yoksa_KAYITLI_SAYILMAZ():
    """🔑 Sahanın kendisi: owner='sahip' ama o adla yüz yok."""
    face_store.ekle("ipek", _embedding(1))
    face_store.sahip_yaz("sahip")

    assert fma.get_owner() == "sahip"
    assert fma.owner_enrolled() is False, (
        "Sahip adı var ama YÜZÜ yok — 'kayıtlı' demek kilit ekranında "
        "çalışmayan bir 'Yüzümle gir' düğmesi gösterir."
    )


def test_sahip_yuzu_varsa_kayitli_sayilir():
    face_store.ekle("sahip", _embedding(2))
    face_store.sahip_yaz("sahip")
    assert fma.owner_enrolled() is True


def test_sahip_hic_atanmamissa_kayitli_degil():
    face_store.ekle("ipek", _embedding(3))
    assert fma.owner_enrolled() is False


@pytest.mark.anyio
async def test_sahibin_yuzu_silinince_SAHIPLIK_DUSER():
    """Silme, türetilmiş durumu da düşürmeli — öksüz `owner` bırakmamalı."""
    face_store.ekle("sahip", _embedding(4))
    face_store.sahip_yaz("sahip")
    assert fma.owner_enrolled() is True

    await fma.delete_face("sahip", sahip_onay=True)

    assert not fma.get_owner(), "sahip alanı öksüz kaldı"
    assert fma.owner_enrolled() is False


@pytest.mark.anyio
async def test_baskasinin_yuzu_silinince_sahiplik_KORUNUR():
    """Yalnız sahibin silinmesi sahipliği düşürmeli; başkasınınki dokunmamalı."""
    face_store.ekle("sahip", _embedding(5))
    face_store.ekle("ipek", _embedding(6))
    face_store.sahip_yaz("sahip")

    await fma.delete_face("ipek")

    assert fma.get_owner() == "sahip"
    assert fma.owner_enrolled() is True


@pytest.mark.anyio
async def test_silme_ad_buyuk_kucuk_harfe_takilmiyor():
    """Depo adı 'Sahip', silme 'sahip' gelirse sahiplik yine düşmeli —
    yoksa aynı öksüz kayıt farklı yazımla geri gelir."""
    face_store.ekle("Sahip", _embedding(7))
    face_store.sahip_yaz("Sahip")
    await fma.delete_face("Sahip", sahip_onay=True)
    assert not fma.get_owner()


@pytest.mark.anyio
async def test_ayni_adla_YENI_yuz_kaydi_sessizce_sahip_yapmaz():
    """🔴 `delete_face`in sahipliği düşürmesinin ASIL sebebi.

    Öksüz `owner="sahip"` bırakılsaydı, kullanıcı ileride aynı adla yeni bir yüz
    kaydettiğinde o yüz **sessizce sahip olurdu** — sahiplik açık bir eylemle
    (`/api/face/enroll`) verilir, ad çakışmasıyla değil.
    """
    face_store.ekle("sahip", _embedding(8))
    face_store.sahip_yaz("sahip")
    await fma.delete_face("sahip", sahip_onay=True)

    # Aynı adla BAŞKA birinin yüzü kaydedilirse sahip olmamalı
    face_store.ekle("sahip", _embedding(9))
    assert fma.owner_enrolled() is False, (
        "Öksüz sahip kaydı, aynı adla kaydedilen yeni yüzü sessizce sahip yaptı"
    )
