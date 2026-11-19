# -*- coding: utf-8 -*-
"""FAZ 3 · Dalga 2 · dosya kuyruğu 3/4 — `frontend/js/map-engine.js` kapıları.

MAP panosunun yüzeylerinin tamamı JS'ten doğuyor; `dil.js::ciz()` hiçbirini
görmez. Buradaki kapılar canlı tarayıcı gerektirmeden o yapıyı korur.

🔴 Bu dosyanın en pahalı kapısı ③: `map-engine.js` **klasik script** ve
`index.html`'de `core.js`'ten SONRA yükleniyor. Burada `function _t` bildirmek
`window._t`ye yazar ve core.js'in sarmalayıcısını **ezer** — gövdeler bugün
aynı olduğu için hiçbir şey kırılmaz, yarın ayrıştıklarında core.js'in 100
çağrı yeri sessizce bu dosyanın kopyasını çağırır.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

FRONT = Path(__file__).resolve().parents[2] / "frontend"
JS = FRONT / "js" / "map-engine.js"
CORE = FRONT / "js" / "core.js"
TR = FRONT / "js" / "diller" / "tr.js"
EN = FRONT / "js" / "diller" / "en.js"

GOK = ["sun", "mercury", "venus", "mars", "jupiter", "saturn", "uranus",
       "neptune", "earth", "ceres", "pluto", "eris", "makemake", "haumea"]
GOK_ALAN = ["name", "diameter", "mass", "gravity", "temp", "moons", "orbit",
            "day", "atmosphere", "distance", "desc"]
KATMANLAR = ["eq", "fire", "plane", "iss", "volcano", "weather", "air", "ship",
             "adsb", "eonet", "sat", "cctv", "asteroid", "military",
             "livestream", "poi", "kpindex", "osmplaces"]


@pytest.fixture(scope="module")
def js() -> str:
    return JS.read_text()


def _anahtarlar(yol: Path) -> set[str]:
    return set(re.findall(r"^\s*['\"]([a-zA-Z0-9_.\-]+)['\"]\s*:", yol.read_text(), re.M))


def _planets_blok(js: str) -> str:
    m = re.search(r"const _PLANETS = \{", js)
    assert m, "`_PLANETS` bulunamadı"
    i, d = m.end() - 1, 0
    while i < len(js):
        if js[i] == "{":
            d += 1
        elif js[i] == "}":
            d -= 1
            if d == 0:
                break
        i += 1
    return js[m.start(): i + 1]


# ── ① sözlük kapsaması ────────────────────────────────────────────────────

def test_kullanilan_her_anahtarin_karsiligi_VAR(js: str):
    tr, en = _anahtarlar(TR), _anahtarlar(EN)
    kul = {k for k in re.findall(r"_mtc?\('([a-zA-Z0-9_.\-]+)'", js) if not k.endswith(".")}
    kul |= {f"harita.katman.{k}" for k in KATMANLAR}
    eksik_tr = sorted(k for k in kul if k not in tr)
    eksik_en = sorted(k for k in kul if k not in en)
    assert not eksik_tr, f"tr.js'te yok: {eksik_tr}"
    assert not eksik_en, f"en.js'te yok: {eksik_en}"


def test_gok_cisimlerinin_HER_METIN_ALANI_sozlukte(js: str):
    """`_gok()` sözlükte bulamadığı alana '—' basar — yani eksik bir çeviri
    ekranda hata değil BOŞLUK üretir; onu yalnız bu kapı görür."""
    tr, en = _anahtarlar(TR), _anahtarlar(EN)
    blok = _planets_blok(js)
    eksik = []
    for g in GOK:
        # ⚠️ Son gök cismi (`haumea`) virgülsüz kapanır — ilk yazımda regex `\},`
        #    beklediği için o blok "bulunamadı" sanıldı. Kapı ürünü değil kendi
        #    deseni yüzünden kırmızı yandı.
        m = re.search(r"\n  " + g + r": \{(.*?)\n  \},?\n", blok, re.S)
        assert m, f"{g} bloğu bulunamadı"
        for a in GOK_ALAN:
            if re.search(rf"\b{a}: '—'", m.group(1)):   # yokluk işareti, metin değil
                continue
            k = f"uzay.{g}.{a}"
            if k not in tr or k not in en:
                eksik.append(k)
    assert not eksik, f"gök cismi alanı sözlükte yok: {eksik}"


def test_tr_en_paritesi(js: str):
    tr = {k for k in _anahtarlar(TR) if k.startswith(("harita.", "uzay."))}
    en = {k for k in _anahtarlar(EN) if k.startswith(("harita.", "uzay."))}
    assert tr == en, f"tek taraflı anahtar: {sorted(tr ^ en)}"


# ── ② ad çakışması: `_t` DEĞİL `_mt` ──────────────────────────────────────

def test_map_engine_core_js_nin_t_sini_EZMEZ(js: str):
    assert not re.search(r"^function _tc?\s*\(", js, re.M), (
        "map-engine.js `_t`/`_tc` bildiriyor — klasik script olduğu için "
        "`window._t`ye yazar ve core.js'in sarmalayıcısını ezer"
    )
    assert not re.search(r"(?<![\w.])_t\(", js), (
        "map-engine.js `_t(` çağırıyor — kendi `_mt`'sini kullanmalı"
    )


def test_core_js_hala_t_bildiriyor_VARSAYIM_ayakta():
    """Üstteki kapının gerekçesi core.js'in `_t` bildirmesi. O değişirse kapı
    anlamsızlaşır ama yeşil kalır — varsayımın kendisi de ölçülür."""
    assert re.search(r"^function _t\s*\(", CORE.read_text(), re.M), (
        "core.js artık `_t` bildirmiyor — ad çakışması kapısını gözden geçir"
    )


# ── ③ modül düzeyi sabit ──────────────────────────────────────────────────

def test_PLANETS_icinde_cagri_YOK(js: str):
    """`const` modül yüklenirken değerlendirilir: içine `_mt()` koymak sözlük
    hazır olmadan çağırır ve dil değişiminde değeri yine DONDURUR. İlk yazımda
    tam bu yapıldı — kaçınılan tuzağın bir kat aşağısı."""
    assert "_mt(" not in _planets_blok(js), (
        "`_PLANETS` içinde `_mt(` var — sabitte ANAHTAR durmalı, metni `_gok()` çözer"
    )


def test_PLANETS_e_dogrudan_erisim_yalniz_gok_icinde(js: str):
    satirlar = [l.strip() for l in js.split("\n") if "_PLANETS[" in l]
    assert len(satirlar) == 1, (
        f"`_PLANETS`'a doğrudan erişim: {satirlar} — hepsi `_gok()`'ten geçmeli, "
        "yoksa ekrana ham anahtar (`uzay.mars.desc`) basılır"
    )


def test_ticker_ve_portal_etiketleri_gomulu_DEGIL(js: str):
    """🔁 2026-10-04: akan şerit (`_tickerItems`) ve PORTAL (`MODES`)
    yüzeyleriyle birlikte SİLİNDİ. Kapı artık iki yönlü: geri gelirlerse
    gömülü metinle gelmesinler; gelmedilerse sözlükte artık anahtarları da
    kalmasın (`harita.ticker.*`, `harita.durum.*` öksüz kalırdı)."""
    m = re.search(r"let _tickerItems = \[(.*?)\];", js, re.S)
    assert not m or "text: '" not in m.group(1), "`_tickerItems` gömülü metin taşıyor"
    m2 = re.search(r"const MODES = \{(.*?)\n  \};", js, re.S)
    assert not m2 or "label: '" not in m2.group(1), "portal `MODES` gömülü etiket taşıyor"
    if not m:
        assert "'harita.ticker." not in TR.read_text(), "şerit gitti ama anahtarları sözlükte duruyor"
    if not m2:
        assert "'harita.durum.idle'" not in TR.read_text(), "portal gitti ama durum anahtarları sözlükte duruyor"


def test_katman_adi_TEK_KAYNAK(js: str):
    """Ad iki yerde duruyordu (düğme etiketi + liste satırı) ve Kp seviyeleri
    de öyleydi — üstelik Kp'nin iki kopyası BİRBİRİNDEN FARKLI yazılmıştı."""
    # ⚠️ Ad YORUMDA da geçiyor (neden kaldırıldığı yazılı) — düz `count` onu da
    #    sayıyordu. Aranan şey bildirimin kendisi.
    assert not re.search(r"const kpLabelsTR", js), "`kpLabelsTR` bildirimi duruyor"
    assert "DEPREM', fire:" not in js, "katman adı sözlüğü koda geri gelmiş"
    # 🪤 ÖNEK EŞLEŞMESİ: `"function _katmanAdi" in js` yazsaydık
    #    `_katmanAdiX` de eşleşir ve mutasyon YEŞİL kalırdı (bizzat oldu).
    #    Ad sınırı açık yazılır.
    assert len(re.findall(r"function _katmanAdi\(", js)) == 1


# ── ④ güvenlik: üçüncü taraf verisi ───────────────────────────────────────

UCUNCU_TARAF = ["data.address", "data.hours", "ast.name", "cam.name", "cam.city",
                "ev.title", "ev.name", "ev.snippet", "sat.name", "v.name",
                "c.city", "s.city", "display_name", "place"]


def test_ucuncu_taraf_verisi_kacissiz_innerHTML_e_GITMEZ(js: str):
    """Alanların kaynağı OpenStreetMap · USGS · NASA · OpenSky — hepsi dış,
    biri (OSM) herkesin düzenleyebildiği açık bir veritabanı. `planner.html`
    turundaki openfoodfacts vakasının birebir aynısı."""
    ham = []
    for alan in UCUNCU_TARAF:
        desenler = [r"\$\{" + re.escape(alan) + r"\}",
                    r"push\(\[[^\]]*?(?<![\w.])" + re.escape(alan) + r"[\],]"]
        for desen in desenler:
            for m in re.finditer(desen, js):
                i = js.rfind("\n", 0, m.start()) + 1
                satir = js[i: js.find("\n", m.end())]
                if not (("<" in satir and ">" in satir) or "push([" in satir):
                    continue   # sohbet promptu — orada kaçış YANLIŞ olurdu
                if not any(x in satir for x in ("_escHtml", "encodeURIComponent", "_guvenliBag")):
                    ham.append(f"{alan} → {satir.strip()[:80]}")
    assert not ham, "kaçışsız üçüncü taraf verisi:\n" + "\n".join(ham)


def test_dis_url_dogrudan_href_e_YAZILMAZ(js: str):
    assert not re.search(r'href="\$\{data\.website\}"', js), (
        "`data.website` doğrudan `href`e yazılıyor — `javascript:` şeması geçer"
    )
    assert re.search(r"function _guvenliBag\(", js), (
        "`_guvenliBag` şema beyaz listesi kaldırılmış"
    )   # ← açılış parantezi ŞART: öneki eşleşen bir ad kapıyı yeşil bırakırdı


# ── ⑤ dil tazeleyici ──────────────────────────────────────────────────────

def test_dil_tazeleyici_VAR_ve_veriyi_silmiyor(js: str):
    assert "yuki-dil-degisti" in js, "dil tazeleyici yok — MAP yüzeyleri dilde donar"
    kuyruk = js[js.index("window.addEventListener('yuki-dil-degisti'"):]
    assert "_fetchLayer(" not in kuyruk, (
        "tazeleyici `_fetchLayer` çağırıyor — dil değiştirmek her açık katmanı "
        "YENİDEN İNDİRİR (OpenSky'ın istek sınırı buna bir dakika dayanır)"
    )
    assert "setPlanetMode(" not in kuyruk, (
        "tazeleyici `setPlanetMode` çağırıyor — canvas'ı yeniden boyutlandırır "
        "ve dönüş animasyonunu sıfırlar; metin için `_planetHudMetni` var"
    )


def test_tr_TR_bicimi_gomulu_DEGIL(js: str):
    assert not re.search(r"toLocale\w*\('tr-TR'\)", js), (
        "`toLocale…('tr-TR')` gömülü — metin çevrilse bile biçim Türkçe kalır"
    )


def _sozluk(yol: Path) -> dict[str, str]:
    return dict(re.findall(r"^\s*'([a-z0-9_.\-]+)':\s*'((?:[^'\\]|\\.)*)',\s*$",
                           yol.read_text(), re.M))


def test_gok_degerlerinde_ONDALIK_AYRACI_dile_uygun():
    """Ondalık ayracı dile bağlıdır: TR virgül (`1,52`), EN nokta (`1.52`).

    🔴 2026-09-22 canlı turda bulundu: 13 `uzay.*.distance` değeri İKİ DİLDE
    BİRDEN tersti — kaynak TR verisi `1.52 AU` yazıyordu, EN'i üreten mekanik
    dönüştürücü noktayı körlemesine virgüle çevirdi → EN `1,52 AU`. Statik
    kapılar anahtarın VARLIĞINI ölçüyordu, değerin BİÇİMİNİ değil.

    Ölçü: rakam + ayraç + **1-2** rakam = kesin ondalık. 3 rakamlı grup
    (`6.779`) binlik de olabilir — belirsiz olduğu için sayılmaz.
    """
    tr, en = _sozluk(TR), _sozluk(EN)
    ondalik_nokta = re.compile(r"\d\.\d{1,2}(?!\d)")
    ondalik_virgul = re.compile(r"\d,\d{1,2}(?!\d)")
    bozuk = []
    for gok in GOK:
        for alan in GOK_ALAN:
            k = f"uzay.{gok}.{alan}"
            if ondalik_nokta.search(tr.get(k, "")):
                bozuk.append(f"TR {k} = {tr[k]!r} (ondalık NOKTA)")
            if ondalik_virgul.search(en.get(k, "")):
                bozuk.append(f"EN {k} = {en[k]!r} (ondalık VİRGÜL)")
    assert not bozuk, "Ondalık ayracı dile uymuyor:\n  " + "\n  ".join(bozuk)
