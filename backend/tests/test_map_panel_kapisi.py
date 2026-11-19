"""MAP panosu — arayüz kapıları (Dalga 3 kalanı, 2026-09-18).

Panelin parçaları birbirine bağlı; biri eksikse kusur SESSİZDİR:

① Sekme düğmesi (`index.html`) — yoksa panele ulaşılamaz
② Sekme mantığı (`tab-nav.js`) — `sekmeAdi` + eleman referansı + liste kaydı
③ Kademe kapısı — Free `switchTab('map')` derse sohbete dönmeli
④ Yetki bayrağı — `features.map_panel`; yanlış alandan okunursa Pro müşteri
   satın aldığını göremez (`multi_character` dersi)
⑤ Markup + 167 DOM kancası — DOM sözleşmesi: eksik kanca hata vermez,
   özellik sessizce çalışmaz
⑥ Kütüphaneler SELF-HOST — kişiselde unpkg.com CDN'indendi; offline SKU'da
   harita hiç açılmaz ve müşterinin IP'si üçüncü tarafa görünürdü
"""
import re
from pathlib import Path

KOK = Path(__file__).resolve().parents[2] / "frontend"
INDEX = (KOK / "index.html").read_text(encoding="utf-8")
TAB_NAV = (KOK / "js" / "tab-nav.js").read_text(encoding="utf-8")
ENGINE = (KOK / "js" / "map-engine.js").read_text(encoding="utf-8")
HUD_CSS = (KOK / "css" / "map-hud.css").read_text(encoding="utf-8")


def _kodu(kaynak: str) -> str:
    kaynak = re.sub(r"/\*.*?\*/", "", kaynak, flags=re.S)
    return re.sub(r"(?m)^\s*//.*$", "", kaynak)


# ── ① Sekme düğmesi ──────────────────────────────────────────────────────────

def test_sekme_dugmesi_var():
    assert 'id="tab-btn-map"' in INDEX, "sekme düğmesi yok — panele ULAŞILAMAZ"


def test_markup_kabi_var():
    assert 'id="tab-map"' in INDEX


def test_dom_kancalari_TAM():
    """167 kanca ölçülmüştü; motor bunları id ile arar.

    🔁 2026-10-04 ("HARİTA ÖNCE"): 167 → 139. Düşüş BİLEREK: 7 kart +
    sağ panel (Yuki portresi, YUKI KANALI, GÖREV KONTROL, SİSTEM, SİNYAL,
    PİYASA), mod çubuğu, akan şerit ve radar kalktı; yerine şerit + çekmece
    + GÜNDEM kimlikleri geldi. Taban sayısı tek başına zayıf bir bekçiydi —
    asıl sözleşme aşağıdaki ikinci kapı: motorun ARADIĞI her kimlik markup'ta."""
    m = re.search(r'<div id="tab-map".*?(?=<div id="tab-yedek")', INDEX, re.S)
    assert m, "tab-map bloğu bulunamadı"
    kanca = set(re.findall(r'id="([a-z0-9-]+)"', m.group(0)))
    assert len(kanca) >= 135, f"kanca sayısı düştü: {len(kanca)} (beklenen ≥135)"
    for kritik in ("leaflet-map", "map-3d-container", "map-serit", "map-katman-cekmece",
                   "map-gundem", "map-news-list", "map-layer-mgr"):
        assert kritik in kanca, f"kritik kanca eksik: {kritik}"


def test_motorun_aradigi_her_kimlik_MARKUPTA():
    """DOM sözleşmesinin kuralı: eksik kanca HATA VERMEZ, özellik sessizce
    çalışmaz. Kart silinirken ona yazan satır kalırsa ya da yeni yüzeyin
    kimliği yazım hatasıyla girerse bu kapı yakalar (sabit dizgeyle
    `getElementById('…')` çağrıları; dinamik `'map-layer-' + key` hariç —
    onları 18 katman satırı karşılıyor, aşağıda ayrıca sayılıyor)."""
    kimlikler = set(re.findall(r'id="([^"]+)"', INDEX))
    for dosya in ("map-engine.js", "map-hud.js"):
        kod = _kodu((KOK / "js" / dosya).read_text(encoding="utf-8"))
        aranan = set(re.findall(r"getElementById\('([^'$]+)'\)", kod))
        eksik = sorted(a for a in aranan if a not in kimlikler)
        assert not eksik, f"{dosya} markup'ta olmayan kimlik arıyor: {eksik}"
    m = re.search(r"const _layerActive = \{([^}]*)\}", _kodu((KOK / "js" / "map-engine.js").read_text(encoding="utf-8")))
    assert m, "_layerActive bulunamadı"
    katmanlar = re.findall(r"(\w+):\s*false", m.group(1))
    eksik = [k for k in katmanlar if f'id="map-layer-{k}"' not in INDEX]
    assert not eksik, f"katman satırı yok (çekmeceden ulaşılamaz): {eksik}"


# ── ② Sekme mantığı ──────────────────────────────────────────────────────────

def test_sekme_adi_taniniyor():
    kod = _kodu(TAB_NAV)
    assert "'map'" in kod and "sekmeAdi" in kod
    assert re.search(r"hedef === 'map'", kod), "sekmeAdi 'map'i tanımıyor"


def test_eleman_referansi_ve_liste_kaydi():
    kod = _kodu(TAB_NAV)
    assert "getElementById('tab-map')" in kod, "panel elemanı hiç alınmıyor"
    assert "getElementById('tab-btn-map')" in kod, "düğme elemanı hiç alınmıyor"
    assert re.search(r"\{\s*ad:\s*'map'", kod), \
        "sekme listesinde yok — geçişte gizlenmez/gösterilmez"


# ── ③ Kademe kapısı ──────────────────────────────────────────────────────────

def test_kutuphaneler_SELF_HOST():
    """🔴 Kişiselde unpkg.com CDN'indendi: offline SKU'da harita hiç açılmaz,
    ayrıca müşterinin IP'si üçüncü tarafa görünür."""
    for kutuphane in ("leaflet-1.9.4/leaflet.js", "markercluster-1.5.3/leaflet.markercluster.js",
                      "maplibre-gl-4/maplibre-gl.js", "leaflet-1.9.4/leaflet.css"):
        assert f"/ui/vendor/{kutuphane}" in INDEX, f"self-host değil: {kutuphane}"
    # 🪤 HTML YORUMLARI SÖKÜLÜR: kuralı ANLATAN yorum ("kişiselde unpkg.com
    # CDN'indendi") ihlal sanılıyordu — bu turda yedinci kez aynı tuzak.
    govde = re.sub(r"<!--.*?-->", "", INDEX, flags=re.S)
    assert "unpkg.com" not in govde, "CDN bağımlılığı geride kalmış"
    assert "cdn.jsdelivr" not in govde and "cdnjs.cloudflare" not in govde


def test_kutuphane_dosyalari_DISKTE():
    vendor = KOK / "vendor"
    for yol in ("leaflet-1.9.4/leaflet.js", "leaflet-1.9.4/leaflet.css",
                "markercluster-1.5.3/leaflet.markercluster.js",
                "maplibre-gl-4/maplibre-gl.js"):
        assert (vendor / yol).exists(), f"dosya yok: {yol}"


def test_leaflet_gorselleri_VAR():
    """`leaflet.css` `images/`ten 3 görsel ister; eksikse işaretçiler KIRIK görünür."""
    img = KOK / "vendor" / "leaflet-1.9.4" / "images"
    for g in ("marker-icon.png", "marker-shadow.png", "layers.png"):
        assert (img / g).exists(), f"leaflet görseli eksik: {g}"


def test_kutuphaneler_MOTORDAN_ONCE():
    """`map-engine.js` açılışta `L`/`maplibregl` arar; sonra yüklenirse harita çizilmez."""
    assert INDEX.index("vendor/leaflet-1.9.4/leaflet.js") < INDEX.index("js/map-engine.js")
    assert INDEX.index("vendor/maplibre-gl-4/maplibre-gl.js") < INDEX.index("js/map-engine.js")


# ── ⑤ Çeviri disiplini ───────────────────────────────────────────────────────

def test_CSS_URUN_TOKENLERINE_bagli():
    """Değerler kopyalansaydı harita ürünün üç temasından yalnız birinde doğru
    görünür, açık temada okunmaz olurdu."""
    # 10-04 göz tur 2: "--altin" → "--mor-ink". Haritada altın kalmadı (altın ürünün
    # nadir vurgusu; seçim/eylem mor) — kapı artık o kararı korur.
    for urun_tokeni in ("--bg-base", "--mor-ink", "--cyan", "--text"):
        assert f"var({urun_tokeni})" in HUD_CSS, f"ürün tokeni kullanılmıyor: {urun_tokeni}"
    for kisisel_token in ("var(--c-gold)", "var(--surface-0)", "var(--c-ink)"):
        assert kisisel_token not in HUD_CSS, f"kişisel token geride kalmış: {kisisel_token}"


def test_tasinmayan_uclara_BAG_KALMADI():
    """Taşınmayan uçlara bağlı kod kalırsa açılışta 'is not defined' patlar."""
    kod = _kodu(ENGINE)
    for iz in ("intelBrief", "mcRunAgent", "updateSysVitals", "/api/intel/", "/api/metrics"):
        assert iz not in kod, f"taşınmayan uca bağ kaldı: {iz}"
