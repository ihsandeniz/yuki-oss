"""FAZ 3 · DALGA 2 · dosya kuyruğu 2/4 — `frontend/js/core.js` (2026-09-20).

`planner.html` kuyruğun ilk dosyasıydı ve dersini ödedi: **çeviri turunun
kendisi kod kırabilir.** Orada `budgetSetCatFilter` aktif çipi METİNDEN
buluyordu; çipler çevrilince süzgeç sessizce öldü — hata yok, konsol temiz,
statik tarama kör.

`core.js`'te aynı sınıftan üç bağ vardı ve üçü de bu dosyada kapıya bağlandı:

  ① komut paleti etiketi (`/öğren`) BACKEND'de metinden tanınıyor
     (`api/websocket.py`) — etiket çevrilince komut LLM'e düz sohbet olarak
     giderdi ve kullanıcı öğrettiğini sanırdı
  ② ekran izleme paneli `active_window !== 'bilinmiyor'` diye bir SÖZLEŞME
     NÖBETÇİSİ ile süzüyor — Türkçe göründüğü için "kaçak" sanılıp
     çevrilseydi ekranda "bilinmiyor" yazan bir kaplama belirirdi
  ③ dört `toLocaleTimeString('tr-TR')` — metin çevrilse bile saat/tarih
     biçimini Türkçe bırakırdı (Blok 3'ün TR BİÇİM dersi)

Ayrıca bu dosyanın kendi arıza sınıfı: `core.js`'in yüzeylerinin çoğu JS'ten
doğuyor, yani `dil.js::ciz()` onları görmüyor → **açık ekranda dil
değiştirilince donuyorlar** (Blok 6/8/9/10'da dört kez ayrı ayrı bulundu).
`yuki-dil-degisti` tazeleyicisi burada mekanik olarak korunuyor.
"""
from __future__ import annotations

import re
from pathlib import Path

from yardim import sozluk, yorumsuz

KOK = Path(__file__).resolve().parents[2]
CORE = KOK / "frontend" / "js" / "core.js"
AMBIENT_PY = KOK / "backend" / "app" / "services" / "ambient.py"

# Bugünkü ölçüm (2026-09-20, core.js indi). YÜKSELİR, düşmez.
# Ölçü `_t(` çağrı yeri sayısı — `intro-sequences.js`'in cırcırıyla aynı
# gerekçe: dalga çok turda iniyor, mutlak kapsam kapısı bugün yazılsaydı
# dalga bitene kadar kırmızı kalır ve kırmızı kalan kapı görmezden gelinir.
# ⚠️ Kör noktası var ve kapalı: komut paletinin 48 anahtarı DİNAMİK üretiliyor
# (`'komut.' + c.ad + '.etiket'`), bu sayaca girmiyor — onların gerilemesini
# `test_komut_paletinin_HER_komutu_sozlukte_karsilik_buluyor` kapatıyor.
KANCA_TABAN = 94  # 10-04 TAM BOY + ölü #mode-toggle metinleri silindi → 6 kanca bilerek gitti (gerileme değil)


def _core() -> str:
    return yorumsuz(CORE.read_text(encoding="utf-8"))


def _tazeleyici(kod: str) -> str:
    """`yuki-dil-degisti` tazeleyicisinin GÖVDESİ.

    ⚠️ Dosyada bu olayın İKİ dinleyicisi var (biri `_applyLangUI`, biri
    tazeleyici) ve gövde sonunu aramak şart: ilk yazımda `split` bloğun
    ardındaki her şeyi de alıyordu, yani 300 satır sonra tanımlanan
    `_buildAmbientSkeleton` "tazeleyicinin içinde" sayılıyordu — kapı gerçek
    bir kusuru değil kendi kapsamını ölçüyordu.
    """
    bas = kod.index("window.addEventListener('yuki-dil-degisti', () => {")
    son = kod.index("\n});", bas)
    return kod[bas:son]


# --------------------------------------------------------------------------- #
# ① Kanca
# --------------------------------------------------------------------------- #

def test_t_kancasi_tanimli_ve_tek_kopya():
    kod = _core()
    assert len(re.findall(r"^function _t\(", kod, re.M)) == 1, "`_t()` tek kapı olmalı"
    assert "window.YukiDil.t(anahtar, degerler)" in kod, (
        "`_t()` YukiDil'e devretmiyor — kendi sözlüğünü tutan ikinci bir yol "
        "dil değişimini sessizce yarım bırakır"
    )
    assert "String(anahtar)" in kod, (
        "`_t()` bilinmeyen anahtarda ANAHTARI döndürmüyor; boş string 'kayıp "
        "metin' üretir ve ekrana bakan kimse sebebini anlamaz"
    )


def test_sarmalayici_adi_t_DEGIL_cunku_t_yerel_degisken():
    """🔴 Bu dosyada sarmalayıcı `t` OLAMAZ ve bu bir zevk meselesi değil.

    `t` burada hâlâ yerel değişken olarak kullanılıyor (`sendMessage`'da girdi
    metni, wake-word ve ambient düğümleri, `getTracks().forEach(t => …)`).
    Sarmalayıcı `t` adını alsaydı o kapsamlarda `t('x')` **sessizce** bir DOM
    düğümünü çağırmaya çalışırdı. `planner.html`'de aynı tuzak yirmi yerde,
    `intro-sequences.js`'te üç yerde çıktı.

    Kapı iki yönlü: `t` yerel olarak KULLANILMAYA devam ediyorsa (yani
    gerekçe hâlâ geçerliyse) çıplak `t('…')` çağrısı bulunmamalı.
    """
    kod = _core()
    yerel_t = re.findall(r"(?:const|let|var)\s+t\s*=|\(\s*t\s*\)\s*=>|\bt\s*=>", kod)
    assert yerel_t, (
        "`t` artık yerel değişken değil — `_t` adının gerekçesi düşmüş olabilir. "
        "Yine de yeniden adlandırma ÖLÇÜLMEDEN yapılmaz; bu testi gerekçesiyle güncelle."
    )
    # 🪤 İlk yazımda kapı YALNIZ çağrı yerlerine bakıyordu ve mutasyon turunda
    # YEŞİL kaldı: `function t(…)` eklemek hiçbir çağrıyı değiştirmez, ama
    # `core.js` klasik script olduğu için o bildirim `window.t`ye de yazılır ve
    # tuzağı kurar. Tanımın kendisi de yasak.
    assert not re.findall(r"^\s*function t\(", kod, re.M), (
        "global `function t(` var — `core.js` klasik script, bu bildirim "
        "`window.t`ye yazar ve `t`nin yerel olduğu kapsamlarda gölgelenir"
    )
    ciplak = re.findall(r"(?<![.\w_])t\(\s*'[a-z0-9_.-]+\.[a-z0-9_.-]+'", kod)
    assert not ciplak, (
        f"çıplak `t('…')` çağrısı var: {ciplak[:3]} — bu dosyada `t` bir DOM "
        "düğümü olabilir, çeviri sessizce başka bir şeye gider"
    )


def test_her_kanca_IKI_sozlukte_de_karsilik_buluyor():
    """Karşılığı olmayan anahtar ekrana ANAHTARIN KENDİSİNİ basar (`dil.js::t`
    tasarımı) — yani kusur görünür, ama ancak o yüzey açılırsa."""
    kod = _core()
    anahtarlar = set(re.findall(r"_tc?\(\s*'([a-z0-9._-]+)'", kod))
    anahtarlar |= set(re.findall(r"_t\([^)]*?\?\s*'([a-z0-9._-]+)'\s*:\s*'([a-z0-9._-]+)'", kod)[0]
                      if False else [])
    for a, b in re.findall(r"_t\([^)]*?\?\s*'([a-z0-9._-]+)'\s*:\s*'([a-z0-9._-]+)'", kod):
        anahtarlar |= {a, b}
    anahtarlar |= set(re.findall(r"k:\s*'([a-z0-9._-]+\.[a-z0-9._-]+)'", kod))          # boot adımları
    anahtarlar |= set(re.findall(r"\[\s*\d+,\s*'(amb\.[a-z0-9-]+)'\s*\]", kod))          # tarama aralıkları
    anahtarlar |= set(re.findall(r"'((?:avatar|boot)\.[a-z0-9-]+)'", kod))
    anahtarlar |= set(re.findall(r'data-i18n[a-z-]*="([a-z0-9._-]+)"', kod))
    # `'komut.' + c.ad + '.etiket'` birleştirmesinin ön eki anahtar DEĞİL;
    # tam biçimi (`alan.oge`) tutmayan her aday elenir.
    anahtarlar = {a for a in anahtarlar if re.fullmatch(r"[a-z0-9-]+\.[a-z0-9._-]+", a)}

    assert len(anahtarlar) >= 60, f"yalnız {len(anahtarlar)} anahtar bulundu — desen bozulmuş olabilir"
    for kod_dil in ("tr", "en"):
        s = sozluk(kod_dil)
        eksik = sorted(a for a in anahtarlar if a not in s)
        assert not eksik, f"{kod_dil} sözlüğünde yok: {eksik}"


def test_cevrilmis_kalem_sayisi_DUSMUYOR():
    kod = _core()
    sayi = len(re.findall(r"_tc?\(\s*'[a-z0-9_.-]+'", kod))
    assert sayi >= KANCA_TABAN, (
        f"çeviri kancası {sayi} < {KANCA_TABAN}: çevrilmiş bir metin ham hâline "
        "döndürülmüş. Bilerek yapıldıysa KANCA_TABAN gerekçesiyle güncellenir"
    )


# --------------------------------------------------------------------------- #
# ② Çeviriyle ölen kod — üç bağ
# --------------------------------------------------------------------------- #

def test_komut_ogren_oneki_BACKEND_ILE_AYNI():
    """🔴 `/öğren` iki katmanda birden yaşıyor: arayüzde bir ETİKET, backend'de
    METİNDEN tanınan bir ÖN EK. Ayrışırlarsa arıza sessizdir — kullanıcı
    komutu yazar, cümle düz sohbet olarak modele gider, beceri belleğine
    hiçbir şey yazılmaz ve hiçbir yerde hata görünmez."""
    from app.mesajlar import KATALOG

    for dil in ("tr", "en"):
        on = sozluk(dil)["komut.ogren.etiket"]
        assert KATALOG[dil]["ui.komut-ogren"] == on, (
            f"{dil}: backend ön eki {KATALOG[dil]['ui.komut-ogren']!r} ile arayüz "
            f"etiketi {on!r} ayrışmış"
        )


def test_backend_ogren_oneki_HER_DILIN_tokenini_taniyor():
    """Kullanıcı Türkçe'yken `/öğren`i öğrenip arayüzü İngilizce'ye alabilir;
    eski alışkanlığı cezalandırmanın faydası yok. Liste KATALOGDAN türetilir,
    elle yazılmaz — elle yazılan liste tam bu turda eksik kaldı."""
    from app.api.websocket import _OGREN_ONEKLERI

    for dil in ("tr", "en"):
        beklenen = sozluk(dil)["komut.ogren.etiket"].lower()
        assert beklenen in _OGREN_ONEKLERI, f"{dil} tokeni ({beklenen}) tanınmıyor"
    # Aksansız yazım tarihî davranış — ölçülmeden kaldırılmaz.
    assert "/ogren" in _OGREN_ONEKLERI


def test_ogren_yanitlari_KATALOGDAN_geliyor():
    """Örnek cümle komut tokenini ENTERPOLASYONLA alır: gömülü olsaydı
    İngilizce metin "/öğren …" diye OLMAYAN bir komutu örnek gösterirdi."""
    from app.mesajlar import M

    for dil in ("tr", "en"):
        ornek = M("ogren.ne-ogreneyim", dil=dil)
        assert sozluk(dil)["komut.ogren.etiket"] in ornek, (
            f"{dil}: örnek cümle o dilin komut tokenini içermiyor: {ornek!r}"
        )
    kod = (KOK / "backend" / "app" / "api" / "websocket.py").read_text(encoding="utf-8")
    assert "Öğrendim:" not in kod, "yanıt metni hâlâ gömülü — katalogdan gelmeli"


def test_ambient_bilinmeyen_nobetcisi_ESITLIGI():
    """`active_window !== 'bilinmiyor'` bir SÖZLEŞME, ekran metni değil.
    Backend tarafı çevrilirse süzgeç sessizce ölür ve ekranda "bilinmiyor"
    yazan bir kaplama belirir."""
    on_yuz = re.search(r"const _AMB_BILINMEYEN = '([^']+)'", _core())
    assert on_yuz, "`_AMB_BILINMEYEN` sabiti yok — nöbetçi yine satır içine gömülmüş"
    arka = re.findall(r'return "([^"]+)"', AMBIENT_PY.read_text(encoding="utf-8"))
    assert on_yuz.group(1) in arka, (
        f"frontend nöbetçisi {on_yuz.group(1)!r} backend'in döndürdüğü değerler "
        f"arasında yok — süzgeç ölü"
    )


def test_tarih_saat_bicimi_SABIT_dil_yazmiyor():
    """Metni çevirmek biçimi çevirmez: `'tr-TR'` sabiti İngilizce ekranda
    Türkçe bir ay adı/saat biçimi bırakır."""
    kod = _core()
    # Tek meşru geçiş `_yerel()`in YEDEĞİ: `YukiDil` hiç yüklenmemişse kaynak
    # dile düşmek doğru davranış. Başka her yerde sabit dil bir kusurdur.
    sabitler = re.findall(r"^.*'tr-TR'.*$", kod, re.M)
    assert len(sabitler) == 1 and "YukiDil" in sabitler[0], (
        f"`toLocale*` çağrısı hâlâ sabit 'tr-TR' taşıyor: {sabitler}"
    )
    assert len(re.findall(r"toLocale\w+\(_yerel\(\)", kod)) >= 4, (
        "`toLocale*` çağrıları `_yerel()`e bağlı değil"
    )


# --------------------------------------------------------------------------- #
# ③ Modül düzeyi sabitler — bu dalgada YEDİNCİ kez
# --------------------------------------------------------------------------- #

def test_komut_paleti_ANAHTAR_tutuyor_cozulmus_etiket_DEGIL():
    kod = _core()
    m = re.search(r"const _KOMUTLAR = \[(.*?)\n  \];", kod, re.S)
    assert m, "_KOMUTLAR tablosu bulunamadı"
    blok = m.group(1)
    assert "label:" not in blok and "hint:" not in blok, (
        "tablo hâlâ çözülmüş etiket/ipucu taşıyor — modül yüklenirken donar ve "
        "dil değişiminde eski dilde kalır"
    )
    adlar = re.findall(r"ad:\s*'([a-z]+)'", blok)
    assert len(adlar) == 18, f"18 komut bekleniyordu, {len(adlar)} bulundu"


def test_komut_paletinin_HER_komutu_sozlukte_karsilik_buluyor():
    """Cırcırın kör noktası: komut anahtarları dinamik üretiliyor
    (`'komut.' + c.ad + '.etiket'`), sayaç onları görmüyor. Burada tek tek
    ölçülüyor — eksik bir anahtar ekrana `komut.web.ipucu` diye basar.

    🔴 `doldur` ayrıca ölçülüyor: eylemi de olmayan bir komutun `doldur`
    anahtarı eksikse `_doldur()` ANAHTARI döndürür ve kullanıcının yazma
    alanına `komut.sistem.doldur` yazılır. (`planner.html`'in "ekrana kod
    basan çeviri" kusuruyla aynı sınıf.)
    """
    kod = _core()
    blok = re.search(r"const _KOMUTLAR = \[(.*?)\n  \];", kod, re.S).group(1)
    tr, en = sozluk("tr"), sozluk("en")
    for satir in blok.strip().splitlines():
        m = re.search(r"ad:\s*'([a-z]+)'", satir)
        if not m:
            continue
        ad = m.group(1)
        gerekli = [f"komut.{ad}.etiket", f"komut.{ad}.ipucu"]
        if "eylem:" not in satir and "etiketiDoldur" not in satir:
            gerekli.append(f"komut.{ad}.doldur")
        for anahtar in gerekli:
            assert anahtar in tr, f"tr sözlüğünde yok: {anahtar}"
            assert anahtar in en, f"en sözlüğünde yok: {anahtar}"


def test_komut_paleti_suzgeci_CEVRILMIS_etikete_bakiyor():
    """Süzgeç koddaki `ad`'a bakarsa İngilizce kullanıcı `/se` yazınca hiçbir
    şey eşleşmez. Ayrıca `toLowerCase()` DEĞİL `toLocaleLowerCase()`: Türkçe'de
    `I` → `ı`'dır ve `/HATIRLAT` yazan kullanıcı eşleşme kaybeder."""
    kod = _core()
    assert "_etiket(c).toLocaleLowerCase" in kod, "süzgeç çevrilmiş etikete bakmıyor"
    assert "val.toLowerCase()" not in kod, "TR 'I'→'ı' tuzağı: toLocaleLowerCase kullanılmalı"


def test_tarama_araliklari_ANAHTAR_tutuyor():
    kod = _core()
    m = re.search(r"const _AMB_INTERVALS = \[(.*?)\];", kod, re.S)
    assert m, "_AMB_INTERVALS bulunamadı"
    assert "'KAPALI'" not in m.group(1), (
        "aralık etiketi hâlâ çözülmüş — modül düzeyi sabit, dil değişiminde donar"
    )
    assert m.group(1).count("'amb.aralik-") == 4


# --------------------------------------------------------------------------- #
# ④ Dil tazeleyici — açık ekranda dil değişimi (BEŞİNCİ kez)
# --------------------------------------------------------------------------- #

def test_dil_tazeleyicisi_JS_ten_dogan_yuzeyleri_kapsiyor():
    """`dil.js::ciz()` yalnız `data-i18n` çapası taşıyan statik markup'ı
    tazeler. `core.js`'in yüzeyleri JS'ten doğuyor; tazeleyici olmazsa açık
    ekranda dil değiştiren kullanıcı bağlantı rozetini, avatar ipucunu, model
    listesini ve ekran izleme panelini ESKİ DİLDE görür."""
    kod = _core()
    kanca = re.findall(r"window\.addEventListener\('yuki-dil-degisti'", kod)
    assert len(kanca) >= 2, "dil tazeleyicisi bağlanmamış"
    govde = _tazeleyici(kod)
    for cagri in ("_setWsPill", "_avatarDurumunuUygula", "_applyViewMode",
                  "_ekipDugmesiTazele", "_syncClaudeBrainBtn", "_fillModelSheet",
                  "_wakeBannerYaz", "_ambEtiketleriTazele"):
        assert cagri in govde, (
            f"tazeleyici {cagri} çağırmıyor — o yüzey dil değişiminde donar"
        )
    # Her çağrı KENDİ kapısında: biri patlarsa kalanı yine tazelensin.
    assert govde.count("dene(") >= 8, (
        "çağrılar tek `try` içinde toplanmış — biri patlarsa kalan yüzeyler "
        "eski dilde kalır ve sebebi hiçbir yerde yazmaz"
    )


def test_ekran_izleme_paneli_dil_degisiminde_YENIDEN_KURULMUYOR():
    """🔴 Çeviri VERİYİ SİLMEMELİ. Panel `#ap-ai-text`te canlı LLM analizini,
    `#ap-img`de canlı kareyi, `#ap-help-sug`da öneriyi taşıyor;
    `_buildAmbientSkeleton()` üçünü de siler. Tazeleyici yalnız etiketleri
    yeniden çizer (`dil.js::_sahibiBizMiyiz` gerekçesinin bir kat yukarısı)."""
    kod = _core()
    tazeleyici = _tazeleyici(kod)
    assert "_buildAmbientSkeleton" not in tazeleyici, (
        "tazeleyici paneli yeniden kuruyor — canlı analiz metni ve kare silinir"
    )
    for canli in ("ap-ai-text", "ap-help-sug", "ap-live"):
        assert re.search(rf'id="{canli}"[^>]*data-i18n-yok', kod), (
            f"#{canli} `data-i18n-yok` taşımıyor — çizici canlı içeriğin üstüne yazabilir"
        )


def test_rozetin_DURUMU_saklaniyor_metni_degil():
    """Dil değişiminde rozeti yeniden çizmek için hangi durumda olduğumuzu
    bilmek gerekir. Saklanmasaydı tazeleyici CANLI yayını "bağlanıyor"
    gösterirdi — yani çeviri, ekrana YANLIŞ BİR DURUM yazdırırdı."""
    kod = _core()
    assert "let _ambSonDurum" in kod
    assert "_ambSonDurum = map[state] ? state : 'connecting'" in kod


# --------------------------------------------------------------------------- #
# ⑤ Çeviri turunun AÇABİLECEĞİ delikler
# --------------------------------------------------------------------------- #

def test_tek_tirnakli_dizgede_HAM_interpolasyon_yok():
    """🔴 `planner.html`'de bizzat yaşandı: tek tırnaklı bir dizgeye `${_t(…)}`
    yazılmıştı ve ekranda çeviri değil ham `${_t('plan.sonuc-yok')}` görünüyordu.
    `node --check` bunu YAKALAMAZ — sözdizimi geçerlidir."""
    ham = CORE.read_text(encoding="utf-8")
    kotu = re.findall(r"'[^'\n]*\$\{_t?c?\([^'\n]*'", ham)
    assert not kotu, f"tek tırnaklı dizgede şablon enterpolasyonu: {kotu[:3]}"


def test_sozlukten_gelen_metin_innerHTML_ile_BIRLESTIRILMIYOR():
    """Komut paleti ve PWA şeridi eskiden `innerHTML` + dizge birleştirmesiyle
    çiziliyordu. Metin artık sözlükten geliyor; bir çeviride `&` ya da `<`
    geçse eski kod onu işaretleme olarak yorumlardı. Aynı dosyadaki
    `_fillModelSheet` bu kararı zaten vermişti — kural istisna değil."""
    kod = _core()
    assert "'<span class=\"cmd-item-icon\">'" not in kod
    assert "'<span>Ana ekrana ekle</span>'" not in kod
    for parca in ("cmd-item-label", "cmd-item-hint"):
        assert f"'{parca}'" in kod, f"{parca} DOM API ile kurulmuyor"
