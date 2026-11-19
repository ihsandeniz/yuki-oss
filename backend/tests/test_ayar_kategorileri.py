"""Ayar panelinde BOŞ AÇILAN kategori ilan edilemez.

Bağlam: R1 raporu *"'Dil & Karakter' kategorisinin tek bir ayarı yok → tıklayan
kullanıcı 'Bu kategoride ayar yok' görüyor"* diyordu. 2026-08-12'de canlı ölçüldü
(Playwright, üç kademe): **iddia çürüdü** — o kategori 3 satır çiziyor (Asistan
Dili · Karakter/Persona · LLM Modeli), çünkü `intro-sequences.js` içinde
`catId==='dil'` diye SABİT bir dal vardı.

🔑 Asıl kusur oradaydı: backend "7 kategori var" diyor, hangisinin gerçekten
içeriği olduğunu yalnız frontend biliyordu. Şemasız yeni bir kategori eklendiğinde
hiçbir şey uyarmıyor, kullanıcı tıklayınca boş panel görüyordu. Kategori artık
kendi çizim biçimini beyan ediyor (`render`), bu testler de beyanın gerçeği
tutmasını sağlıyor.

*"Kural yazılı olmak uygulatmıyor, kapı uygulatıyor"* (2026-08-08 dersi).
"""

from __future__ import annotations

import re
from pathlib import Path

from app.api import settings_api

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
INTRO_JS = FRONTEND / "js" / "intro-sequences.js"


def _yorumsuz_js(metin: str) -> str:
    """JS yorumlarını at — açıklamada geçen bir kalıp 'kod' sanılmasın.

    (`test_ozellik_ilani.py` aynı tuzağa düşmüştü: testin kendi açıklama yorumu
    'çağrı' diye yakalanmıştı. Bu dosyada da düşüldü — regresyon sabiti
    aradığımız test, o sabiti ANLATAN yorumu buldu.)
    """
    metin = re.sub(r"/\*.*?\*/", "", metin, flags=re.DOTALL)
    return re.sub(r"(?<![:'\"])//[^\n]*", "", metin)

# Bir `render` değerinin frontend'de karşılığı olduğunu gösteren imza:
# hem seçim dalı hem çizici fonksiyon aranır — dal olup çizici olmazsa
# kategori yine boş açılır.
RENDER_IMZALARI = {
    settings_api.RENDER_LIVE: ("render==='live'", "function renderLiveTrio"),
    settings_api.RENDER_GFX: ("render==='gfx'", "function renderGfxBolumu"),
    settings_api.RENDER_GUVENLIK: ("render==='guvenlik'", "function renderGuvenlikBolumu"),
}

# `extra` = şema satırlarının altına eklenen ek panel.
EXTRA_IMZALARI = {
    settings_api.EXTRA_TTS: ("cat.extra==='tts'",),
    settings_api.EXTRA_GORUS: ("cat.extra==='gorus'",),
}


def _kullanilabilir_ayar_sayisi(cat_id: str) -> int:
    return sum(1 for s in settings_api._gorunur_sema()
               if s["cat"] == cat_id and s["available"])


def test_hicbir_kategori_bos_acilmiyor():
    """Her kategori ya kullanılabilir bir ayar taşır ya özel bir bölüm çizer."""
    bos = []
    for c in settings_api.CATEGORIES:
        if c.get("render"):
            continue
        if _kullanilabilir_ayar_sayisi(c["id"]) == 0:
            bos.append(c["id"])
    assert not bos, (
        f"tıklanınca boş açılacak kategori(ler): {bos} — ya ayar ekle, "
        f"ya `render` ver, ya CATEGORIES'ten çıkar"
    )


def test_ayar_gizleme_kategoriyi_bosaltmadi():
    """🔴 F1 ile birleşen risk: `available:false` damgası bir kategorinin TÜM
    ayarlarını süzerse kategori boş açılır — gizleme, boş panel üretmemeli.

    (Bugün 'ses' 7→4, 'algı' 9→5 düşüyor; ikisi de dolu kalıyor.)
    """
    for c in settings_api.CATEGORIES:
        if c.get("render"):
            continue
        ilan = sum(1 for s in settings_api.SETTINGS_SCHEMA if s["cat"] == c["id"])
        if ilan == 0:
            continue  # üstteki test yakalar
        assert _kullanilabilir_ayar_sayisi(c["id"]) > 0, (
            f"{c['id']}: şemadaki {ilan} ayarın hepsi gizlendi → kategori boş açılır"
        )


def test_bilinmeyen_render_degeri_yok():
    for c in settings_api.CATEGORIES:
        r = c.get("render")
        if r is None:
            continue
        assert r in RENDER_IMZALARI, (
            f"{c['id']}: tanınmayan render '{r}' — frontend onu çizemez"
        )


def test_bilinmeyen_extra_degeri_yok():
    for c in settings_api.CATEGORIES:
        e = c.get("extra")
        if e is None:
            continue
        assert e in EXTRA_IMZALARI, (
            f"{c['id']}: tanınmayan extra '{e}' — frontend o paneli gömemez"
        )


def test_frontend_kullanilan_her_extra_panelini_taniyor():
    kaynak = _yorumsuz_js(INTRO_JS.read_text(encoding="utf-8")).replace(" ", "")
    for c in settings_api.CATEGORIES:
        e = c.get("extra")
        if not e:
            continue
        for imza in EXTRA_IMZALARI[e]:
            assert imza.replace(" ", "") in kaynak, (
                f"{c['id']}: frontend '{e}' ek panelini tanımıyor (eksik: {imza})"
            )


def test_frontend_kullanilan_her_render_bicimini_taniyor():
    """🔑 Beyan ile çizim AYRI ölçülür.

    2026-08-09 karakter kilidi dersi: kapı vardı, arayüz kapıya bakmıyordu.
    Burada da backend `render:'gfx'` diyebilir ama frontend o dalı bilmiyorsa
    kategori sessizce boş açılır.
    """
    kaynak = _yorumsuz_js(INTRO_JS.read_text(encoding="utf-8")).replace(" ", "")
    for c in settings_api.CATEGORIES:
        r = c.get("render")
        if not r:
            continue
        for imza in RENDER_IMZALARI[r]:
            assert imza.replace(" ", "") in kaynak, (
                f"{c['id']}: frontend '{r}' biçimini tanımıyor (eksik: {imza})"
            )


def test_frontend_kategori_kimligini_sabit_yazmiyor():
    """Regresyon: `catId==='dil'` sabiti geri gelmesin.

    Sabit karşılaştırma, kuralın backend'de değil arayüzde saklanması demekti —
    bu dosyadaki testlerin hiçbiri onu göremezdi.
    """
    kaynak = _yorumsuz_js(INTRO_JS.read_text(encoding="utf-8")).replace(" ", "").replace('"', "'")
    for c in settings_api.CATEGORIES:
        assert f"catId==='{c['id']}'" not in kaynak, (
            f"frontend '{c['id']}' kategorisini sabit yazıyor — `cat.render` kullan"
        )


def test_kategori_alanlari_tam():
    """Etiketsiz/ikonsuz kategori sol menüde kimliksiz bir satır olur."""
    for c in settings_api.CATEGORIES:
        assert c.get("id") and c.get("label"), f"eksik alan: {c}"
        assert c.get("icon"), f"{c['id']}: ikon yok"


def test_kategori_kimlikleri_benzersiz():
    idler = [c["id"] for c in settings_api.CATEGORIES]
    assert len(idler) == len(set(idler)), f"yinelenen kategori kimliği: {idler}"


def test_semadaki_her_ayar_var_olan_bir_kategoriye_bagli():
    """Öksüz ayar hiçbir yerde çizilmez — sessizce kaybolur."""
    tanimli = {c["id"] for c in settings_api.CATEGORIES}
    oksuz = sorted({s["key"] for s in settings_api.SETTINGS_SCHEMA
                    if s["cat"] not in tanimli})
    assert not oksuz, f"kategorisi olmayan ayar(lar): {oksuz}"
