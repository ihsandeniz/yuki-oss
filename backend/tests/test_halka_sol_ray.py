"""HALKA sol rayı (#hr-leftrail) kaldırıldı — parçası geri sızmasın.

🔴 Ölçülen kusur (2026-09-08): ray markup'ı bir oturumda silindi ama
**onu besleyen zamanlayıcılar bırakıldı.** Düğümler yok, döngüler koşuyordu:

    vitals      3 sn   → ModeData.system()                    20 istek/dk
    sol alarm  10 sn   → ModeData.reminders()                  6 istek/dk
    aktif mod  15 sn   → GET /api/modes/list                   4 istek/dk
    gauge      60 sn   → ModeData.health()                     1 istek/dk
    istatistik 60 sn   → todoLists + 3× todoTasks             ~4 istek/dk
                                                        ────────────────
                                                        ~35 istek/dakika

Hiçbiri hata vermiyordu: `querySelector` null döner, yazıcı sessizce çıkar —
ama **istek çoktan atılmıştır**. Yani belirti yok, yalnız boşa giden ağ ve pil.

📏 Ders: markup'ı silmek onu besleyen döngüyü susturmaz. Bir bölüm kaldırılırken
kaldırılacak üç şey vardır: markup · üretici · **besleyici**.

⚠️ Bu dosya statik bir bekçidir, kanıt değildir. Kanıt ölçümdür (yukarıdaki
istek sayıları canlı ölçüldü). Buradaki testler yalnız aynı yarım kaldırmanın
sessizce geri dönmesini engeller.

⚠️ Ad + AÇILIŞ PARANTEZİ aranıyor (`_refreshVitals(`), çıplak ad değil: aynı
adlar dosyadaki açıklama yorumunda **parantezsiz** geçiyor ve orada geçmeleri
gerekiyor (kaldırmanın gerekçesini anlatıyorlar). Çıplak ad arasaydık bu test
kendi açıklamasını kusur sayardı.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[2] / "frontend" / "modes"
HUD_JS = KOK / "hud-ring.js"
HUD_CSS = KOK / "hud-ring.css"

# Rayın besleyicileri: hepsi bir ağ isteği yapıp yalnız ray düğümlerine yazıyordu.
BESLEYICILER = [
    "_refreshVitals",
    "_refreshGauges",
    "_refreshStats",
    "_refreshActiveMode",
    "_refreshLeftAlarms",
    "_refreshPersona",
]

# Rayın üreticileri ve kurulumları.
URETICILER = [
    "_gauge",
    "_charSelectorHtml",
    "_initCharSelector",
    "_vitalsHtml",
    "_personaHtml",
    "_statsHtml",
    "_activeModHtml",
    "_leftAlarmsHtml",
    "_initLeftCollapse",
    "_setupLeftDrag",
    "_teardownLeftDrag",
]

# Yalnız rayda yaşayan düğüm kimlikleri. #hr-side (sağ panel) bunları kullanmaz —
# ölçüldü 2026-09-08: sağ panel .hr-side-header/.hr-tab-btn ailesini kullanıyor.
RAY_ID = [
    "hr-leftrail",
    "hr-rail-header",
    "hr-rail-collapse-btn",
    "hr-g-state",
    "hr-g-mem",
    "hr-g-up",
    "hr-v-cpu",
    "hr-v-ram",
    "hr-v-net",
    "hr-st-msg",
    "hr-st-mem",
    "hr-st-task",
    "hr-persona-name",
    "hr-persona-state",
    "hr-actmod-inner",
    "hr-la-inner",
]


@pytest.fixture(scope="module")
def js() -> str:
    return HUD_JS.read_text(encoding="utf-8")


@pytest.mark.parametrize("ad", BESLEYICILER + URETICILER)
def test_ray_fonksiyonu_ne_tanimli_ne_cagriliyor(js: str, ad: str) -> None:
    """`ad(` biçimi hiç geçmemeli — ne tanım ne çağrı."""
    assert f"{ad}(" not in js, (
        f"{ad}( hâlâ hud-ring.js'te geçiyor. Sol ray kaldırıldı; bu fonksiyon "
        f"ya var olmayan bir düğüme yazıyor ya da boşuna ağ isteği atıyor. "
        f"Geri getirmek istiyorsan rayı da geri getir — yarısı olmaz."
    )


@pytest.mark.parametrize("hid", RAY_ID)
def test_ray_dugum_kimligi_javascriptte_gecmiyor(js: str, hid: str) -> None:
    """Ray kimliklerine `querySelector`/`getElementById` ile uzanılmamalı.

    🔴 Bu testin ilk hâli YANLIŞ POZİTİF verdi ve kendi yazarı tarafından sahada
    yakalandı: çıplak `#hr-leftrail` aranıyordu, ama o dize dosyadaki açıklama
    yorumunda geçiyor — üstelik **geçmesi gerekiyor**, kaldırmanın kaydı orada.
    Ölçüt daraltıldı: aranan şey artık **tırnak içinde** bir seçici, yani ancak
    `querySelector('#…')` / `getElementById('…')` biçiminde kullanılabilecek hâli.
    📏 Ders (bu depoda üçüncü kez): bir ölçüm aracı yorum metnini kod sayarsa
    ölü olanı canlı, canlı olanı ölü gösterir.
    """
    for kalip in (f"'#{hid}'", f'"#{hid}"', f"'{hid}'", f'"{hid}"'):
        assert kalip not in js, (
            f"{kalip} hud-ring.js'te seçici olarak geçiyor — kaldırılan sol rayın "
            f"düğümü. Bu seçici hep null döner; onu besleyen kod da boşa koşar."
        )


def test_ray_zamanlayicilari_yok(js: str) -> None:
    """Rayı besleyen üç zamanlayıcı değişkeni tamamen gitmiş olmalı."""
    for degisken in ("_vitalsTimer", "_leftModTimer", "_leftAlarmTimer"):
        assert degisken not in js, (
            f"{degisken} duruyor. Bu zamanlayıcı görünmeyen bir düğüm için "
            f"periyodik ağ isteği atar — belirtisi yoktur, ölçmeden görülmez."
        )


def test_60sn_dongusu_yalniz_hafiza_haritasini_taziyor(js: str) -> None:
    """Kalan 60 sn'lik döngü sağ paneldeki hafıza haritasını besliyor — o canlı.

    Bu test döngünün *varlığını* değil **kapsamını** korur: içine tekrar
    gauge/istatistik eklenirse ray olmadan yine boşa istek başlar.
    """
    assert "_renderMemMap()" in js, "60 sn döngüsünün canlı işi de silinmiş olmamalı"


def test_sag_panel_ray_ailesinden_bagimsiz(js: str) -> None:
    """#hr-side kaldırılan sınıflara bağımlı olmamalı (ray CSS'i günün birinde silinecek).

    ⚠️ CSS bilerek TEMİZLENMEDİ: bu depoda ölü CSS avı üç ayrı araç
    körlüğü üretti (/179/184) ve kendi kapısını gerektiriyor. Bu test o işi
    yapmaz, yalnız **sağ panelin ölü aileye bağlanmadığını** garanti eder ki
    temizlik günü geldiğinde güvenle silinebilsin.
    """
    side_bas = js.find("side.id = 'hr-side'")
    assert side_bas != -1, "sağ panel kurulumu bulunamadı — test çapası kaymış"
    side_blok = js[side_bas : side_bas + 2000]
    for olu_sinif in ("hr-wcard", "hr-gauge", "hr-cs-btn", "hr-rail-"):
        assert olu_sinif not in side_blok, (
            f"sağ panel {olu_sinif} kullanıyor — bu sınıf sol raya aitti ve ölü "
            f"sayılıyordu. Ya sağ panel düzeltilmeli ya sınıf canlı sayılmalı."
        )


# ──  KAPANDI (2026-09-08) — beklenti ters çevrildi ───────────────────
# Buradaki test eskiden ölü CSS'in DURDUĞUNU kayda geçiriyordu ("temiz demiyor,
# biliyoruz diyor") ve docstring'i kapanış günü tersine çevrilmesini söylüyordu.
# O gün geldi: 56 kural / 245 satır silindi. Artık kapı ters yönde bekçilik yapar.

RAY_SECICILERI = (
    # ── sol ray ailesi ──
    "#hr-leftrail", ".hr-rail-header", ".hr-rail-title", ".hr-gauge", ".hr-g-bg",
    ".hr-g-fg", ".hr-wcard", ".hr-vital", ".hr-persona-orb", ".hr-persona-txt",
    ".hr-stats-body", ".hr-stat", "#hr-actmod-inner", ".hr-am-name", ".hr-la-item",
    "#hr-gauges", ".hr-wcard--collapsed",
    # ── daha eski kaldırmaların artıkları (2026-09-08) ──
    # ⚠️ Bu liste DAR tutuldu: yalnız adı kaynakta HİÇ geçmeyenler. Kardeşleri
    # CANLI ve burada YOK — `.hr-tab-btn` · `.hr-tabs-bar` · `.hr-tab-pane` ·
    # `.hr-panel-head` · `.hr-cs-btn` · `#hr-stocks-body` · `#hr-hq-body` ·
    # `.hr-hq-grid/card/lbl/val` · `.hr-sz-*`. İkisini karıştırmak ürünü bozar:
    # bu turda araç tam o kardeşleri iki kez "ölü" ilan etti (bkz. docstring).
    ".hr-panel", "#hr-panel-mem", "#hr-panel-flow", ".hr-tabs", ".hr-tab",
    ".hr-body", ".hr-card", ".hr-empty", ".hr-tabs-body", ".hr-cs-body",
    ".hr-cs-icon", ".hr-cs-lbl", ".hr-cs-dot", ".hr-cs-rol", "#hr-char-selector",
    ".hr-stocks-grid", ".hr-stock-card", ".hr-stock-sym", ".hr-stock-price",
    ".hr-stock-chg",
)


# 🔴 CANLI KARDEŞLER — bu kapı ters yönde bekçilik yapar (2026-09-08).
# Yukarıdaki temizlik turunda tarayıcı İKİ KEZ canlı sınıfı "ölü" ilan etti:
#   ① `.hr-sz-hex/diamond/oct` — `hud-ring.js:949` adı ÇALIŞMA ANINDA kuruyor
#      (`'hr-snap-zone hr-sz-' + zone.shape`), düz tarama göremedi.
#   ② `.hr-hq-grid/card/lbl/val` — aracın blok-yorum sökücüsü bir JS METNİNİN
#      içindeki `/*` ile eşleşip 5131 karakteri yuttu; `_renderHq` o blokta kaldı.
# İkisi de silinseydi HALKA'nın snap bölgeleri ve KOMUTEVİ sekmesi bozulurdu.
YASAYAN_KARDESLER = (
    ".hr-sz-hex", ".hr-sz-diamond", ".hr-sz-oct", ".hr-hq-grid", ".hr-hq-card",
    ".hr-hq-lbl", ".hr-hq-val", ".hr-tab-btn", ".hr-tabs-bar", ".hr-panel-head",
)


@pytest.mark.parametrize("secici", YASAYAN_KARDESLER)
def test_canli_kardesler_YANLISLIKLA_SILINMEDI(secici: str) -> None:
    """Ölü kardeşiyle karıştırılıp silinmesin — bu sınıflar HÂLÂ kullanılıyor."""
    ham = HUD_CSS.read_text(encoding="utf-8")
    kod = re.sub(r"/\*.*?\*/", " ", ham, flags=re.S)
    assert re.search(re.escape(secici) + r"(?![A-Za-z0-9_-])", kod), (
        f"{secici} CSS'ten SİLİNMİŞ ama JS onu hâlâ üretiyor → biçimsiz görünüm. "
        f"Ölü kardeşleriyle (RAY_SECICILERI) karıştırılmış olabilir."
    )


@pytest.mark.parametrize("secici", RAY_SECICILERI)
def test_ray_css_i_geri_gelmedi(secici: str) -> None:
    """Silinen sol ray seçicileri CSS'e geri sızmamalı.

    İki ölçü tuzağı açıkça kapalı, ikisi de bu turda BİZZAT düşüldü:
      ② YORUM — dosyada temizliği ANLATAN yorumlar var ve içlerinde seçici
        adları geçiyor; ham metinde arasaydık test kendi yanlış pozitifini verirdi.
      ③ ALT-DİZE — `.hr-wcard` düz `in` ile arandığında hâlâ duran
        `.hr-wcard-toggle`'ı yakalıyordu. Token sınırı şart.
    (Aynı iki tuzak bu depoda /179/184'te de ölçülmüştü.)
    """
    ham = HUD_CSS.read_text(encoding="utf-8")
    kod = re.sub(r"/\*.*?\*/", " ", ham, flags=re.S)
    kalip = re.escape(secici) + r"(?![A-Za-z0-9_-])"
    assert re.search(kalip, kod) is None, (
        f"{secici} CSS'e geri gelmiş. Sol ray 2026-09-08'de kaldırıldı (/218); "
        f"markup ve besleyicileri yok, bu kural hiçbir elemana uygulanmaz."
    )


def test_ray_temizligi_gercekten_kod_uzerinde_olculuyor() -> None:
    """Yukarıdaki kapının GÖREBİLDİĞİNİ kanıtlar — kör test her şeyi onaylar.

    Bugünün dersi buydu: iki tarama aracı 'temiz' dedi, ikisi de kördü. Bir kapı
    'yok' diyorsa, o kapının 'var'ı ayırt edebildiği gösterilmeli.
    """
    kod = re.sub(r"/\*.*?\*/", " ", "/* #hr-leftrail yorumda */\n#hr-side { a: b }", flags=re.S)
    assert "#hr-leftrail" not in kod, "yorum sökücü çalışmıyor — kapı yanlış pozitif verir"
    assert "#hr-side" in kod, "yorum sökücü kodu da yiyor — kapı yanlış negatif verir"

    # ③ token sınırı: `.hr-wcard` uzun bir kardeşin İÇİNDE eşleşmemeli,
    #    ama tam eşleşmeyi de kaçırmamalı.
    sinir = r"(?![A-Za-z0-9_-])"
    assert re.search(re.escape(".hr-wcard") + sinir, ".hr-wcard-toggle { a:b }") is None
    assert re.search(re.escape(".hr-wcard") + sinir, ".hr-wcard { a:b }") is not None
