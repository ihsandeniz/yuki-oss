""" ⑤ — yüz giriş / canlılık mesajları dil kapısı.

KİLİT EKRANI frontend'i çevrildi, ama ekranda görünen cümlelerin çoğu
backend'den geliyor: canlılık talimatı ("N kez göz kırpın"), red sebebi,
kalan hak, kayıt uyarıları. Bunlar Türkçe kalırsa İngilizce kullanıcı
kilit ekranında yarı Türkçe bir hata okur — Blok 4B arızasının yüz eşi.

TR metinler kataloğa BİREBİR taşındı: `test_face_liveness.py` ve
`test_yuz_parcali_gonderim.py` Türkçe alt dizgi arıyor ve yeşil kalmalı.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from app import config
from app.mesajlar import KATALOG, M, Mc

_BACKEND = Path(__file__).resolve().parents[1]
_TR = re.compile(r"[çğıöşüÇĞİÖŞÜ]")
_YUZ_DOSYALARI = ("app/api/face_api.py", "app/services/face_liveness.py",
                  "app/services/face_multi_auth.py", "app/services/face_store.py")


def _kod_satirlari(kaynak: str) -> str:
    kaynak = re.sub(r'"""(?:.|\n)*?"""', "", kaynak)
    kaynak = re.sub(r"\b(?:logger|log)\.\w+\((?:[^()]|\([^()]*\))*\)", "", kaynak)
    return "\n".join(s.split("#", 1)[0] for s in kaynak.splitlines())


def test_yuz_dosyalari_KULLANICIYA_ham_Turkce_gondermiyor():
    for yol in _YUZ_DOSYALARI:
        kod = _kod_satirlari((_BACKEND / yol).read_text(encoding="utf-8"))
        kalan = [m.group(0) for m in re.finditer(r"""f?(["'])[^"'\n]*\1""", kod)
                 if _TR.search(m.group(0))]
        assert not kalan, f"{yol}: ham Türkçe dizgi → {kalan}"


def test_yuz_anahtarlari_IKI_DILDE_dolu_ve_yer_tutucu_ayni():
    anahtarlar = sorted(k for k in KATALOG["tr"] if k.startswith(("yuz.", "canlilik.")))
    assert len(anahtarlar) >= 50
    yt = re.compile(r"\{(\w+)\}")
    for k in anahtarlar:
        en = KATALOG["en"].get(k)
        assert en, f"en: '{k}' eksik/boş"
        assert not _TR.search(en), f"en: '{k}' Türkçe harf taşıyor"
        # Yer tutucu düşerse İngilizce kullanıcı sayıyı/adı göremez
        assert set(yt.findall(en)) == set(yt.findall(KATALOG["tr"][k])), k


def test_islem_anahtarlari_KODDAKI_her_cagriyi_karsiliyor():
    """`_hata_cevir(e, "<islem>")` → `yuz.islem.<islem>`. Karşılığı yoksa 500
    mesajının ortasında ham anahtar görünür."""
    kod = (_BACKEND / "app/api/face_api.py").read_text(encoding="utf-8")
    islemler = set(re.findall(r'_hata_cevir\(e, "([\w-]+)"\)', kod))
    assert islemler, "çağrı bulunamadı — desen değişmiş"
    for i in islemler:
        for dil in ("tr", "en"):
            assert KATALOG[dil].get(f"yuz.islem.{i}"), f"{dil}: yuz.islem.{i} yok"


@pytest.fixture
def dil():
    onceki = config.get_arayuz_dili()
    yield
    config.set_arayuz_dili(onceki, persist=False)


@pytest.mark.asyncio
async def test_meydan_okuma_talimati_AKTIF_DILDE(dil):
    from app.services import face_liveness
    config.set_arayuz_dili("en", persist=False)
    m = await face_liveness.olustur("1.2.3.4")
    assert m["instruction"] == f"Look at the camera and blink {m['blinks']} times.", m
    config.set_arayuz_dili("tr", persist=False)
    m = await face_liveness.olustur("1.2.3.4")
    assert m["instruction"] == f"Kameraya bak ve {m['blinks']} kez göz kırp."


@pytest.mark.asyncio
async def test_canlilik_reddi_AKTIF_DILDE(dil):
    from app.services import face_liveness
    config.set_arayuz_dili("en", persist=False)
    sonuc = await face_liveness.dogrula("yok-boyle-bir-id", "1.2.3.4", [b"x"])
    assert sonuc["ok"] is False
    assert sonuc["reason"] == "Challenge not found or expired.", sonuc


def test_kalan_hak_COGUL():
    assert Mc("yuz.kalan-hak", 1, dil="en") == "1 attempt left."
    assert Mc("yuz.kalan-hak", 3, dil="en") == "3 attempts left."
    assert Mc("yuz.kalan-hak", 3, dil="tr") == "3 deneme hakkın kaldı."
    assert M("yuz.islem-hatasi", dil="en", islem=M("yuz.islem.dogrulama", dil="en")) == \
        "An error occurred during verification."
