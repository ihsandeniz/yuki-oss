"""HQ sol menüsünde kaybolan panel ya da kategori olamaz.

2026-08-12 (karar D5): iç içe iki menü — üstte 8 sekmelik yatay şerit, AYARLAR'ın
içinde 7 kategorilik ikinci dikey liste — tek sol menüde birleştirildi.

🔴 Bu birleştirmenin doğurduğu YENİ risk: menü artık `intro-sequences.js`
içindeki `HQ_MENU` tablosundan çiziliyor. Yeni bir panel ya da kategori eklenip
o tabloya yazılmazsa, girdi **ULAŞILAMAZ** olur — bu projenin en sık kusur
sınıfı (TAM BOY modu `MODES` listesinde yoktu · `avatar_3d` beyaz listede
değildi · karakter kilidi arayüzden sorulmuyordu). Kod var, yol yok.

Frontend'de bir emniyet var (menüde yeri olmayan kategori son gruba düşer) ama
emniyet sessizdir: kategori yanlış grupta belirir ve kimse fark etmez. Kapı bu
yüzden burada.
"""

from __future__ import annotations

import re
from pathlib import Path

from app.api import settings_api

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
INTRO_JS = FRONTEND / "js" / "intro-sequences.js"
INDEX_HTML = FRONTEND / "index.html"

# AYARLAR paneli menüde KENDİ girdisi olarak durmaz — kategorileri doğrudan
# listelendiği için ayrı bir "AYARLAR" satırı ikinci bir seviye demek olurdu.
MENUDE_OLMAYAN_PANEL = {"ayarlar"}
# 11-13 : HQ menüsünde kalan ama HQ paneli OLMAYAN girdi — switchHqTab onu ayrı sekmeye yollar.
SEKMEYE_YONLENEN = {"yedekleme"}


def _yorumsuz(metin: str, html: bool = False) -> str:
    """Yorumları at.

    Bu dersi bu turda ÜÇ kez düştüm: bir kalıbın geri gelmediğini ölçen test,
    o kalıbı ANLATAN yorumu bulup kırmızı yanıyor. (`test_ozellik_ilani.py`
    aynı tuzağa 2026-08-02'de düşmüştü.)
    """
    if html:
        return re.sub(r"<!--.*?-->", "", metin, flags=re.DOTALL)
    metin = re.sub(r"/\*.*?\*/", "", metin, flags=re.DOTALL)
    return re.sub(r"(?<![:'\"])//[^\n]*", "", metin)


def _js() -> str:
    return _yorumsuz(INTRO_JS.read_text(encoding="utf-8"))


def _html() -> str:
    return _yorumsuz(INDEX_HTML.read_text(encoding="utf-8"), html=True)


def _menu_bloku() -> str:
    m = re.search(r"var HQ_MENU\s*=\s*\[(.*?)\n  \];", _js(), re.DOTALL)
    assert m, "HQ_MENU tablosu bulunamadı (yeniden mi adlandırıldı?)"
    return m.group(1)


def _menu_girdileri(tip: str) -> set[str]:
    return set(re.findall(r"tip:'%s',\s*id:'([^']+)'" % tip, _menu_bloku()))


def _bildirilen_paneller() -> set[str]:
    m = re.search(r"var _HQ_PANELS\s*=\s*\[([^\]]+)\]", _js())
    assert m, "_HQ_PANELS listesi bulunamadı"
    return set(re.findall(r"'([^']+)'", m.group(1)))


def test_her_panelin_menude_yeri_var():
    eksik = _bildirilen_paneller() - _menu_girdileri("panel") - MENUDE_OLMAYAN_PANEL
    assert not eksik, (
        f"menüde yeri olmayan panel(ler): {sorted(eksik)} — kullanıcı oraya "
        f"hiçbir yoldan ulaşamaz"
    )


def test_menude_var_olmayan_panel_yok():
    """Silinmiş bir paneli menüde bırakmak, tıklanınca boş ekran demektir."""
    hayalet = _menu_girdileri("panel") - _bildirilen_paneller() - SEKMEYE_YONLENEN
    assert not hayalet, f"karşılığı olmayan menü girdisi: {sorted(hayalet)}"


def test_her_kategorinin_menude_yeri_var():
    backend_katlar = {c["id"] for c in settings_api.CATEGORIES}
    eksik = backend_katlar - _menu_girdileri("cat")
    assert not eksik, (
        f"HQ_MENU'ya yazılmamış kategori(ler): {sorted(eksik)} — emniyet onları "
        f"son gruba düşürür ama yanlış grupta belirir ve kimse fark etmez"
    )


def test_menude_var_olmayan_kategori_yok():
    backend_katlar = {c["id"] for c in settings_api.CATEGORIES}
    hayalet = _menu_girdileri("cat") - backend_katlar
    assert not hayalet, f"backend'de olmayan kategori menüde: {sorted(hayalet)}"


def test_ic_ice_ikinci_menu_geri_gelmedi():
    """`#hq-settings-side` kaldırıldı; geri gelirse iki menü yine iç içe girer."""
    html = _html()
    assert 'id="hq-settings-side"' not in html, (
        "panel içi ikinci kategori listesi geri gelmiş — D5 kararı iki menüyü "
        "tek listede birleştirmişti"
    )
    assert "hq-settings-side" not in _js(), (
        "JS hâlâ kaldırılmış `#hq-settings-side`'a yazıyor"
    )


def test_menu_tek_kaynaktan_ciziliyor():
    """Statik HTML kopyası bırakmak = aynı soruya iki cevap (`surum.js` dersi)."""
    html = _html()
    assert "hq-subtab" not in html, (
        "index.html'de statik menü butonu kalmış — menü yalnız hqMenuCiz'den çizilir"
    )
    assert 'id="hq-subnav"' in html, "menü kabı silinmiş"


def test_tts_panelindeki_olu_bolumler_ayara_bagli():
    """Ayarı gizleyip aynı özelliğin başka yüzeyini açık bırakma.

    Fish Speech anahtarı `available:false` (sunucu pakette yok) ama TTS
    panelindeki "Fish Speech referans sesi" yükleyicisi ekranda duruyordu —
    müşteri dosya yükler, hiçbir şey olmaz.
    """
    html = _html()
    assert 'data-ayar="USE_FISH_TTS"' in html, (
        "Fish bölümü hangi ayara bağlı olduğunu söylemiyor"
    )
    js = _js().replace(" ", "")
    assert "querySelectorAll('[data-ayar]')" in js, (
        "JS `data-ayar` kancasını kullanmıyor → blok her hâlükârda görünür"
    )


def test_menu_gruplari_tanimli():
    gruplar = re.findall(r"grup:'([^']+)'", _menu_bloku())
    assert len(gruplar) >= 3, f"grup başlıkları kaybolmuş: {gruplar}"
    assert len(gruplar) == len(set(gruplar)), f"yinelenen grup başlığı: {gruplar}"
