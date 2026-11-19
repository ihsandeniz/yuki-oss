""" ② — i18n Dalga 2 dosya KUYRUĞU (2026-09-22).

Dalga 2'nin büyük dosyaları (intro-sequences · planner · core · map-engine)
kendi kapılarını aldı. Kalan ~22 küçük dosya tek tek sırayla çevriliyor. Bu
dosya o kuyruğun kapısı: çevrilmiş sayılan her dosya `CEVRILMIS` tablosuna
girer ve buradaki dört ölçüden geçmek zorunda kalır.

  ① Türkçe harf taşıyan string literal YOK (konsol ve bilinçli istisna hariç)
  ② Dosyanın KENDİ ön ekli sarmalayıcısı var ve YukiDil'e devrediyor
  ③ `yuki-dil-degisti` dinleyicisi var (açık ekran yeni dile geçer)
  ④ Kullanılan her anahtar tr + en sözlüğünde TANIMLI

🔑 Cırcır dosya düzeyinde: tabloya giren dosya çıkamaz. Çıkarmak bir KARARDIR
ve gerekçesi buraya yazılır. (Kalem sayacı `test_faz3_dalga2_js_metni.py`'deki
`KANCA_TABAN` intro-sequences'a özeldir, bu dosyaları saymaz.)
"""
from __future__ import annotations

import re
from pathlib import Path

from yardim import FRONTEND, sozluk, yorumsuz

BACKEND = Path(__file__).resolve().parents[1]

# dosya → sarmalayıcı adı. Ad dosyaya ÖZEL: klasik script'te `function _t`
# window._t'yi ezer (core.js'in adı) — map-engine turunda bu yüzden `_mt` seçildi.
CEVRILMIS = {
    "js/mic-devices.js": "_mdt",
    "modes/skill-card.js": "_sct",
    "modes/chat-modes.js": "_t",   # IIFE içinde, Blok 7'den beri; window'a sızmıyor
    # js/panel-view.js + js/alice-canvas.js 11-13'te silindi (PANEL sekmesi kalktı).
    "modes/game-mode.js": "_gmt",  #  paket 3: animasyon etiketleri + modul başlıkları + panel metni
    # ── kuyruk 2 (2026-09-22) ──
    "modes/hud-ring.js": "_hrt",
    "js/yedekleme.js": "_ydt",
    "js/updater-ui.js": "_uut",
    "js/model-downloader.js": "_mdlt",
    "js/google-baglanti.js": "_gbt",
    "js/app-lock.js": "_alt",
    "js/cihazlar.js": "_czt",
    "js/tab-nav.js": "_tnt",
    "js/tab-switcher.js": "_tst",
    "js/ajan-view.js": "_ajt",     # AJAN sekmesi, doğarken kuyrukta
    "js/duvar.js": "_dvt",
    "js/tema.js": "_tmt",
    "js/tema-panel.js": "_tpt",   # 10-01: TEMA ortam seç (panel 14)
    "modes/gfx.js": "_gft",
    "modes/yuki-3d.js": "_y3t",
    "js/giris-konsol.js": "_gkt",   # 10-11 Halka Konsolu küçültme
    "modes/sohbet-sahne.js": "_t",  # 10-11 CANLI turunda kuyruğa girdi (IIFE içinde, window'a sızmıyor)
}
# 🚫 js/map-init.js BİLEREK YOK: içindeki Türkçe (Altın=, Portföy=, TAB_CONTEXT…) arayüz
# metni değil, LLM'e giden bağlam. Çevirmek Yuki'nin gördüğü veriyi değiştirir, kullanıcının
# gördüğünü değil. Karar: rapor FAZ3-DALGA2-INDI.md §19.

# Bilinçli Türkçe-harfli literal (metin değil veri). Gerekçesiz satır eklenmez.
ISTISNA = {
    # Kod-çözme animasyonunun karıştırma alfabesi — okunacak metin değil.
    "modes/skill-card.js": {"ABCÇDEFGĞHIİJKLMNOÖPRSŞTUÜVYZ0123456789#%◆▲"},
    # electron/delta-updater.js:548'in yolladığı AŞAMA DEĞERİ — çevrilirse düğme hiç değişmez.
    "js/updater-ui.js": {"uygulanıyor"},
}

_TR_HARF = re.compile(r"[çğıöşüÇĞİÖŞÜ]")
_LITERAL = re.compile(r"'((?:[^'\\\n]|\\.)*)'|\"((?:[^\"\\\n]|\\.)*)\"|`((?:[^`\\]|\\.)*)`", re.S)


def _kod(yol: str) -> str:
    return yorumsuz((FRONTEND / yol).read_text(encoding="utf-8"))


def test_TURKCE_literal_kalmadi():
    ihlal = []
    for yol in CEVRILMIS:
        for satir_no, satir in enumerate(_kod(yol).splitlines(), 1):
            if "console." in satir:
                continue                      # geliştirici günlüğü, kullanıcı görmez
            for m in _LITERAL.finditer(satir):
                metin = next(g for g in m.groups() if g is not None)
                if _TR_HARF.search(metin) and metin not in ISTISNA.get(yol, set()):
                    ihlal.append(f"{yol}:{satir_no}: {metin[:60]!r}")
    assert not ihlal, "Çevrilmiş sayılan dosyada Türkçe metin kaldı:\n" + "\n".join(ihlal)


def test_KENDI_sarmalayicisi_var_ve_devrediyor():
    for yol, ad in CEVRILMIS.items():
        kod = _kod(yol)
        assert re.search(rf"function {re.escape(ad)}\(anahtar, degerler\)", kod), (
            f"{yol}: `{ad}` sarmalayıcısı yok"
        )
        assert "window.YukiDil.t(anahtar, degerler)" in kod, f"{yol}: YukiDil'e devretmiyor"
        assert "String(anahtar)" in kod, f"{yol}: bilinmeyen anahtarda anahtarı döndürmüyor"


def test_DIL_DEGISIMINI_dinliyor():
    """🔴 Olay WINDOW'da yayınlanır (`dil.js`: `window.dispatchEvent`). `document`'a
    bağlanan dinleyici hiç tetiklenmez — olay adının dosyada GEÇMESİ yetmez.
    2026-09-22: kuyruk 2'nin brief'i `document` diyordu, 8 dosya sessizce ölü
    dinleyiciyle geldi; eski test (yalnız ad araması) hepsine yeşil verirdi."""
    dil = (FRONTEND / "js" / "dil.js").read_text(encoding="utf-8")
    assert "window.dispatchEvent(new CustomEvent('yuki-dil-degisti'" in dil, (
        "dil.js olayı artık window'da yayınlamıyor — bu testin varsayımı değişti"
    )
    for yol in CEVRILMIS:
        kod = _kod(yol)
        assert "window.addEventListener('yuki-dil-degisti'" in kod, (
            f"{yol}: dil değişimini dinlemiyor — açık ekran eski dilde kalır"
        )
        assert not re.search(r"document\.addEventListener\(\s*'yuki-dil-degisti'", kod), (
            f"{yol}: dil dinleyicisi document'a bağlı — olay window'da, HİÇ çalışmaz"
        )


def _kullanilan_anahtarlar(yol: str, ad: str) -> set[str]:
    kod = _kod(yol)
    anahtarlar = set(re.findall(rf"\b{re.escape(ad)}\('([a-z0-9][\w.-]*)'", kod))
    # Anahtar tutan veri alanları (`banner: 'beceri.skill.banner'`).
    anahtarlar |= set(re.findall(r":\s*'((?:beceri|mik|gorunum|karakter|sohbet|panel)\.[\w.-]+)'", kod))
    # `'gorunum.mod.' + key` gibi ön ek birleştirmeleri anahtar değil — onları
    # dosyaya özel test (getter'lar) ayrıca ölçüyor.
    return {k for k in anahtarlar if not k.endswith(".")}


def test_kullanilan_her_ANAHTAR_iki_sozlukte_de_var():
    tr, en = sozluk("tr"), sozluk("en")
    eksik = []
    for yol, ad in CEVRILMIS.items():
        for k in sorted(_kullanilan_anahtarlar(yol, ad)):
            for dil, s in (("tr", tr), ("en", en)):
                if k not in s:
                    eksik.append(f"{yol} → {dil}: {k}")
    assert not eksik, "Sözlükte olmayan anahtar (ekranda ham anahtar görünür):\n" + "\n".join(eksik)


# --------------------------------------------------------------------------- #
# Dosyaya özel sözleşmeler
# --------------------------------------------------------------------------- #

def test_chat_modes_MOD_ve_KARAKTER_metni_okuma_aninda_cozuluyor():
    """MODES/CHARACTERS modül düzeyi sabit. Metin orada çözülseydi ilk yükleme
    dilinde donardı; `get` ile okuma anına bırakıldı. game-mode.js ve hud-ring.js
    `window.MODE_CHARACTERS`'tan `c.title` okuyor — getter onları da kapsar."""
    kod = _kod("modes/chat-modes.js")
    assert "get title()" in kod and "get label()" in kod and "get desc()" in kod
    assert not re.search(r"title:\s*'", kod), "karakter unvanı yine düz metin"
    tr, en = sozluk("tr"), sozluk("en")
    modlar = re.findall(r"_mod\('([\w-]+)'", kod)
    karakterler = re.findall(r"_kar\('(\w+)'", kod)
    assert modlar and karakterler
    for dil, s in (("tr", tr), ("en", en)):
        for m in modlar:
            for alan in ("ad", "aciklama"):
                assert f"gorunum.mod.{m}.{alan}" in s, f"{dil}: gorunum.mod.{m}.{alan} yok"
        for k in karakterler:
            assert f"karakter.{k}.unvan" in s, f"{dil}: karakter.{k}.unvan yok"


def test_chat_modes_karsilama_BASLIGI_sozlukten():
    """Boş sohbet başlığı `data-i18n` taşıyor ama chat-modes.js onu çalışma
    anında yazıyor → dil.js elemanı sahiplenmiyor. Düz metin yazılırsa EN'de
    Türkçe donar (2026-09-22'de böyle bulundu)."""
    kod = _kod("modes/chat-modes.js")
    assert "_t('sohbet.merhaba-ben', { ad })" in kod
    assert "Merhaba, ben" not in kod


def test_mic_devices_TITLE_sahipligi_kendinde():
    """`#mic-btn` title'ını bu dosya yazıyor; dil.js geri çekiliyor. Tazeleme
    dinleyicisi aynı yardımcıyı (`_etiketleriYaz`) çağırmalı."""
    kod = _kod("js/mic-devices.js")
    assert "function _etiketleriYaz()" in kod
    dinleyici = kod.split("'yuki-dil-degisti'", 1)[1][:400]
    assert "_etiketleriYaz()" in dinleyici


def test_beceri_karti_backend_ANAHTAR_gonderiyor():
    """Kart metni backend'den Türkçe geliyordu (`ilk kullanım · x`, `BÜYÜK BİLGE`,
    `MOD BAŞLATILDI`). Artık `name_key`/`tag_key` gidiyor; düz metin yalnız yedek."""
    se = (BACKEND / "app" / "services" / "skill_events.py").read_text(encoding="utf-8")
    assert 'tag_key="beceri.unlock.tag-arac"' in se
    assert 'name_key="beceri.buyuk-bilge"' in se
    assert 'tag_key="beceri.task.tag-sayi"' in se

    tr, en = sozluk("tr"), sozluk("en")
    govde = se.split("_FRIENDLY = {", 1)[1].split("}", 1)[0]
    araclar = re.findall(r'"(\w+)":', govde)
    assert len(araclar) >= 20
    for dil, s in (("tr", tr), ("en", en)):
        eksik = [a for a in araclar if f"beceri.arac.{a}" not in s]
        assert not eksik, f"{dil}: _FRIENDLY aracının kart adı sözlükte yok: {eksik}"


def test_mod_karti_TURKCE_banner_gondermiyor():
    """Backend `sub`/`banner` gönderirse frontend'in `mode` kalıbını EZER."""
    kod = (BACKEND / "app" / "services" / "tools" / "modes.py").read_text(encoding="utf-8")
    govde = kod.split("async def _emit_card", 1)[1].split("\nasync def ", 1)[0].split("\ndef ", 1)[0]
    satirlar = [s for s in govde.splitlines() if not s.lstrip().startswith("#")]
    assert not any("banner=" in s or "sub=" in s for s in satirlar), (
        "_emit_card yine banner/sub gönderiyor — EN kullanıcı Türkçe kart görür"
    )


def test_CSS_content_ile_TURKCE_metin_basilmiyor():
    """🔴 Canlı turların KÖR NOKTASI (2026-09-22'de bulundu): turlar DOM metnini
    ölçer, `::before/::after { content: '…' }` sözde-eleman metnini GÖRMEZ.
    Durum rozeti `content: 'HAZIR'` ile EN kullanıcıya Türkçe görünüyordu ve
    dört dalga boyunca hiçbir tur yakalamadı. Metin JS'ten özniteliğe yazılır,
    CSS `content: attr(...)` ile okur. Bu kapı tüm CSS'i tarar."""
    ihlal = []
    for css in sorted(FRONTEND.rglob("*.css")):
        if "node_modules" in css.parts or "dist" in css.parts:
            continue
        metin = re.sub(r"/\*.*?\*/", " ", css.read_text(encoding="utf-8"), flags=re.S)
        for m in re.finditer(r"content:\s*(['\"])((?:(?!\1).)*)\1", metin):
            if _TR_HARF.search(m.group(2)) or re.search(r"[A-Za-z]{4,}", m.group(2)):
                ihlal.append(f"{css.relative_to(FRONTEND)}: content: {m.group(2)[:50]!r}")
    assert not ihlal, "CSS sözde-elemanında sabit metin (çevrilemez):\n" + "\n".join(ihlal)


def test_durum_rozeti_ve_panel_bos_metni_ozellikten_okunuyor():
    kabuk = (FRONTEND / "css" / "kabuk.css").read_text(encoding="utf-8")
    assert "content: attr(data-durum-metni)" in kabuk
    core = _kod("js/core.js")
    assert "b.setAttribute('data-durum-metni', _t(k))" in core
    assert "'state-busy': 'durum.mesgul'" in core
    assert "dene('durum-rozeti', _durumMetniYaz)" in core
    # 11-13 : PANEL sekmesi ve alice-canvas.js kalktı; eski ::before metni de geri gelmesin.
    pj = (FRONTEND / "css" / "panel-jobs.css").read_text(encoding="utf-8")
    assert "content: attr(data-bos-metin)" not in pj, "eski ::before metni geri geldi"
