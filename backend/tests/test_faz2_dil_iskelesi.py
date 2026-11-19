"""FAZ 2 — i18n iskelesi (2026-09-18).

`js/dil.js` + `js/diller/*.js`: çeviri katmanının taşıyıcısı. Bu dosya üçünü ölçer:

  ① Yükleme kuralı — sözlükler ve `dil.js` <head>'de, SENKRON, `defer` YOK
  ② Tek kapı — dil değiştirmenin ikinci bir yolu kalmamış olmalı
  ③ Önbellek kapısı — sözlük değişince `?v=` damgası bumplanmış olmalı

🔴 ③ neden ZORUNLU: `sw.js` cache-first. Bir çeviri düzeltilip damga
unutulursa **test yeşil kalır, müşteri eski metni görür** ve kimse sebebini
bulamaz. `scripts/yayin.py surum` tek tek `?v=` damgalarına DOKUNMAZ.
"""
from __future__ import annotations

import re
from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
DILLER = ("tr", "ja", "en")
KAYNAK = "tr"


def _oku(*parcalar: str) -> str:
    return (FRONTEND.joinpath(*parcalar)).read_text(encoding="utf-8")


def _yorumsuz(js: str) -> str:
    """`//` ve `/* */` yorumlarını siler.

    ⚠️ Gerekçe ölçülmüş: bu depoda kaldırılan kusurlar gerekçeleriyle birlikte
    yorumda ALINTILANIYOR (desen bilinçli). Ham metinde arayan bir kapı kendi
    açıklamasını "kusur" sanar — FAZ 1'de ve FAZ 2'de birer kez tam olarak bu
    oldu. Kaba bir sıyırıcı yeterli: amaç sözdizimi ayrıştırmak değil, yorumda
    geçen örnek kodun kapıyı tetiklemesini engellemek.
    """
    js = re.sub(r"/\*.*?\*/", " ", js, flags=re.S)
    return "\n".join(s for s in js.splitlines() if not s.lstrip().startswith("//"))


def _sozluk_anahtarlari(kod: str) -> set[str]:
    metin = _oku("js", "diller", f"{kod}.js")
    govde = metin.split("=", 1)[-1]
    return set(re.findall(r"^\s*'([^']+)':", govde, re.M))


# --------------------------------------------------------------------------- #
# ① Yükleme kuralı
# --------------------------------------------------------------------------- #

def test_dil_dosyalari_var():
    assert (FRONTEND / "js" / "dil.js").exists()
    for kod in DILLER:
        assert (FRONTEND / "js" / "diller" / f"{kod}.js").exists(), f"sözlük yok: {kod}"


def test_senkron_yuklenir_defer_yok():
    """`defer`/`async` olsaydı ilk kare Türkçe basılır sonra çevrilirdi (FOUT) —
    `tema.js:7-9`'un FOUC gerekçesinin birebir aynısı."""
    for sayfa in ("index.html", "planner.html"):
        metin = _oku(sayfa)
        for satir in re.findall(r"<script[^>]*js/(?:dil\.js|diller/\w+\.js)[^>]*>", metin):
            assert "defer" not in satir, f"{sayfa}: dil betiği defer ile yükleniyor → {satir}"
            assert "async" not in satir, f"{sayfa}: dil betiği async ile yükleniyor → {satir}"


def test_sozlukler_dil_js_ten_ONCE_yuklenir():
    """`dil.js` açılışta sözlükten okur; sonra yüklenirse ilk kare boş çevirir."""
    for sayfa in ("index.html", "planner.html"):
        metin = _oku(sayfa)
        i_dil = metin.index("js/dil.js")
        for kod in DILLER:
            i_sozluk = metin.index(f"js/diller/{kod}.js")
            assert i_sozluk < i_dil, f"{sayfa}: {kod}.js, dil.js'ten SONRA yükleniyor"


def test_planner_de_dil_yukluyor():
    """PLAN ekranı ayrı bir belge (iframe). `tema.js` oraya ayrıca konmuştu;
    dil de aynı sebeple konmalı, yoksa iframe çevirisiz kalır."""
    assert "js/dil.js" in _oku("planner.html")


# --------------------------------------------------------------------------- #
# ② Tek kapı
# --------------------------------------------------------------------------- #

def test_core_js_ikinci_dil_durumu_tutmuyor():
    """🔑 FAZ 2'nin asıl kuralı. `core.js` kendi `_currentLang`/`_LANGS`'ini
    tutarsa `dil.js` ile ayrışır — düzelttiğimiz `data-theme`/`data-tema`
    çift-sistem arızasının bir tur sonraki hâli."""
    kod = _yorumsuz(_oku("js", "core.js"))
    for yasak in ("_currentLang", "_LANGS", "_langBilgi", "_LANG_FALLBACK"):
        assert yasak not in kod, f"core.js hâlâ kendi dil durumunu tutuyor: {yasak}"


def test_dil_yazma_yolu_tek():
    """`/api/language`'e POST atan TEK yer `dil.js` olmalı."""
    # ⚠️ Burada REGEX KULLANMA. `[^\n]*api/language[^\n]*` deseni `vendor/`
    # altındaki minified dosyalarda (tek satır, 100 KB+) katastrofik geri
    # izlemeye giriyor ve test süresiz asılıyor — ilk koşuda tam olarak bu oldu.
    # Düz `in` kontrolü aynı işi görür.
    yazanlar = []
    for js in FRONTEND.rglob("*.js"):
        if "node_modules" in js.parts or "dist" in js.parts or js.name.endswith(".min.js"):
            continue
        kod = _yorumsuz(js.read_text(encoding="utf-8", errors="ignore"))
        for satir in kod.splitlines():
            if "api/language" in satir and ("POST" in satir or "method:" in satir):
                yazanlar.append(js.name)
    assert set(yazanlar) <= {"dil.js"}, (
        f"/api/language'e POST atan ikinci yol var: {sorted(set(yazanlar))} — "
        "dil değiştirmenin tek kapısı YukiDil.ayarla() olmalı"
    )


def test_tema_sozlesmesini_aynaliyor():
    """`intro-sequences.js::temaPaneliCiz` deseni `al`/`ayarla`/`secenekler`
    bekliyor; dil aynı sözleşmeyi taşımazsa her panel kendi biçimini uydurur."""
    kod = _oku("js", "dil.js")
    for uye in ("al:", "ayarla:", "secenekler:", "t:", "sunucudan:"):
        assert uye in kod, f"YukiDil sözleşmesinde eksik: {uye}"


# --------------------------------------------------------------------------- #
# ③ Sözlük sağlığı + önbellek kapısı
# --------------------------------------------------------------------------- #

def test_sozlukler_anahtar_paritesi():
    """⚠️ Bu testin İDDİASI 2026-09-18'de (FAZ 3) DARALDI — gevşetilmedi, DEVREDİLDİ.

    Yazıldığında sözlüklerde 4 anahtar vardı ve *"üçü de aynı kümeyi taşır"*
    bedava doğruydu. FAZ 3'te geliştiricinin kapsam kararı **yalnız `en`** oldu:
    `ja` üründe kayıtlı bir asistan dili ama arayüzü hiç çevrilmedi ve bu turda
    da çevrilmeyecek (Japonca çıktıyı bu vault'ta doğrulayamıyoruz — ölçülmemiş
    300 satır, çeviri GİBİ GÖRÜNEN bir yüzey üretirdi).

    Eski hâliyle koşsaydı iki seçenek kalırdı: ① testi geçsin diye 300 satır
    uydurmak ② kapıyı silmek. İkisi de yanlış. Onun yerine iddia iki parçaya
    ayrıldı ve İKİSİ DE `test_faz3_metin_cevirisi.py`'de duruyor:

      · `test_en_sozlugu_tr_yi_TAM_kapsiyor`  → `en` için parite KATI
      · `test_ja_kapsami_DUSMUYOR`            → `ja` için CIRCIR (gerileme yasak)

    Burada kalan, FAZ 2'nin asıl ölçtüğü şey: **kaynak sözlük boş değil** ve
    eksik anahtar sessizce kaybolmuyor (`dil.js` kaynağa düşüyor, bkz.
    `test_eksik_anahtar_kaynaga_dusuyor`).
    """
    kaynak = _sozluk_anahtarlari(KAYNAK)
    assert kaynak, "kaynak sözlük boş"
    for kod in DILLER:
        # `-cogul` kaynakta (tr) bilerek YOKTUR: Türkçe'de sayıdan sonra çoğul
        # eki gelmez ("5 kayıt"), İngilizce'de gelir ("5 records"). Kökü
        # kaynakta olmayan bir çoğul hâlâ ölü çeviridir — istisna kapıyı
        # boşaltmıyor, yalnız daraltıyor. Backend kataloğunda da aynı kural
        # (`Mc` · `test_backend_en_katalogu_tr_yi_kapsiyor`).
        fazla = _sozluk_anahtarlari(kod) - kaynak
        for k in sorted(fazla):
            assert k.endswith("-cogul") and k[: -len("-cogul")] in kaynak, (
                f"'{kod}' sözlüğünde kaynakta OLMAYAN anahtar var (ölü çeviri): {k}"
            )


def test_sozluk_dilleri_backend_ile_ayni():
    """Sözlük dosyaları `config.LANGUAGES` ile aynı kümeyi taşımalı: backend'de
    olup sözlüğü olmayan dil seçilebilir ama arayüzü çevrilemez."""
    from app.config import LANGUAGES

    diskte = {y.stem for y in (FRONTEND / "js" / "diller").glob("*.js")}
    assert diskte == set(LANGUAGES), (
        f"sözlükler {sorted(diskte)} · backend {sorted(LANGUAGES)} — ayrışmış"
    )


def test_sozluk_surum_damgasi_bumplanmis():
    """🔴 ZORUNLU KAPI. `sw.js` cache-first: damga atlanırsa düzeltilmiş çeviri
    müşteriye HİÇ ulaşmaz, üstelik testler yeşil kalır."""
    index = _oku("index.html")
    damgalar = {
        ad: int(v)
        for ad, v in re.findall(r"js/(dil\.js|diller/\w+\.js)\?v=(\d+)", index)
    }
    assert damgalar, "dil betiklerinde ?v= damgası YOK — sw.js onları sonsuza kadar önbellekte tutar"
    for ad, v in damgalar.items():
        assert v >= 1, f"{ad} damgası geçersiz: {v}"

    # Precache listesi damgalarla BİREBİR aynı olmalı: farklıysa service worker
    # başka bir URL'i saklar ve sayfanın istediği sürüm her açılışta ağa gider.
    sw = _oku("sw.js")
    for ad, v in damgalar.items():
        assert f"'/ui/js/{ad}?v={v}'" in sw, (
            f"sw.js precache'i {ad}?v={v} ile eşleşmiyor — index.html ile ayrışmış"
        )


def test_sw_cache_version_dil_degisikligini_takip_ediyor():
    sw = _oku("sw.js")
    m = re.search(r"CACHE_VERSION = 'yuki-v(\d+)'", sw)
    assert m, "CACHE_VERSION bulunamadı"
    assert int(m.group(1)) >= 248, "FAZ 2 frontend'i değiştirdi ama CACHE_VERSION bumplanmamış"
