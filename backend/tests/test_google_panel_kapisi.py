"""GOOGLE paneli — arayüz kapıları ( FAZ 2).

Panelin üç parçası **birbirine bağlıdır** ve biri eksik kalırsa kusur SESSİZDİR:

① Menü girdisi (`intro-sequences.js::HQ_MENU`) — yoksa panele **ulaşılamaz**.
   Bu projenin en sık kusur sınıfı: kod var, menü girdisi yok (TAM BOY modu
   tam olarak böyle ölmüştü).
② Açılış karşı-kuralı (`css/hq.css`) — `.hq-panel` `display:none !important`
   ile kapalı gelir. Kural yazılmazsa içerik **çizilir ama görünmez**
   (duvar panelinde ölçüldü: 9061 karakter çizilmiş, ekran boş).
③ Markup kabı (`index.html`) — JS `getElementById` ile onu arar.

Ayrıca kademe kapısı: panel **Pro**'dur (`require_planner`), menü girdisi
`kosul` ile FAIL-CLOSED bağlanmıştır — yetki *bilinmezken* de çizilmez.

📏 Kapı statiktir; canlı tur ayrıca var: `scratchpad/google-panel-canli-test.py`
   (6 senaryo — kimlik yok / biçimsiz / bağlı değil / bağlı / izin eksik / Free).
"""

import re
from pathlib import Path

from yardim import sozluk as _sozluk

KOK = Path(__file__).resolve().parents[2] / "frontend"
INDEX = (KOK / "index.html").read_text(encoding="utf-8")
HQ_CSS = (KOK / "css" / "hq.css").read_text(encoding="utf-8")
INTRO = (KOK / "js" / "intro-sequences.js").read_text(encoding="utf-8")
PANEL_JS = (KOK / "js" / "google-baglanti.js").read_text(encoding="utf-8")


def _kodu(kaynak: str) -> str:
    """Yorumları ayıklanmış kaynak.

    🪤 **Bu tur boyunca ÜÇ KEZ düşülen tuzak:** düz metin taraması, bir kuralı
    *anlatan* yorumu da kuralın **ihlali** sanır — ve kapı tam da doğru yazılmış
    dosyada kırmızı yanar. ("`confirm()` KULLANILMAZ" diyen yorum, `confirm(`
    aranınca eşleşir.) Yasak arayan her kapı kodu yorumdan ayırmalı.
    """
    satirlar = []
    blok = False
    for ham in kaynak.splitlines():
        s = ham.strip()
        if blok:
            if "*/" in s:
                blok = False
                s = s.split("*/", 1)[1]
            else:
                continue
        if s.startswith("//"):
            continue
        if "/*" in s:
            on, _, kalan = s.partition("/*")
            if "*/" in kalan:
                s = on + kalan.split("*/", 1)[1]
            else:
                s, blok = on, True
        if s:
            satirlar.append(s)
    return "\n".join(satirlar)


PANEL_KOD = _kodu(PANEL_JS)


def test_menu_girdisi_var():
    """① Menüsüz panel = ulaşılamaz panel.

    ⚠️ 2026-09-19 (FAZ 3 · Dalga 2) — bu iddia DEVREDİLDİ, gevşetilmedi.
    Eskiden `etiket:'Google'` aranıyordu; `HQ_MENU` artık metin değil ANAHTAR
    taşıyor (`etiket:'hq.menu.google'`), çünkü menü İngilizce müşteride de
    çizilmek zorunda. Eski deseni ARAMAYA devam etmek testi kırmızıda tutardı;
    metni sözlükten okumaya çevirmek ise iddiayı GÜÇLENDİRİYOR: girdinin var
    olması artık yeterli değil, adının iki dilde de karşılığı olması gerekiyor
    (anahtarı olup sözlükte karşılığı olmayan girdi, menüde `hq.menu.google`
    diye görünür — `dil.js::t` bilinmeyen anahtarda anahtarı döndürür).
    """
    assert re.search(r"id:\s*'google'", INTRO), "HQ_MENU'de google girdisi yok"
    m = re.search(r"id:\s*'google'.*?etiket:\s*'([^']+)'", INTRO, re.S)
    assert m, "google girdisinde etiket alanı yok"
    anahtar = m.group(1)
    assert anahtar.startswith("hq.menu."), (
        f"etiket bir çeviri anahtarı değil: {anahtar!r} — ham metin yazılmışsa "
        "İngilizce müşteride Türkçe kalır (FAZ 3 · Dalga 2)"
    )
    for dil in ("tr", "en"):
        assert anahtar in _sozluk(dil), f"{dil} sözlüğünde '{anahtar}' yok"


def test_menu_girdisi_pro_kapisina_bagli_ve_fail_closed():
    """🔴 Yetki BİLİNMEZKEN de çizilmemeli.

    `!== false` yazılsaydı, açılışta lisans fetch'i sürerken (ya da kilit
    ekranı yüzünden 401 alınmışken) girdi çizilir, Free kullanıcı panele girip
    403 yerdi. HQ'nun "Sonlandır" dersinin aynısı.
    """
    m = re.search(r"id:\s*'google'.*?\}", INTRO, re.S)
    assert m, "google girdisi bulunamadı"
    govde = m.group(0)
    assert "kosul" in govde, "google girdisinde kademe koşulu yok"
    assert "_yukiPlannerOk === true" in govde, \
        "koşul fail-closed değil (=== true olmalı, !== false DEĞİL)"


def test_kosul_mekanizmasi_menude_uygulaniyor():
    """Girdiye `kosul` yazmak yetmez — çizim döngüsü onu OKUMALI."""
    assert re.search(r"typeof\s+x\.kosul\s*===\s*'function'\s*&&\s*!x\.kosul\(\)", INTRO), \
        "hqMenuCiz koşulu uygulamıyor — girdi her kademede çizilir"


def test_acilis_karsi_kurali_var():
    """② Kuralsız panel: içerik çizilir, ekran boş kalır."""
    assert re.search(
        r'#tab-hq\[data-hq="google"\]\s+#hq-panel-google\s*\{[^}]*display:\s*flex\s*!important',
        HQ_CSS), "css/hq.css'te google açılış karşı-kuralı yok"


def test_markup_kabi_var():
    """③ JS kabı `getElementById` ile arar."""
    assert 'id="hq-panel-google"' in INDEX
    assert 'class="hq-panel"' in re.search(
        r'<div id="hq-panel-google"[^>]*>', INDEX).group(0)


def test_panel_scripti_yuklu_ve_damgali():
    """Script etiketi yoksa panel hiç çizilmez; `?v=` yoksa müşteri eskisini alır."""
    m = re.search(r'src="/ui/js/google-baglanti\.js\?v=(\d+)"', INDEX)
    assert m, "google-baglanti.js script etiketi yok ya da ?v= damgası eksik"


def test_switchHqTab_paneli_besliyor():
    """Panel açılınca içerik çizilmeli — ve ÖNBELLEKLENMEMELİ.

    Bağlantı durumu panel dışında değişir (onay BAŞKA PENCEREDE tamamlanır,
    ya da kullanıcı Google tarafından erişimi iptal eder). `_loaded` bayrağı
    konsaydı kullanıcı bağlandıktan sonra hâlâ "bağlı değil" görürdü.
    """
    m = re.search(r"if\(name==='google'\)\{([^}]*)\}", INTRO)
    assert m, "switchHqTab google dalını taşımıyor"
    assert "googlePanelAc" in m.group(1)
    assert "_loaded" not in m.group(1), "panel önbelleğe alınmış — bayat durum gösterir"


def test_panel_satir_ici_stil_yazmiyor():
    """Panel tasarım sistemine oturmalı.

    🔴 İlk sürüm inline `display:grid;gap` + `.hq-btn` kullandı; canlı turda
    görüldü: düğmeler dikey kutulara dönüştü, panel öbür panellere hiç
    benzemiyordu. Sınıflar: `.ak-govde/.ak-bas/.alan/.girdi/.dg-*`.
    """
    suclular = [s for s in PANEL_KOD.splitlines() if "style=" in s]
    assert not suclular, f"panelde satır içi stil kalmış: {suclular[:3]}"
    # ak-govde/ak-bas yalnız silinen Pro kartındaydı (F2, kademe kalktı).
    for sinif in ("ak-form", "alan", "girdi", "dg-birincil"):
        assert sinif in PANEL_JS, f"tasarım sistemi sınıfı kullanılmıyor: {sinif}"


def test_yikici_eylem_confirm_kullanmiyor():
    """⚠️ Üründe `confirm()` YASAK — native diyalog Electron penceresini
    kilitler ve otomatik ölçümü asar. Bağlantıyı kesme iki adımlı tıktır."""
    assert "confirm(" not in PANEL_KOD, "panelde confirm() çağrısı var"
    assert "dataset.onay" in PANEL_KOD, "yıkıcı eylemde onay adımı yok"


def test_kullanilan_yardimci_siniflar_tanimli():
    """Panelin ürettiği sınıfların CSS karşılığı olmalı.

    Tanımsız sınıf **sessizdir**: markup doğru, görünüm bozuk — tam olarak
    bu turda bir kez yaşandı.
    """
    for sinif in ("ak-dugmeler", "ak-uyari", "ak-mesaj"):
        assert re.search(r"\." + sinif + r"\s*[,{]", HQ_CSS), \
            f"{sinif} CSS'te tanımlı değil"
