"""Kişiselle birebir — yazı çubuğu + Odaklı Halka SİTELER, YAPI kapıları (2026-10-11).

Sunucusuz. Tarayıcı ölçümleri: `frontend/tests/test_birebir_konsol.py` ·
`frontend/tests/test_halka_siteler.py` (ikinci port).

geliştirici kararı (10-11): ürün sohbet çubuğu kişiseldeki Halka Konsolu ile birebir olsun.
  1. Mikrofonun çevresinde boşta da ince kesikli süs halkası (kayıtta seviye aynen).
  2. Yazı çubuğunun altı ince "◈ model · dil · küçült ⌄" satırı; EKRAN/PANO/ARA/AKTAR
     çipleri ⋯ menüsüne — hiçbir işlev kaybolmaz, kademe kapıları menüde sürer.
  3. Odaklı Halka'ya SİTELER: müşteri kendi kısayollarını ekler/siler, yerel saklanır,
     yalnız http/https, açılış sistem tarayıcısında (iframe değil).
"""
from __future__ import annotations

import re
from pathlib import Path

KOK = Path(__file__).resolve().parents[2]
FE = KOK / "frontend"
INDEX = (FE / "index.html").read_text(encoding="utf-8")
SOHBET = (FE / "css/sohbet.css").read_text(encoding="utf-8")
SAHNE_CSS = (FE / "modes/sohbet-sahne.css").read_text(encoding="utf-8")
SAHNE_JS = (FE / "modes/sohbet-sahne.js").read_text(encoding="utf-8")
HALKA_JS = (FE / "modes/hud-ring.js").read_text(encoding="utf-8")
SITELER = (FE / "js/halka-siteler.js").read_text(encoding="utf-8")
TR = (FE / "js/diller/tr.js").read_text(encoding="utf-8")
EN = (FE / "js/diller/en.js").read_text(encoding="utf-8")
PRODUCT = (KOK / "PRODUCT.md").read_text(encoding="utf-8")
SW = (FE / "sw.js").read_text(encoding="utf-8")


def _blok(metin: str, bas: str, son: str) -> str:
    i = metin.index(bas)
    return metin[i:metin.index(son, i)]


SATIR = _blok(INDEX, '<div id="hizli-satir"', "<!-- ── PLANNER TAB")
MENU = _blok(INDEX, 'id="input-secondary-btns"', '<input type="file" id="mediaFileInput"')


# ── 1 · mikrofon süs halkası ──────────────────────────────────────────────

def test_mikrofon_bosta_kesikli_halka_cizer():
    m = re.search(r"#mic-container:not\(:has\(#mic-btn\.recording\)\) #mic-level-ring \.ring-bg \{([^}]*)\}", SOHBET)
    assert m, "boştaki halka kuralı (yalnız kayıt DIŞINDA) yok"
    assert "stroke-dasharray" in m.group(1), "boştaki halka kesikli olmalı"
    assert "--mor-ink" in m.group(1), "ürün paleti: mor (altın değil)"


def test_mikrofon_halkasi_bostayken_gizlenmiyor():
    gizle = re.search(r"#mic-container:not\(:has\(#mic-btn\.recording\)\) #mic-level-ring \{[^}]*opacity:\s*0", SOHBET)
    assert not gizle, "boşta halkayı gizleyen eski kural geri gelmiş (geliştirici 10-11 kararı: boşta da görünür)"


def test_kayitta_seviye_halkasi_yerinde():
    assert re.search(r"#mic-level-ring \.ring-level \{[^}]*stroke: var\(--mor-ink\)", SOHBET)
    assert "document.querySelector('#mic-level-ring .ring-level')" in (FE / "js/core.js").read_text(encoding="utf-8"), \
        "seviyeyi çizen core.js kancası"


def test_product_ilke1_istisnasi_tarihli_ve_gerekceli():
    ilke = _blok(PRODUCT, "1. **Ekranda yer kaplayan", "2. **Mor kimliktir")
    assert "2026-10-11" in ilke and "geliştirici" in ilke, "İlke 1 istisnası tarih + karar sahibiyle yazılmalı"
    assert "Gerekçe" in ilke and "kesikli" in ilke


# ── 2 · ince durum satırı + çipler menüde ─────────────────────────────────

def test_durum_satiri_model_dil_kucult_sirasiyla_ve_cipsiz():
    assert "hizli-cip" not in SATIR, "durum satırında çip kalmış"
    # 11-14 (kişiseldeki gibi): model · dil · Hep dinle · küçült
    sira = [SATIR.index(f'id="{k}"') for k in ("hap-model", "hap-dil", "hep-dinle-anahtar", "giris-kucult")]
    assert sira == sorted(sira), "sıra: model · dil · hep dinle · küçült"
    assert SATIR.count('class="hizli-ayrac"') == 3, "aralarında üç ayraç (·)"
    assert 'onclick="toggleAlwaysOn()"' in SATIR and 'role="switch"' in SATIR, "Hep dinle anahtarı asıl işleve bağlı"
    assert 'data-i18n="girdi.kucult-kisa"' in SATIR, "küçült yazısı görünür ve çevrilir"


def test_kaldirilan_ciplerin_islevi_menude():
    for fonk in ("qaScreenshot()", "qaClipboard()", "qaSearch()", "qaExport()"):
        assert f'onclick="{fonk}"' in MENU, f"{fonk} ⋯ menüsünde yok — işlev kaybı"
        assert f'onclick="{fonk}"' not in SATIR


def test_kademe_kapilari_menude_suruyor():
    assert re.search(r'<button id="menu-ekran"[^>]*hidden>', MENU), "ekran öğesi kapalı doğar"
    assert re.search(r'<button id="menu-pano"[^>]*hidden>', MENU), "pano öğesi kapalı doğar"
    assert "goster('menu-ekran', izin('take_screenshot') === true)" in SAHNE_JS
    assert "goster('menu-pano', pano)" in SAHNE_JS
    assert "cip-" not in SAHNE_JS.split("// ════ KISAYOL SATIRI ════", 1)[1].split("Model/dil hapları", 1)[0], \
        "kapı ölü çip kimliğine yazıyor"


def test_aktar_dar_kabukta_da_menude():
    assert not re.search(r"#menu-aktar \{ display: none; \}", SOHBET), \
        "AKTAR'ın tek yolu artık menü — dar kabukta gizlenemez"


def test_durum_dugmeleri_44px_dokunma_alani():
    m = re.search(r"\.hizli-hap::after \{([^}]*)\}", SAHNE_CSS)
    assert m, "dokunma alanını büyüten ::after yok"
    assert "inset-block: calc((26px - var(--hedef)) / 2)" in m.group(1)
    assert "inset-inline: min(0px, calc((100% - var(--hedef)) / 2))" in m.group(1)
    assert re.search(r"\.hizli-hap \{[^}]*height: 26px", SAHNE_CSS), "görsel yükseklik ::after hesabıyla aynı"


def test_durum_satiri_cercevesiz_ince():
    m = re.search(r"\n\.hizli-hap \{([^}]*)\}", SAHNE_CSS)
    assert m and "border: 0" in m.group(1) and "background: transparent" in m.group(1)


# ── 3 · Odaklı Halka SİTELER ─────────────────────────────────────────────

def test_siteler_grubu_menude():
    # 11-14: KARAKTER grubu yalnız birden çok karakter varken (şu an yalnız Yuki)
    assert "const OD_GRUPLAR = ['sekme', ...(CHARS_CW.length > 1 ? ['kar'] : []), 'site'];" in HALKA_JS
    assert '<script src="/ui/js/halka-siteler.js?v=' in INDEX


def test_acilis_sistem_tarayicisinda_iframe_yok():
    assert "iframe" not in re.sub(r"/\*.*?\*/", "", SITELER, flags=re.S), "site deposu iframe kurmamalı"
    assert "window.open(d.url, '_blank', 'noopener,noreferrer')" in SITELER
    od = _blok(HALKA_JS, "// ODAKLI HALKA", "// ③c Dış orbit")
    assert "createElement('iframe')" not in od and "<iframe" not in od


def test_acmadan_once_yeniden_dogrulanir():
    ac = _blok(SITELER, "function ac(adres)", "window.HalkaSiteler")
    assert ac.index("dogrula(adres)") < ac.index("window.open"), "açmadan hemen önce kapı"
    assert "if (!d.ok) return false;" in ac


def test_depodan_okurken_dogrulanir():
    liste = _blok(SITELER, "function liste()", "function _yaz")
    assert "dogrula(s.url)" in liste and "if (!d.ok" in liste, "elle bozulmuş localStorage'daki adres süzülmeli"


def test_yalniz_http_https():
    assert "u.protocol !== 'http:' && u.protocol !== 'https:'" in SITELER
    assert "u.username || u.password" in SITELER


def test_site_metinleri_cevrilir_tr_en():
    anahtarlar = set(re.findall(r"_hrt\('(hudring\.od\.(?:site|ne\.ekle|ne\.tum|ust\.site|ipucu\.site|ipucu\.tikla|grup\.)[^']*)'", HALKA_JS))
    anahtarlar.add("hudring.od.grup.site")
    hatalar = set(re.findall(r"hata: '([a-z]+)'", SITELER))
    assert {"bos", "sema", "gecersiz", "kimlik", "var", "dolu", "kayit", "uzun"} <= hatalar
    anahtarlar |= {f"hudring.od.site.hata.{h}" for h in hatalar}
    for k in sorted(anahtarlar):
        if k.endswith("."):
            continue
        assert f"'{k}':" in TR, f"TR sözlükte yok: {k}"
        assert f"'{k}':" in EN, f"EN sözlükte yok: {k}"


def test_html_kacislanir():
    panel = _blok(HALKA_JS, "function _odPanelHtml()", "function _odPanelAc")
    for alan in ("st.ad", "st.host", "st.url", "st.id"):
        for m in re.finditer(r"\$\{([^}]*" + re.escape(alan) + r"[^}]*)\}", panel):
            assert m.group(1).startswith("_odEsc(") or "_hrt(" in m.group(1), f"kaçışsız: {m.group(0)}"


# ── 3b · SİTELER = Ultra (2026-10-12) ──────────────────────────

def test_kilitliyken_site_grubu_cizilmez_tercih_ezilmez():
    ciz = _blok(HALKA_JS, "function _odCiz()", "function _odMerkezYaz")
    assert "if (_odGrup === 'site' && _siteKilitli())" in ciz
    assert "localStorage.setItem" not in ciz, "kilit kayıtlı grup tercihini ezmemeli"
    assert "document.addEventListener('yuki:entitlements'" in HALKA_JS, "yetki gelince yeniden çizilmeli"


def test_kilit_listeye_dokunmaz():
    # Kapı halka-siteler.js'te değil: depo okuma/yazma kademeye bakmaz → Pro'ya düşen müşterinin listesi kalır
    assert "_yukiPanelOk" not in SITELER and "license" not in SITELER


def test_kilitli_grup_uzerine_gelince_parlamaz():
    css = (FE / "modes/hud-ring.css").read_text(encoding="utf-8")
    assert ".hr-od-grup.hr-od-grup-kilitli:hover { color: rgba(220,232,255,.62); }" in css


def test_sw_cache_version_geri_gitmez():
    # Dalda CACHE_VERSION elle artırılmaz (yayin.py --sw artırır, şef notu); v0.8.3 birleşiminde
    # keyring/UI-F001 v336'yı getirdi, yayın v337 yapar. Kapı: bu işin tabanı v335'in gerisine düşmez.
    n = int(re.search(r"const CACHE_VERSION = 'yuki-v(\d+)';", SW).group(1))
    assert n >= 335, f"CACHE_VERSION geri gitmiş: v{n}"


def test_surum_damgalari_esit():
    asset = re.search(r"const ASSET_V = '(\d+)'", (FE / "modes/chat-modes.js").read_text(encoding="utf-8")).group(1)
    assert f'/ui/modes/chat-modes.js?v={asset}"' in INDEX, "chat-modes ?v= == ASSET_V"
    damga = set()
    for dosya in ("index.html", "mini.html", "planner.html", "sw.js"):
        metin = (FE / dosya).read_text(encoding="utf-8")
        tr = re.findall(r"diller/tr\.js\?v=(\d+)", metin); en = re.findall(r"diller/en\.js\?v=(\d+)", metin)
        assert tr and tr == en, f"sözlük damgası {dosya}: tr {tr} · en {en}"
        damga.update(tr)
    # dört dosyada eşit ve bu işin sözlüğünden (v81) geri değil
    assert len(damga) == 1 and int(damga.pop()) >= 81, "sözlük ?v= dört dosyada eşit olmalı"
