"""YEDEKLEME paneli — arayüz kapıları ( FAZ 4B).

Panelin parçaları **birbirine bağlıdır** ve biri eksik kalırsa kusur SESSİZDİR
(GOOGLE panelinin aynı kapı dosyasının dersi):

① Menü girdisi (`intro-sequences.js`) — yoksa panele **ulaşılamaz** (TAM BOY modu
   tam böyle ölmüştü: kodu vardı, menü girdisi yoktu).
② 11-13 : panel HQ'dan **YEDEK sekmesine** çıktı. `_HQ_PANELS`'te artık YOK; menü
   girdisi `switchHqTab('yedekleme')` → `switchTab('yedek')` ile sekmeye yönlenir.
③ Sekme kaydı (`tab-nav.js`) — sekme listesinde yoksa düğme hiçbir şey göstermez;
   sekme açılınca panel TAZELENİR.
④ Markup kabı (`index.html` `#yedek-kok`) + script etiketi — JS kabı id ile arar.
⑤ Yetki bayrağı (`tab-nav.js`) — panel Pro; bayrak yazılmazsa girdi hiç çizilmez.

Ayrıca iki üründe-kanıtlanmış kural: `confirm()` KULLANILMAZ (native diyalog
Electron penceresini kilitler) ve kademe koşulu **fail-closed** (`=== true`).
"""

import re
from pathlib import Path

KOK = Path(__file__).resolve().parents[2] / "frontend"
INDEX = (KOK / "index.html").read_text(encoding="utf-8")
HQ_CSS = (KOK / "css" / "hq.css").read_text(encoding="utf-8")
INTRO = (KOK / "js" / "intro-sequences.js").read_text(encoding="utf-8")
PANEL_JS = (KOK / "js" / "yedekleme.js").read_text(encoding="utf-8")
TAB_NAV = (KOK / "js" / "tab-nav.js").read_text(encoding="utf-8")
PRELOAD = (KOK.parent / "electron" / "preload.js").read_text(encoding="utf-8")


def _kodu(kaynak: str) -> str:
    """Yorumları söker.

    🪤 2026-09-14'te ÜÇ KEZ aynı tuzağa düşüldü: düz metin taraması bir kuralı
    *anlatan* yorumu kuralın **ihlali** sanıyor (`confirm()` KULLANILMAZ diyen
    yorum, `confirm(` aranınca eşleşir). Yasak arayan her kapı bu yardımcıyı
    kullanmalı.
    """
    kaynak = re.sub(r"/\*.*?\*/", "", kaynak, flags=re.S)
    return re.sub(r"(?m)^\s*//.*$", "", kaynak)


# ── ① Menü girdisi ───────────────────────────────────────────────────────────

def test_menude_girdi_var():
    """⚠️ 2026-09-19: ham metin araması DEVREDİLDİ — `HQ_MENU` çeviri anahtarı
    taşıyor (FAZ 3 · Dalga 2). Bkz. `yardim.menu_adi`."""
    from yardim import menu_adi

    assert "id:'yedekleme'" in INTRO, "menü girdisi yok — panele ULAŞILAMAZ"
    for dil in ("tr", "en"):
        assert menu_adi("yedekleme", dil).strip(), f"{dil}: menü adı boş"


def test_menu_kosulu_FAIL_CLOSED():
    """`!== false` yazılsaydı açılışta lisans fetch'i sürerken (ya da kilit ekranı
    yüzünden 401 alınmışken) girdi çizilir, Free kullanıcı panele girip 403 yerdi."""
    m = re.search(r"id:'yedekleme'.*?kosul:function\(\)\{\s*return ([^;]+);", INTRO, re.S)
    assert m, "kademe koşulu yok — panel herkese çizilir"
    assert m.group(1).strip() == "window._yukiYedekOk === true", m.group(1)


def test_menude_ayni_ad_iki_kez_gecmiyor():
    """HQ'nun iki özdeş 'Sistem' dersi: menü panelleri ve ayar kategorileri aynı
    ad uzayını paylaşır; çakışmayı hiçbir test değil, yalnız ekran görüntüsü
    yakalamıştı — artık mekanik.

    ⚠️ 2026-09-19: ölçü ham metinden ANAHTARA taşındı (FAZ 3 · Dalga 2). Adın
    kendisinin menüde tekil olması artık iki dilde birden ölçülüyor ve o ölçüm
    tek yerde duruyor: `test_hq_sistem_kapisi.py::
    test_hq_menusunde_AYNI_AD_iki_kez_gecmiyor`. Burada kalan iddia daha dar
    ama bu dosyanın konusu: yedekleme girdisi menüye İKİ KEZ eklenmiş olmasın.
    """
    from yardim import menu_anahtari

    anahtar = menu_anahtari("yedekleme")
    assert INTRO.count(f"etiket:'{anahtar}'") == 1, (
        f"'{anahtar}' menüde birden çok kez geçiyor"
    )


# ── ② Panel listesi ──────────────────────────────────────────────────────────

def test_HQ_PANELS_listesinde_DEGIL_menu_sekmeye_yonlenir():
    """11-13: panel ayrı sekme. `_HQ_PANELS`'te kalsaydı HQ boş bir panele geçerdi."""
    m = re.search(r"_HQ_PANELS\s*=\s*\[(.*?)\]", INTRO, re.S)
    assert m and "'yedekleme'" not in m.group(1), "yedekleme hâlâ HQ paneli"
    kod = _kodu(INTRO)
    assert re.search(r"if\(name==='yedekleme'\)\{[^}]*switchTab\('yedek'\);\s*return;", kod), \
        "HQ menüsündeki Yedekleme girdisi sekmeye gitmiyor"


def test_sekme_acilinca_TAZELENIR():
    """`_loaded` bayrağıyla bir kez yüklenip bırakılsaydı kullanıcı bayat bir
    'son yedekleme' tarihi görürdü — tur arka planda koşuyor olabilir."""
    kod = _kodu(TAB_NAV)
    assert re.search(r"tab === 'yedek'\)\s*\{[^}]*window\.yedeklemePanelAc\(\)", kod), "sekme açılınca tazelenmiyor"
    assert "_yedekInited" not in kod and "_loaded.yedekleme" not in _kodu(INTRO), "panel bir kez yüklenip bırakılıyor"


# ── ③ Açılış kuralı ──────────────────────────────────────────────────────────

def test_sekme_KAYITLI():
    """Sekme düğmesi + kap + tab-nav listesi: biri eksikse düğme bir şey göstermez."""
    assert 'id="tab-btn-yedek"' in INDEX and 'id="tab-yedek"' in INDEX
    assert re.search(r"\{ ad: 'yedek', panel: yedekEl, dugme: btnYedek \}", TAB_NAV), "tab-nav listesinde yok"


def test_panelin_kullandigi_siniflar_css_te_TANIMLI():
    """Google panelinin dersi: sınıflar CSS'te yoksa panel çizilir ama öbür
    panellere hiç benzemez (canlı turda görüldü, testler yeşilken)."""
    # ⚠️ İki kez düzeltildi, ikisi de mutasyonla ölçülerek:
    #   ① düz substring: `.y-kaynak` metni `.y-kaynak-ad` kuralında da geçiyor
    #   ② sınır bakışı: `.y-kaynak .y-sil {` kuralı da eşleşiyordu
    # Aranan şey "sınıf bir yerlerde ANILMIŞ mı" değil, **kendi kuralını TANIMLIYOR
    # mu**: seçici listesinin bir üyesi olarak `{` ya da `,` ile bitmeli.
    # 📏 Statik metnin tavanı burası; kuralın gerçekten *çizdiğini*
    #    `scratchpad/yedekleme-panel-canli-test.py` hesaplanmış stilden ölçer.
    for sinif in (".y-liste", ".y-kaynak", ".y-etiket", ".alan.alan-satir", ".girdi.girdi-dar"):
        desen = r"(?m)^[^{}\n]*" + re.escape(sinif) + r"\s*[,{]"
        assert re.search(desen, HQ_CSS), f"{sinif} kendi kuralını tanımlamıyor"


# ── ④ Markup + script ────────────────────────────────────────────────────────

def test_markup_kabi_ve_script_var():
    assert 'id="yedek-kok"' in INDEX, "kap yok — getElementById null döner"
    assert 'id="hq-panel-yedekleme"' not in INDEX, "eski HQ kabı kaldı — iki kap, iki çizim"
    assert re.search(r'<script src="/ui/js/yedekleme\.js\?v=\d+">', INDEX), "script etiketi yok"


# ── ⑤ Yetki bayrağı ──────────────────────────────────────────────────────────

def test_confirm_KULLANILMIYOR():
    """Native diyalog Electron penceresini kilitler ve otomatik ölçümü asar."""
    assert "confirm(" not in _kodu(PANEL_JS)


def test_satir_ici_stil_YOK():
    """Panel tasarım sistemine oturur; satır içi `display:grid;gap` ilk Google
    panelinde düğmeleri dikey kutulara çevirmişti (canlı turda görüldü)."""
    kod = _kodu(PANEL_JS)
    assert "style=\"" not in kod and "style='" not in kod


def test_native_secici_YOKSA_metin_alanina_dusuyor():
    """Tarayıcıda `yukiDosya` tanımsızdır. Düğmeyi yine de çizmek, basınca hiçbir
    şey olmayan bir düğme demekti ('kapıya bakan arayüz' kuralı)."""
    kod = _kodu(PANEL_JS)
    assert "window.yukiDosya" in kod
    # ⚠️ `"y-ekle-yol" in kod` YETMEZ: id olay bağlama tarafında da geçiyor, yani
    # ÇİZİM kaldırılsa bile test yeşil kalırdı (mutasyonla ölçüldü). Ölçülen şey
    # ternary'nin YEDEK kolunun gerçekten bir metin alanı + düğme çizmesi.
    m = re.search(r"var secici = window\.yukiDosya(.*?);\n", kod, re.S)
    assert m, "klasör seçici dalı bulunamadı — desen değiştiyse test güncellensin"
    yedek = m.group(1).split(":", 1)[-1]
    assert 'id="y-yol"' in yedek and 'id="y-ekle-yol"' in yedek, \
        "tarayıcıda klasör eklenemez — yedek kol metin alanı çizmiyor"


def test_preload_klasor_secicisi_expose_ediyor():
    assert "yukiDosya" in PRELOAD and "dosya:klasor-sec" in PRELOAD


def test_preload_DELTA_ile_tasinabilir():
    """🔴  kısıtı: bir sonraki sürüm `shell_id` değiştirmemeli. Klasör
    seçicisi `onyukleme.js`'e yazılsaydı yalnız TAM PAKETLE giderdi; `preload.js`
    delta yüküyle taşınır ve bu mekanik olarak doğrulanır."""
    import sys
    sys.path.insert(0, str(KOK.parent / "scripts"))
    import importlib.util
    spec = importlib.util.spec_from_file_location("up", KOK.parent / "scripts" / "update_payload.py")
    up = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(up)
    assert "preload.js" not in up.ELECTRON_YASAK
    yollar = [a for _, a in up._yuk_dosyalari()]
    assert "electron/preload.js" in yollar, "klasör seçicisi delta ile müşteriye gitmiyor"
    assert "frontend/js/yedekleme.js" in yollar


# ── Kullanıcıya söylenenler ──────────────────────────────────────────────────

def test_sirlarin_yedege_girmedigi_SOYLENIYOR():
    """Sessiz güvenlik kararı, kullanıcıyı geri yüklerken anahtarını ararken bırakır. Panel bunu açıkça yazar.

    ⚠️ Eski ölçü (`"API anahtarın" in PANEL_JS`) bir YORUM satırı + anahtar adıyla yeşil yanıyordu, ekrandaki
    cümleyi hiç ölçmüyordu. Gerçek ölçü `test_yedekleme_panel.py::test_sirlarin_yedege_girmedigi_EKRANDA_*`
    (panel çizilir, cümle iki dilde okunur, sırlar motorda dışlanıyor). Burada yalnız bağ: anahtar KOD içinde."""
    assert "'yedek.anahtar-girmez'" in _kodu(PANEL_JS), "sır cümlesi çizilmiyor (yorumda ya da silinmiş)"


def test_atlanan_buyuk_dosyalar_RAPORLANIYOR():
    """Sessizce atlamak 'yedeğim var' sanan kullanıcı üretir."""
    assert "buyuk_atlandi" in PANEL_JS


def test_baglanti_yoksa_KULLANICI_google_paneline_yollaniyor():
    """11-13: panel YEDEK sekmesinde → önce HQ sekmesi, hedef panel `_hqHedefPanel` ile."""
    kod = _kodu(PANEL_JS)
    assert re.search(r"window\._hqHedefPanel = 'google';\s*if \(typeof window\.switchTab === 'function'\) window\.switchTab\('hq'\)", kod)
