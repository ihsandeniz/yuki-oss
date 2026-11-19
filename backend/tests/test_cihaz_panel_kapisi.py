"""CİHAZLAR paneli — arayüz kapıları (2026-09-18).

Panelin parçaları **birbirine bağlıdır** ve biri eksik kalırsa kusur SESSİZDİR
(yedekleme/GOOGLE panellerinin dersi):

① Menü girdisi (`intro-sequences.js`) — yoksa panele **ulaşılamaz**
② `_HQ_PANELS` üyeliği — yoksa panel geçişinde gizlenmez/gösterilmez
③ Açılış karşı-kuralı (`hq.css`) — yoksa içerik çizilir, **ekran boş** kalır
④ Markup kabı + script etiketi (`index.html`) — JS kabı id ile arar
⑤ Yetki bayrağı (`tab-nav.js`) — panel Ultra; bayrak yoksa girdi hiç çizilmez

Ayrıca bu panele özel iki kural:
· QR **yerinde** üretilir — dış istek/resim servisi YOK (kod üçüncü tarafa gitmez)
· Python `qrcode` paketi EKLENMEDİ — `shell_id` değişir, müşteri 457 MB indirirdi
"""
import re
from pathlib import Path

KOK = Path(__file__).resolve().parents[2] / "frontend"
INDEX = (KOK / "index.html").read_text(encoding="utf-8")
HQ_CSS = (KOK / "css" / "hq.css").read_text(encoding="utf-8")
INTRO = (KOK / "js" / "intro-sequences.js").read_text(encoding="utf-8")
PANEL_JS = (KOK / "js" / "cihazlar.js").read_text(encoding="utf-8")
TAB_NAV = (KOK / "js" / "tab-nav.js").read_text(encoding="utf-8")
QR_JS = (KOK / "vendor" / "qr-uret.js").read_text(encoding="utf-8")


def _kodu(kaynak: str) -> str:
    """Yorumları söker — kuralı ANLATAN yorum, kuralın ihlali sanılmasın.

    🪤 2026-09-14'te üç kez bu tuzağa düşüldü: `confirm() KULLANILMAZ` diyen
    yorum, `confirm(` aranınca eşleşiyordu.
    """
    kaynak = re.sub(r"/\*.*?\*/", "", kaynak, flags=re.S)
    return re.sub(r"(?m)^\s*//.*$", "", kaynak)


# ── ① Menü girdisi ───────────────────────────────────────────────────────────

def test_menude_girdi_var():
    """⚠️ 2026-09-19: `etiket:'Cihazlar'` ham metin araması DEVREDİLDİ —
    `HQ_MENU` artık çeviri anahtarı taşıyor (FAZ 3 · Dalga 2). İddia zayıflamadı:
    girdinin varlığı + etiketin anahtar olması + adın İKİ DİLDE karşılığı."""
    from yardim import menu_adi

    assert "id:'cihazlar'" in _kodu(INTRO), "menü girdisi yok — panele ULAŞILAMAZ"
    for dil in ("tr", "en"):
        assert menu_adi("cihazlar", dil).strip(), f"{dil}: menü adı boş"


def test_menu_kosulu_FAIL_CLOSED():
    """`=== true` şart: yetki BİLİNMEZKEN girdi çizilmemeli."""
    kod = _kodu(INTRO)
    m = re.search(r"id:'cihazlar'.*?\}\}", kod, re.S)
    assert m, "menü girdisi bulunamadı"
    assert "_yukiCihazOk === true" in m.group(0), \
        "koşul fail-closed değil (`=== true` olmalı)"


def test_panel_acilis_kancasi_var():
    kod = _kodu(INTRO)
    assert "cihazlarPanelAc" in kod, "panel açılınca hiçbir şey çizilmez"


# ── ② _HQ_PANELS üyeliği ─────────────────────────────────────────────────────

def test_hq_panels_listesinde():
    m = re.search(r"_HQ_PANELS\s*=\s*\[(.*?)\]", INTRO, re.S)
    assert m and "'cihazlar'" in m.group(1), \
        "_HQ_PANELS'te yok — panel geçişinde gizlenmez/gösterilmez"


# ── ③ Açılış karşı-kuralı ────────────────────────────────────────────────────

def test_css_acilis_kurali():
    """Bu kural olmadan panel çizilir ama EKRAN BOŞ görünür (duvar panelinde ölçüldü)."""
    assert re.search(
        r'#tab-hq\[data-hq="cihazlar"\]\s*#hq-panel-cihazlar\s*\{[^}]*display:\s*flex',
        HQ_CSS,
    ), "hq.css açılış karşı-kuralı yok"


# ── ④ Markup kabı + script etiketleri ────────────────────────────────────────

def test_markup_kabi_var():
    assert 'id="hq-panel-cihazlar"' in INDEX, "JS'in aradığı kap yok"


def test_script_etiketleri_var():
    assert "js/cihazlar.js" in INDEX, "panel scripti yüklenmiyor"
    assert "vendor/qr-uret.js" in INDEX, "QR üreteci yüklenmiyor"


def test_qr_scripti_panelden_ONCE():
    """`cihazlar.js` açılışta `QRUret`i arar; sonra yüklenirse QR çizilmez.

    🪤 `INDEX.index("js/cihazlar.js")` YANLIŞ ölçer — o metin markup yorumunda
    da geçiyor ("içeriği js/cihazlar.js çizer") ve `.index()` ilk geçişi alır.
    Aranan şey <script> ETİKETİ; ilk yazımda test bu yüzden yanlış kırmızı verdi.
    """
    qr = INDEX.index('src="/ui/vendor/qr-uret.js')
    panel = INDEX.index('src="/ui/js/cihazlar.js')
    assert qr < panel, "QR üreteci panelden SONRA yükleniyor — QR çizilmez"


# ── ⑤ Yetki bayrağı ──────────────────────────────────────────────────────────

def test_confirm_KULLANILMIYOR():
    """Native diyalog Electron penceresini kilitler — ürünün kanıtlanmış kuralı."""
    assert "confirm(" not in _kodu(PANEL_JS)


def test_QR_DIS_ISTEK_YOK():
    """QR yerinde üretilir; kod üçüncü bir tarafa gitmemeli."""
    kod = _kodu(PANEL_JS) + _kodu(QR_JS)
    for yasak in ("http://", "https://", "fetch('http", "chart.googleapis", "qrserver"):
        if yasak in ("http://", "https://"):
            # xmlns URL'i SVG şemasıdır, istek üretmez — onu ayıkla
            temiz = kod.replace("http://www.w3.org/2000/svg", "")
            assert yasak not in temiz, f"QR yolunda dış adres var: {yasak}"
        else:
            assert yasak not in kod, f"QR dış servise gidiyor: {yasak}"


def test_ag_uyarisi_panelde_GOSTERILIYOR():
    """HOST=127.0.0.1 ise kullanıcı bunu GÖRMELİ — sessizce çalışmaz görünmemeli.

    ⚠️ 2026-10-01: eski hâli yalnız `"uyari" in kod` arıyordu — o kelime `alan-uyari` sınıf adında da geçtiği için ağ
    uyarısı silinse bile kırmızı yanmazdı. Şimdi panelin GERÇEK dosyası `node` ile koşar: ağ kapalıyken çizilen
    markup'ta uyarı cümlesi var mı, 'Cihaz ekle' pasif mi (davranışın tamamı `test_cihaz_rafi.py`'de)."""
    from cihaz_panel_kosum import AG_KAPALI, kos, yanit
    assert "dinleniyor" in _kodu(PANEL_JS), "ağın GERÇEKTEN dinlenip dinlenmediği hiç okunmuyor"
    s = kos({"yanit": yanit(ag=AG_KAPALI), "adimlar": [{"op": "ac"}]})
    h = s["adimlar"][-1]["html"]
    assert "cihaz.ag-kapali-baslik" in h, "ağ kapalıyken kullanıcıya sebep söylenmiyor"
    assert "disabled" in re.search(r'<button[^>]*data-cz="ekle"[^>]*>', h).group(0), "ağ kapalıyken 'Cihaz ekle' aktif"


def test_python_qrcode_EKLENMEDI():
    """`shell_id` koruması: yeni Python bağımlılığı müşteriyi 457 MB indirmeye zorlar."""
    req = (Path(__file__).resolve().parents[1] / "requirements-product.txt")
    icerik = req.read_text(encoding="utf-8").lower()
    assert "qrcode" not in icerik, \
        "qrcode paketi eklenmiş — shell_id değişir, delta güncelleme kırılır"
