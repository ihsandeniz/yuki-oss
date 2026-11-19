"""FAZ 3 · DALGA 2 · BLOK 4B — sağlayıcı metinlerinin backend yarısı.

🔴 Bu dosyanın var olma sebebi bir YARIM TESLİM. Blok 4'te 🔑 ANAHTAR
panelinin frontend metinleri çevrildi ve canlı tur *"İngilizce ekranda Türkçe
kalan: 0"* dedi. Ekran görüntüsünde panelin yarısı hâlâ Türkçeydi: rehberin
gövdesi (`ucretsiz` · `not_` · `uyari`) ve Ollama'nın adı frontend'den değil
`services/llm_providers.py`'den geliyor.

📏 Ders: *bir panel "çevrildi" sayılmaz, onu DOLDURAN her kaynak çevrilene
kadar.* Kapsam kararı dosya bazlı verilmişti (Dalga 2 = JS metinleri) ama
kullanıcının gördüğü şey dosya değil EKRAN.

Kademe (`llm_config_api._sag_metin`): kaynak hâlâ `llm_providers.py` — ölçüm
orada yaşıyor ve bir kısıt değişince (Ollama'nın bağlam penceresi gibi) tek
yerde güncellenmeli. Katalog onu ÇEVİRİYOR, yeniden yazmıyor.
"""
from __future__ import annotations

from app.api.llm_config_api import _sag_metin
from app.mesajlar import KATALOG, M
from app.services import llm_providers as _lp


def _kaynak(sag, alan: str) -> str:
    return getattr(sag, "not_" if alan == "not" else alan, "") or ""


def test_saglayici_metni_KAYNAKLA_AYNI():
    """🔴 Çift sahiplik kapısı — Blok 1'deki `hq.cat.*` kapısının backend eşi.

    Katalogdaki TÜRKÇE değer `llm_providers.py`'dekiyle birebir aynı olmak
    zorunda. Ayrışırsa ölçüm güncellenip arayüz eski metni göstermeye devam
    eder ve bunu kimse fark etmez — Ollama uyarısı tam da böyle bir "ölçülmüş
    kısıt" (2026-08-08 canlı ölçümünden geliyor, bağlam penceresi rakamı var).
    """
    tr = KATALOG["tr"]
    for sag in _lp.tumu():
        for alan in ("ad", "ucretsiz", "not", "uyari"):
            anahtar = f"saglayici.{sag.kimlik}.{alan}"
            if anahtar not in tr:
                continue                      # çevirisi yok → yedeğe düşer
            assert tr[anahtar] == _kaynak(sag, alan), (
                f"{anahtar}: katalog '{tr[anahtar][:60]}' ≠ kaynak "
                f"'{_kaynak(sag, alan)[:60]}' — iki metin ayrışmış"
            )


def test_ceviri_YOKSA_kaynaga_dusuyor():
    """`M()` bilinmeyen anahtarda ANAHTARI döndürür, boş string değil. `_sag_metin`
    bunu `cev == anahtar` ile sorar; `if not cev` yazılsaydı çevirisi olmayan
    sağlayıcı arayüzde `saglayici.xai.ucretsiz` diye görünürdü."""
    xai = _lp.kayit("xai")
    assert xai is not None
    # `xai` bilerek çevrilmedi (metni yok) — yedek boş string olmalı, anahtar değil
    assert not _sag_metin(xai, "ucretsiz").startswith("saglayici.")


def test_EN_katalogu_TR_yi_kapsiyor():
    """Eksik bir İngilizce karşılık, panelde sessizce Türkçe metin bırakır
    (yedek zinciri `en` → `tr`). Kapsam boşluğu görünür olmalı."""
    tr, en = KATALOG["tr"], KATALOG["en"]
    eksik = sorted(k for k in tr if k.startswith("saglayici.") and k not in en)
    assert not eksik, f"en katalogda eksik sağlayıcı metni: {eksik}"


def test_ollama_uyarisi_OLCUMU_tasiyor():
    """Uyarı metni kozmetik değil: 2026-08-08 canlı ölçümünden geliyor
    (`truncating input prompt limit=2050 prompt=4097`). Çeviri rakamı ve
    çözümü düşürürse kullanıcı sessizce bozuk yanıtlar alır ve sebebini
    hiçbir yerde bulamaz."""
    for dil in ("tr", "en"):
        metin = M("saglayici.ollama.uyari", dil=dil)
        assert "4" in metin and "100" in metin.replace(".", "").replace(",", ""), (
            f"{dil}: uyarı token rakamını kaybetmiş"
        )
        assert "OLLAMA_CONTEXT_LENGTH=8192" in metin, (
            f"{dil}: uyarı çözümü (ortam değişkeni) kaybetmiş"
        )


def test_yerel_hata_metni_cevrilebilir():
    """Ollama kapalıyken panele düşen cümle. Ham `httpx` metni bilerek
    çevrilmiyor (log'un dili), ama kullanıcıya bakan kısım çevrilmeli —
    2026-08-08'de panelde ham İngilizce "All connection attempts failed"
    yazıyordu ve müşteri bunu "Yuki bozuk" diye okuyordu."""
    for dil in ("tr", "en"):
        metin = M("yerel.ulasilamadi", dil=dil, adres="http://x:1/v1", teknik="E")
        assert "http://x:1/v1" in metin, f"{dil}: adres yer tutucusu çözülmemiş"
        assert "ollama.com/download" in metin, f"{dil}: kurulum adresi düşmüş"


# --------------------------------------------------------------------------- #
# BLOK 6 / 6B — 🔒 GÜVENLİK odasının backend yarısı
#
# 🔴 Blok 4B'nin dersi burada İKİNCİ KEZ ölçüldü. Blok 6 frontend'i indikten
# sonra oda iki dilde tarandı: Türkçe kalem 15 → 4 düştü ve kalan dördü
# `faces.js` + `pydeps.kullanilabilir()` kaynaklıydı. "Dosya bitti" ile
# "ekran bitti" aynı şey değil; kapı EKRANI dolduran kaynakları sayıyor.
# --------------------------------------------------------------------------- #

import re as _re
from pathlib import Path as _Path

_BACKEND = _Path(__file__).resolve().parents[1]
_TR = _re.compile(r"[çğıöşüÇĞİÖŞÜ]")


def _ham_kullanici_metni(kaynak: str) -> list[str]:
    """`detail="…"` / `ValueError("…")` içindeki Türkçe harfli sabitler.

    Yorumlar ve log satırları ELENİYOR: ikisi de kullanıcıya gitmiyor ve
    log'un dili bilinçli olarak Türkçe kalıyor (geliştirici okuyor). Ölçü
    "dosyada Türkçe var mı" değil, **kullanıcıya Türkçe gidiyor mu**.
    """
    kaynak = _re.sub(r'"""(?:.|\n)*?"""', "", kaynak)
    kaynak = _re.sub(r"^\s*#.*$", "", kaynak, flags=_re.M)
    bulgular = []
    for m in _re.finditer(r'(?:detail|ValueError)\s*[=(]\s*(?:f?")([^"]{4,})"', kaynak):
        if _TR.search(m.group(1)):
            bulgular.append(m.group(1))
    return bulgular


def test_kilit_uclari_HAM_TURKCE_metin_tasimiyor():
    """Bu metinler GÜVENLİK panelinin toast'ına ve KİLİT EKRANINA düşüyor —
    yani frontend çevrilmişken bunlar Türkçe kalsaydı panel yarı Türkçe
    görünürdü (Blok 4B arızası)."""
    for yol in ("app/api/lock_api.py", "app/services/login_guard.py",
                "app/services/app_lock.py", "app/pydeps.py"):
        kalan = _ham_kullanici_metni((_BACKEND / yol).read_text(encoding="utf-8"))
        assert not kalan, f"{yol}: kullanıcıya ham Türkçe gidiyor → {kalan}"


def test_kilit_mesajlari_IKI_DILDE_de_dolu():
    """Katalog kapsama kapısı `en ⊇ tr` diyor ama boş string de "kapsıyor"
    sayılırdı. Bu kapı DOLULUK ölçüyor ve yer tutucunun ikisinde de
    çözüldüğünü sınıyor — `{dk}` İngilizce'de düşerse müşteri kaç dakika
    beklemesi gerektiğini öğrenemez."""
    for anahtar in ("kilit.kurulu-degil", "kilit.parola-yanlis",
                    "kilit.mevcut-parola-yanlis", "kilit.kaydedilemedi",
                    "kilit.uzunluk", "kilit.kalan-hak", "pydeps.eksik"):
        for dil in ("tr", "en"):
            assert KATALOG[dil].get(anahtar), f"{dil}: '{anahtar}' eksik/boş"

    for yol in ("parola", "yuz"):
        for durum in ("alt-var", "alt-yok"):
            anahtar = f"giris-kilidi.{yol}-{durum}"
            for dil in ("tr", "en"):
                metin = M(anahtar, dil=dil, dk=7, kez=5)
                assert "7" in metin, f"{dil}/{anahtar}: {{dk}} çözülmemiş"
                assert "{" not in metin, f"{dil}/{anahtar}: çözülmemiş yer tutucu"
            # İki yolun cümlesi AYRI olmalı: "parola kapandı" ile "yüz kapandı"
            # tek metne inerse kullanıcı hangi yolun kapandığını bilemez.
        assert M(f"giris-kilidi.{yol}-alt-var", dil="en", dk=7, kez=5) != \
            M(f"giris-kilidi.{yol}-alt-yok", dil="en", dk=7, kez=5)
    assert M("giris-kilidi.parola-alt-var", dil="en", dk=7, kez=5) != \
        M("giris-kilidi.yuz-alt-var", dil="en", dk=7, kez=5)


def test_parola_uzunluk_mesaji_GERCEK_SINIRI_soyluyor():
    """Sayılar sabit yazılmaz — `app_lock` kapısı değişirse mesaj da değişmeli.
    Çeviriye taşınırken en kolay kaybedilen şey buydu: cümleyi sözlüğe alıp
    sınırı elle yazmak, iki gerçek üretirdi."""
    from app.services import app_lock

    try:
        app_lock.parola_kur("x")
    except ValueError as e:
        mesaj = str(e)
    else:
        raise AssertionError("kısa parola kabul edildi — uzunluk kapısı ölü")
    assert str(app_lock.MIN_UZUNLUK) in mesaj and str(app_lock.MAX_UZUNLUK) in mesaj, (
        f"mesaj gerçek sınırı taşımıyor: {mesaj!r}"
    )
