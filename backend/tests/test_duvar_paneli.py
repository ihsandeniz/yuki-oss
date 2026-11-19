"""HQ › DUVAR · ÖNİZLEME ÖNCE — panel bekçileri (2026-09-27).

Kişisel 54de771 ürüne yeniden yazılırken ölçülen dört kusurun kapısı:
  ① Metin testinin KÖR NOKTASI: `yardim.yorumsuz`'un `/\\*.*?\\*/` regex'i `accept="image/…"`
     jokerindeki eğik çizgi+yıldızı yorum başı sanıp dosyanın ~%40'ını siliyordu → panelin
     yükleme/silme kodu hiçbir metin testine görünmüyordu (ham TR 'Silmek için tekrar tıkla'
     yeşil geçiyordu). Kök: dosyada yorum dışında `/*` dizisi olmamalı.
  ② Panel CSS'i üründe TANIMSIZ token kullanıyordu (`--border-card` …) → kenarlar çizilmiyordu.
  ③ Ayar kaydı sunucu cevabına bakmıyordu (422'de ekranda yanlış değer kalıyordu).
  ④ Liste alınamazsa panel sonsuza dek "YÜKLENİYOR" diyordu.
"""
from __future__ import annotations

import re
from pathlib import Path

from yardim import yorumsuz

KOK = Path(__file__).resolve().parents[2]

DUVAR_JS = (KOK / "frontend" / "js" / "duvar.js").read_text(encoding="utf-8")
DUVAR_CSS = (KOK / "frontend" / "css" / "duvar.css").read_text(encoding="utf-8")


def test_yorum_disinda_yorum_basi_dizisi_YOK():
    """① Yorumları kabaca sök, kalan kodda `/*` geçmemeli — geçerse sıyırıcı oradan
    itibaren kodu yutar ve metin testleri kör olur."""
    # ⚠️ Aynı regex'le önce yorum SÖKÜLÜP sonra `/*` aranırsa test hiç kırmızı yanmaz:
    # string içindeki `/*` sökme sırasında "yorum" sayılıp silinir. Yorum başı ancak
    # satır başında ya da boşluktan sonra gelir; harf/tırnak/eşittir ardından gelen `/*`
    # bir string ya da ifadenin parçasıdır (mutasyonla doğrulandı: `image/*` → kırmızı).
    bul = re.search(r"[\w'\"=,]/\*", DUVAR_JS)
    assert not bul, f"kodda yorum olmayan `/*`: …{DUVAR_JS[bul.start()-20:bul.end()+10]!r}…" if bul else ""


def test_yorumsuz_hali_paneli_TAMAMEN_goruyor():
    y = yorumsuz(DUVAR_JS)
    for ad in ("function panelCiz", "function _panelBagla", "async function _yukleHepsi",
               "async function ayarKaydet", "window.duvarPanelCiz"):
        assert ad in y, f"{ad} yorumsuz hâlde görünmüyor — sıyırıcı kodu yutuyor"


def test_panel_css_TANIMSIZ_token_kullanmiyor():
    """② Ürün token'ları `tokens.css`'te; kişiselin adları üründe yok."""
    kod = re.sub(r"/\*.*?\*/", "", DUVAR_CSS, flags=re.S)
    for ad in ("--border-card", "--surface-1", "--scrim-2", "--c-ink", "--c-cyan", "--c-gold", "--c-err", "--c-ok"):
        assert f"var({ad}" not in kod, f"tanımsız token: {ad}"


def test_ayar_kaydi_sunucu_cevabina_bakiyor():
    """③ `r.ok` değilse eski ayar geri gelir ve sebep yazılır."""
    m = re.search(r"async function ayarKaydet\(yeni\) \{(.*?)\n  \}", DUVAR_JS, re.S)
    assert m, "ayarKaydet bulunamadı"
    govde = m.group(1)
    assert "if (!r.ok)" in govde and "_ayar = eski" in govde


def test_liste_alinamazsa_tekrar_dene():
    """④ `_ayar` yoksa sessiz return değil, tekrar dene düğmesi."""
    m = re.search(r"function panelCiz\(\) \{(.*?)\n    const mod", DUVAR_JS, re.S)
    assert m and "duvar.okunamadi" in m.group(1) and "dv-tekrar" in m.group(1)


def test_silme_ve_onay_tarayici_diyalogu_KULLANMIYOR():
    y = yorumsuz(DUVAR_JS)
    assert "confirm(" not in y and "prompt(" not in y
    assert "data-duvar-sil-evet" in y, "satır içi silme onayı yok"


def test_hq_menusundeki_her_simge_sozlukte_var():
    """⑤ Sözlükte olmayan simge adı menüye DÜZ METİN olarak basılıyordu ("cihazlar" yazısı
    etiketin üstüne biniyordu). Her `ikon:'…'` `_PANEL_IKONLARI`'nda tanımlı olmalı."""
    js = (KOK / "frontend" / "js" / "intro-sequences.js").read_text(encoding="utf-8")
    sozluk = re.search(r"var _PANEL_IKONLARI = \{(.*?)\n  \};", js, re.S)
    assert sozluk, "_PANEL_IKONLARI bulunamadı"
    tanimli = set(re.findall(r"^\s*'([a-z]+)':", sozluk.group(1), re.M))
    eksik = sorted(set(re.findall(r"ikon:'([a-z]+)'", js)) - tanimli)
    assert not eksik, f"sözlükte olmayan menü simgesi: {eksik}"
