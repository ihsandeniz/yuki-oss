"""FAZ 3 · DALGA 2 — JS metinlerinin çevirisi (2026-09-19).

Dalga 1 `index.html`'i kapattı: orada her metin markup'ta duruyordu ve çizici
(`dil.js::ciz`) `data-i18n` çapalarını tarayarak çevirebiliyordu. **Bu dalgada
çapa yok.** Metin `innerHTML` şablonlarının içinde doğuyor; çizici onu göremez,
göremediğini de söylemez. Arıza sınıfı bu yüzden yeni:

    kullanıcı dili değiştirir → sekmeler İngilizce olur →
    AYAR'ın sol menüsü TÜRKÇE kalır → konsolda tek satır yok

Bu dosyanın ölçtüğü dört şey:

  ① Kanca      — `t()` var, tek kopya, ve bu dosyada GÖLGELENMİYOR
  ② Yeniden çizim — dil değişiminde JS'in ürettiği DOM tazeleniyor mu
  ③ Kademe     — kategori adı sözlükten geliyor ama TR'de backend'le AYNI
  ④ Gerileme   — çevrilmiş kalem sayısı düşmüyor (cırcır)

🔑 ④ neden cırcır: Dalga 2'nin kapsamı 460 kalem ve tek turda kapanmıyor
(`intro-sequences.js` → `planner.html` → `core.js` → `map-engine.js` → kuyruk).
"Çapasız metin 0" gibi mutlak bir kapı bugün yazılsaydı dalga bitene kadar
kırmızı kalır, kırmızı kalan kapı da bir süre sonra görmezden gelinir. O yüzden
ölçü **gerileme**: bugün çevrilmiş olan yarın çevrilmemiş olamaz. Kapsam kapısı
dalga kapandığında yazılacak (Dalga 1'in `test_index_html_capasiz_metin…`
karşılığı) ve bu cırcır o gün SİLİNECEK.
"""
from __future__ import annotations

import re
from pathlib import Path

from yardim import sozluk, yorumsuz

KOK = Path(__file__).resolve().parents[2]
FRONTEND = KOK / "frontend"
INTRO = FRONTEND / "js" / "intro-sequences.js"

# Bugünkü ölçüm (2026-09-19, Blok 1 indi). YÜKSELİR, düşmez.
# Düşürmek bir KARARDIR: bir metin artık çevrilmiyorsa gerekçesi yazılmalı.
#
# ⚠️ Ölçü `t(` ÇAĞRI sayısı DEĞİL — ilk yazımda öyleydi ve yanlıştı: menünün
# 17 anahtarı tek bir `t(x.etiket)` çağrısından geçiyor, yani 17 kalem çevirmek
# sayacı 1 artırıyor. Kapsamı temsil eden şey KANCA sayısı: doğrudan `t('…')`
# çağrıları + anahtar taşıyan veri alanları (`etiket:'hq.…'`, `grup:'hq.…'`).
#
# 🔁 Blok 6'da veri alanı listesine `ODA_AMAC` girdileri eklendi
# (`guvenlik: 'oda.amac.guvenlik'`). Sayaca girmeleri gerekiyordu çünkü tam
# olarak aynı şeyler: metnin yerine ANAHTAR tutan veri alanları. Sayılmasalardı
# dokuz oda amacını çevirmek taşı bir adım bile ilerletmezdi ve cırcır bu
# dokuzunun geri alınmasına izin verirdi.
# 🔁 Blok 7'de sayacın KENDİSİ genelleştirildi (bkz. `kanca_sayisi`): alan
# adı ve ad alanı listeleri kaldırıldı, ölçü biçimsel oldu. Aynı turda
# `PERF_KADEMELERI` ve `modes/gfx.js::TIERS` de anahtar tutmaya geçti.
# 🔁 Blok 8 (2026-09-20): 244 → 263 — 🧠 Hafıza Yöneticisi odası.
# 🔁 Blok 9 (2026-09-20): 263 → 284 — 🔊 SES & TTS odası.
# 🔁 Blok 10 (2026-09-20): 284 → 311 — 🔔 BİLDİRİM odası + Evolution.
#    ⚠️ `_EVOL_LABELS`/`_EVOL_TRAITS`in 20 elemanı bu sayaca GİRMİYOR: sayaç
#    `alan: 'anahtar'` biçimini tanıyor, çıplak dizi elemanını değil. Onların
#    gerilemesini `test_EVOL_dizileri_ANAHTAR_tasiyor` ayrıca kapatıyor —
#    yani cırcırın kör noktası var ve kapalı.
# 🔁  kuyruk 2 canlı tur ardılı (2026-09-22): 311 → 354 — lisans özeti
#    (kademe + 19 özellik etiketi anahtar taşıyor — 11'i ham kimlik basıyordu), yeniden başlatma,
#    hata günlüğü temizleme ve ayar yükleme hatası. Canlı EN turunda lisans
#    panelinde "TAM SÜRÜM · Karakter: hepsi/5 · Semantik hafıza" görülmüştü.
KANCA_TABAN = 354


def _intro() -> str:
    return yorumsuz(INTRO.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- #
# ① Kanca
# --------------------------------------------------------------------------- #

def test_t_kancasi_tanimli_ve_tek_kopya():
    """`t()` bu dosyanın çeviri kapısı. İkinci bir kopya, sözlük erişimini
    ayrıştırır — bu depoda o bedel `esc()` (3 kopya) ve `af()` (2 kopya) ile
    zaten ödendi (`DEVIR.md` kısıt ③)."""
    kod = _intro()
    tanimlar = re.findall(r"^\s*function t\(", kod, re.M)
    assert len(tanimlar) == 1, (
        f"`t()` {len(tanimlar)} kez tanımlı — tek kapı olmalı"
    )
    assert "window.YukiDil.t(anahtar, degerler)" in kod, (
        "`t()` YukiDil'e devretmiyor — kendi sözlüğünü tutan ikinci bir yol "
        "dil değişimini sessizce yarım bırakır"
    )
    assert "String(anahtar)" in kod, (
        "`t()` bilinmeyen anahtarda ANAHTARI döndürmüyor. Boş string 'kayıp "
        "metin' üretir ve ekrana bakan kimse sebebini anlamaz (dil.js::t tasarımı)"
    )


def test_t_adi_YEREL_degiskenle_golgelenmiyor():
    """🔴 Bu dalganın en sinsi tuzağı — ve bir kez yaşandı.

    `t` bu dosyada üç yerde yerel değişkendi (`var t=ent&&ent.tools` ·
    `function(t)` kademe callback'i · `var t=_hqPlatform.terminal`). O
    kapsamlarda `t('x')` yazmak `t is not a function` bile DEMEZ: `t` gerçekten
    vardır, yalnız başka bir şeydir — bir dizi ya da bir dize. Yani çeviri
    çağrısı sessizce başka bir şeye gider.

    Kapı ad listesi değil DESEN denetliyor: `t` yeniden yerel olarak
    bağlanırsa (hangi adla olursa olsun) yanar.
    """
    kod = _intro()
    ihlal = []
    for n, satir in enumerate(kod.splitlines(), 1):
        if re.search(r"^\s*function t\(", satir):
            continue                      # kancanın kendi tanımı
        if re.search(r"\b(?:var|let|const)\s+t\s*=", satir):
            ihlal.append(f"{n}: yerel `t` ataması")
        if re.search(r"function\s*\(\s*t\s*[,)]", satir):
            ihlal.append(f"{n}: `t` parametre adı")
    assert not ihlal, (
        "`t` çeviri kancası yerel bir bağlamayla gölgeleniyor — o kapsamda "
        f"çeviri sessizce yanlış şeye gider: {ihlal}"
    )


# --------------------------------------------------------------------------- #
# ② Dil değişiminde yeniden çizim
# --------------------------------------------------------------------------- #

def test_menu_dil_degisiminde_YENIDEN_ciziliyor():
    """`dil.js::ciz` yalnız statik markup'ı tarar. Bu menü `nav.innerHTML=h`
    ile JS'ten doğduğu için çizici onu bulamaz; dinleyici yazılmazsa menü
    eski dilde donar ve hata da vermez."""
    kod = _intro()
    m = re.search(r"addEventListener\('yuki-dil-degisti'.*?\}\);", kod, re.S)
    assert m, (
        "`yuki-dil-degisti` dinleyicisi yok — JS'in ürettiği menü dil "
        "değişiminde eski dilde kalır"
    )
    assert "hqMenuCiz" in m.group(0), (
        "dinleyici menüyü yeniden çizmiyor"
    )


def test_dil_olayi_dil_js_tarafindan_YAYINLANIYOR():
    """Dinleyici yazıp yayıncıyı kaybetmek, hiçbir şeyin çalışmadığı ama
    hiçbir testin de yanmadığı bir hâl üretir (`tabchange` kapısının aynı
    gerekçesi, `test_faz3_metin_cevirisi.py`)."""
    dil = yorumsuz((FRONTEND / "js" / "dil.js").read_text(encoding="utf-8"))
    assert "CustomEvent('yuki-dil-degisti'" in dil, (
        "dil.js olayı yayınlamıyor — ona bağlı her yeniden çizim sessizce ölür"
    )


# --------------------------------------------------------------------------- #
# ③ Kategori adı — sözlük önde, backend yedekte, TR'de İKİSİ AYNI
# --------------------------------------------------------------------------- #

def _backend_kategorileri() -> dict[str, str]:
    api = (KOK / "backend" / "app" / "api" / "settings_api.py").read_text(encoding="utf-8")
    return {
        m.group(1): m.group(2)
        for m in re.finditer(r'\{"id":\s*"([a-z_]+)",\s*"label":\s*"([^"]+)"', api)
    }


def test_kategori_adi_backend_ile_AYNI():
    """🔴 Çift sahiplik kapısı.

    Kategori adı iki yerde yaşıyor: `settings_api.CATEGORIES[*].label` (bugünün
    kaynağı) ve `hq.cat.*` (çeviri). Bu, geçici ve BİLİNÇLİ bir kademe —
    backend'in 1.086 metin konumu çevrilene kadar menünün yarısı Türkçe
    kalmasın diye. Ama iki kaynak ayrışırsa kullanıcı backend'i güncelleyip
    menüde eski adı görür ve sebebini hiçbir yerde bulamaz.

    O yüzden TÜRKÇE değer birebir aynı olmak zorunda: sözlük İngilizce'yi
    EKLİYOR, Türkçe'yi yeniden yazmıyor. (`intro-sequences.js::_catAd` aynı
    kademeyi koda döküyor.)
    """
    tr, en = sozluk("tr"), sozluk("en")
    kat = _backend_kategorileri()
    assert kat, "backend kategorileri okunamadı — desen bayatlamış olabilir"

    for kid, etiket in kat.items():
        anahtar = "hq.cat." + kid
        assert anahtar in tr, (
            f"'{anahtar}' tr sözlüğünde yok → menüde backend'in Türkçe adı "
            f"çizilir ve İngilizce müşteri onu görür"
        )
        assert tr[anahtar] == etiket, (
            f"{anahtar}: sözlük '{tr[anahtar]}' ≠ backend '{etiket}' — iki "
            "kaynak ayrışmış; TÜRKÇE değer backend'in label'ıdır"
        )
        assert anahtar in en, f"'{anahtar}' en sözlüğünde yok"


def test_hata_yolu_NAV_ILE_AYNI():
    """🔴 Kısıt ⑥'nın frontend hâli — Dalga 1 bunu backend'de kapatmıştı.

    Hata mesajları kullanıcıya bir arayüz yolu tarif ediyor ("AYAR → SAĞLIK →
    KOPYALA ile hata günlüğünü paylaş"). Yol cümleye sabit yazılırsa, sekme
    etiketi İngilizce'de `SETTINGS` olduğu gün mesaj **olmayan bir menüyü**
    tarif eder ve kullanıcı aradığını bulamaz.

    Yol tek anahtarda (`hata.gunluk-yolu`) ve sekme etiketiyle bağlı: `nav.ayar`
    değeri yolun İÇİNDE geçmek zorunda. Birleştirici bir yardımcı bilerek
    yazılmadı — menüdeki adlar "Sağlık" biçiminde, mesajdaki yol BÜYÜK harf; TR
    metnini birebir korumak için ayrı anahtar, ayrışmayı yasaklamak için bu kapı.
    """
    for dil in ("tr", "en"):
        s = sozluk(dil)
        assert "hata.gunluk-yolu" in s, f"{dil}: 'hata.gunluk-yolu' yok"
        yol, sekme = s["hata.gunluk-yolu"], s["nav.ayar"]
        assert sekme.lower() in yol.lower(), (
            f"{dil}: hata mesajındaki yol '{yol}' sekme etiketi '{sekme}' ile "
            "ayrışmış — mesaj olmayan bir menüyü tarif ediyor"
        )


def test_hata_mesajlari_SABIT_TR_degil():
    """`apiJson`/`agHatasi` her ağ çağrısının hata yolunda duruyor (46 çağrı
    yeri). Sabit Türkçe kalırsa İngilizce müşteri panelleri İngilizce görür ama
    bir şey bozulduğu an — tam paniklediği anda — Türkçe cümle okur."""
    kod = _intro()
    for fn, anahtar in (("apiJson", "hata.yanit-okunamadi"),
                        ("agHatasi", "hata.baglanilamadi"),
                        ("hataHtml", "hata.bilinmeyen")):
        m = re.search(rf"function {fn}\(.*?\n  \}}", kod, re.S)
        assert m, f"{fn} bulunamadı"
        assert f"t('{anahtar}'" in m.group(0), (
            f"{fn} '{anahtar}' anahtarını kullanmıyor — sabit metin kalmış olabilir"
        )


def test_catAd_bilinmeyen_anahtarda_backende_dusuyor():
    """`t()` bilinmeyen anahtarda ANAHTARI döndürür. `_catAd` bunu `if(!m)`
    ile sorsaydı sözlükte karşılığı olmayan kategori menüde
    `hq.cat.gelistirici` diye görünürdü — kullanıcıya kod sızar."""
    kod = _intro()
    m = re.search(r"function _catAd\(c\)\{(.*?)\n  \}", kod, re.S)
    assert m, "_catAd bulunamadı"
    govde = m.group(1)
    assert "m === a" in govde, (
        "_catAd çeviri yokluğunu `m === a` ile sormuyor — `!m` yazılırsa "
        "ekrana anahtar basılır (t() boş string döndürmez)"
    )
    assert "c.label" in govde, "_catAd backend adına düşmüyor"


# --------------------------------------------------------------------------- #
# ④ Gerileme cırcırı
# --------------------------------------------------------------------------- #

# Anahtar BİÇİMİ: `alan.oge` · `alan.alt.oge` — hepsi küçük harf, en az bir
# nokta. Marka adları (`'GNOME Terminal'`, `'Kitty'`) ve kimlikler (`'auto'`)
# bu kalıba UYMAZ; ayrım elle tutulan bir listeyle değil biçimle yapılıyor.
ANAHTAR_BICIMI = r"[a-z0-9]+(?:\.[a-z0-9-]+)+"


def kanca_sayisi(kod: str) -> int:
    """Çeviriye bağlanmış kalem sayısı — çağrı sayısı değil KANCA sayısı.

    İki sınıf sayılır:
      ① doğrudan `t('…')` çağrıları
      ② **anahtar taşıyan veri alanları** — `etiket:'hq.…'` · `label:'gorunum.…'`
        · `desc:'gfx.…'` gibi. Bunlar modül düzeyi sabitlerin içinde yaşıyor ve
        oraya `t()` YAZILAMAZ (dosya yüklenirken bir kez değerlenir, dil
        değişince metin donar — Blok 6'da `ODA_AMAC`, Blok 7'de
        `PERF_KADEMELERI` ile iki kez yaşandı). O yüzden anahtar tutuyorlar ve
        sayaç onları görmezse, dokuz-on kalem çevirmek taşı hiç ilerletmez.

    🔁 2026-09-19 (Blok 7): alan adı listesi (`etiket|grup`) ve ad alanı
    kısıtı (`hq.`) KALDIRILDI — her ikisi de her yeni blokta elle
    genişletilmesi gereken listelerdi ve Blok 6'da bir kez unutulmuştu.
    Artık ölçü BİÇİMSEL: bir veri alanı anahtar biçiminde bir dize taşıyorsa
    kancadır. Yanlış pozitif riski düşük çünkü kimlikler (`'auto'`, `'chat'`)
    nokta taşımaz, marka adları büyük harf/boşluk taşır.
    """
    dogrudan = len(re.findall(r"(?<![.\w])t\(\s*'[a-z0-9_.-]+'", kod))
    # `{{` / `,` de kabul ediliyor: `HQ_MENU` ve `PERF_KADEMELERI` girdileri
    # TEK SATIRDA duruyor (`{key:'auto', label:'gorunum.perf.auto'}`), satır
    # başına çapalanan bir kalıp onları GÖRMEZ — ilk yazımda tam bu oldu ve
    # sayaç 17 menü anahtarını birden kaybetti.
    veri = len(re.findall(rf"(?:^|[{{,])\s*'?[\w-]+'?:\s*'{ANAHTAR_BICIMI}'", kod, re.M))
    return dogrudan + veri


def test_cevrilmis_kalem_sayisi_DUSMUYOR():
    """Dalga 2 birden çok turda iniyor; bu kapı ilerlemeyi zorlamaz,
    **geri gitmeyi** yasaklar. Dalga kapanınca yerini kapsam kapısına bırakır."""
    sayi = kanca_sayisi(_intro())
    assert sayi >= KANCA_TABAN, (
        f"çeviri kancası {sayi} < {KANCA_TABAN}: çevrilmiş bir metin ham "
        "hâline döndürülmüş. Bilerek yapıldıysa KANCA_TABAN gerekçesiyle "
        "güncellenir"
    )


def test_HQ_MENU_etiketleri_ANAHTAR_tasiyor():
    """Menü tablosunun tamamı — tek bir ham metin kalsa o girdi İngilizce
    müşteride Türkçe görünür ve komşusu çevrilmiş olduğu için daha da göze
    batar."""
    kod = _intro()
    m = re.search(r"var HQ_MENU\s*=\s*\[(.*?)\n  \];", kod, re.S)
    assert m, "HQ_MENU tablosu bulunamadı"
    blok = m.group(1)
    tr = sozluk("tr")

    for alan in ("grup", "etiket"):
        for deger in re.findall(rf"{alan}:'([^']+)'", blok):
            assert deger.startswith("hq."), (
                f"HQ_MENU {alan}:'{deger}' ham metin — çeviri anahtarı olmalı"
            )
            assert deger in tr, f"'{deger}' tr sözlüğünde yok"


# --------------------------------------------------------------------------- #
# ⑤ BLOK 7 — modül düzeyi sabitler ve İKİNCİ TÜKETİCİ
#
# 🔴 Bu bölümün var olma sebebi, aynı tuzağın İKİ BLOKTA ÜST ÜSTE çıkması:
# `ODA_AMAC` (Blok 6) ve `PERF_KADEMELERI` (Blok 7) ikisi de modül düzeyi
# sabit. İçlerine `t()` yazmak hata VERMEZ, test de görmez — yalnız dil
# değişince metin açılıştaki dilde donar. Üçüncüsü gelmeden kapı yazıldı.
# --------------------------------------------------------------------------- #

GFX = FRONTEND / "modes" / "gfx.js"
CHAT_MODES = FRONTEND / "modes" / "chat-modes.js"

# Modül düzeyi sabit → içindeki metin alanı ANAHTAR tutmalı.
# (dosya, sabit adı, anahtar tutması gereken alanlar)
SABITLER = [
    (INTRO, "ODA_AMAC", ("llm", "ses", "guvenlik", "gelistirici")),
    (INTRO, "PERF_KADEMELERI", ("label",)),
    (GFX, "TIERS", ("label", "desc")),
    # Blok 8 (09-20): kategori rozeti tablosu. Dördüncü kez aynı sınıf —
    # modül düzeyi sabit, içinde ANAHTAR tutar, `t()` çizim anında çözer.
    (INTRO, "_MEMMGR_KAT", ("conversation", "fact", "preference", "task")),
]


def _sabit_govdesi(kaynak: str, ad: str) -> str:
    m = re.search(rf"var {ad}\s*=\s*[\[{{](.*?)[\]}}];", kaynak, re.S)
    assert m, f"`{ad}` sabiti bulunamadı — desen bayatlamış olabilir"
    return m.group(1)


def test_modul_duzeyi_sabitler_ANAHTAR_tasiyor_t_CAGIRMIYOR():
    """Sabitin içinde `t(` görülürse kapı yanar: o çağrı dosya yüklenirken
    BİR KEZ koşar ve sonucu dondurur. Doğrusu anahtar tutup çizim anında
    çözmek (`t(k.label)`)."""
    for yol, ad, alanlar in SABITLER:
        govde = _sabit_govdesi(yorumsuz(yol.read_text(encoding="utf-8")), ad)
        assert "t(" not in govde.replace("format(", ""), (
            f"{yol.name}::{ad} içinde çeviri ÇAĞRISI var — modül düzeyi sabit "
            "yüklemede bir kez değerlenir, dil değişince metin DONAR"
        )
        for alan in alanlar:
            # 🪤 `re.search` ile İLK eşleşmeye bakmak YETMEZ — mutasyon
            #    denetiminde ölçüldü: `PERF_KADEMELERI`nin ikinci kademesi
            #    ham metne döndürüldüğünde kapı YEŞİL kaldı, çünkü ilk
            #    kademe hâlâ anahtar tutuyordu. Alanın HER geçişi sınanır.
            degerler = re.findall(rf"\b{alan}\s*:\s*'([^']+)'", govde)
            assert degerler, f"{yol.name}::{ad}: '{alan}' alanı bulunamadı"
            for deger in degerler:
                assert re.fullmatch(ANAHTAR_BICIMI, deger), (
                    f"{yol.name}::{ad}.{alan} = {deger!r} — ham metin; "
                    "anahtar biçiminde (alan.oge) olmalı"
                )


def test_gfx_TIERS_in_IKINCI_tuketicisi_de_cozuyor():
    """🔴 `Gfx.TIERS` iki yerde okunuyor: AYAR ▸ Görünüm odası ve sohbetteki
    `⋯` menüsü (`chat-modes.js`). Sabit anahtara geçtiğinde ikincisi
    güncellenmezse menüde HAM ANAHTAR (`gfx.hafif.ad`) görünür — sessiz
    değil, görünür bir kusur; ama yalnız o menü açıldığında fark edilir.

    Ayrıca yardımcının adı `t` OLMAMALI: aynı dosyada `TIERS.forEach(t => …)`
    var ve düz `t` yardımcıyı gölgelerdi (bu depoda üç kez yaşandı)."""
    cm = yorumsuz(CHAT_MODES.read_text(encoding="utf-8"))
    assert re.search(r"function _t\(", cm), (
        "chat-modes.js'te `_t` yardımcısı yok — TIERS anahtarları çözülemez"
    )
    assert "window.YukiDil.t(" in cm, "`_t` YukiDil'e devretmiyor"
    assert not re.search(r"\bfunction t\(", cm), (
        "yardımcı düz `t` adıyla tanımlanmış — `TIERS.forEach(t => …)` onu "
        "gölgeler ve çeviri sessizce yanlış şeye gider"
    )
    m = re.search(r"TIERS\.forEach.*?\n(?:.*?\n){0,6}?.*?vmm-text.*?\n", cm, re.S)
    assert m and "_t(t.label)" in m.group(0) and "_t(t.desc)" in m.group(0), (
        "chat-modes.js GRAFİK bölümü `t.label`/`t.desc`'i ham basıyor — "
        "menüde anahtar görünür"
    )


def test_mod_formu_KIRLIYKEN_yeniden_cizilmiyor():
    """🔴 Dil tazeleyicisi veri kaybettirmemeli.

    `renderModeForm` alanları depodaki değerden kurar. Kullanıcı bir şey
    yazmışken çağrılırsa yazılan SESSİZCE silinir — dil değiştirmenin bedeli
    bu olamaz. Kapı, tazeleyicinin kirlilik kontrolünden geçtiğini ölçüyor.

    Karşılaştırma kaydetme yolunun toplayıcılarını (`_val`/`chipVals`)
    kullanmalı; ayrı bir okuma yazılsaydı iki yol zamanla ayrışır ve "temiz"
    denen bir form kaydedilince başka bir gövde gönderirdi."""
    kod = _intro()
    assert re.search(r"function _modFormuKirli\(", kod), (
        "`_modFormuKirli` yok — tazeleyici açık formu koşulsuz yeniden çizer"
    )
    m = re.search(r"modlar:\s*function\(\)\{(.*?)\n    \}", kod, re.S)
    assert m, "`_dilTazeleyici.modlar` bulunamadı"
    assert "_modFormuKirli()" in m.group(1), (
        "tazeleyici kirlilik kapısını sormuyor — kullanıcının yazdığı silinir"
    )
    govde = re.search(r"function _modFormuKirli\(\)\{(.*?)\n  \}", kod, re.S).group(1)
    for toplayici in ("_val(", "chipVals("):
        assert toplayici in govde, (
            f"kirlilik kontrolü `{toplayici}` kullanmıyor — kaydetme yolundan "
            "ayrı bir okuma iki gerçek üretir"
        )


# --------------------------------------------------------------------------- #
# ⑤ BLOK 8 — 🧠 Hafıza Yöneticisi (2026-09-20)
# --------------------------------------------------------------------------- #


def _memmgr_govdesi(kod: str) -> str:
    """`_memmgrRenderItem`'dan TTS bölümünün başına kadar — odanın gövdesi.

    ⚠️ Sınır YORUM başlığıyla aranmaz: gövde `yorumsuz()`'tan geçiyor ve
    "FAZ 19 — TTS PANEL" başlığı orada YOK. İlk yazımda öyleydi, sınır dosya
    sonuna kayıyor ve kapı TTS bölümünün (Blok 9) metinlerini de bu bloğa
    fatura ediyordu — yani kapı gerçekte BAŞKA bir şeyi ölçüyordu. Çapa
    koddur: `_ttsGetVoices`.
    """
    bas = kod.index("function _memmgrRenderItem")
    son = kod.index("function _ttsGetVoices", bas)
    return kod[bas:son]


def test_hafiza_rozeti_SUZGEC_ILE_AYNI_anahtari_okuyor():
    """🔴 Liste satırındaki kategori rozeti, süzgeç düğmeleriyle AYNI
    sözlük anahtarlarını okumalı.

    Eskiden backend'in ham değeri basılıyordu (`fact`) ve iki santim
    yukarıdaki süzgeç düğmesi Dalga 1'de çevrilmişti (*Gerçek*) — aynı
    ekranda aynı şeyin iki adı görünüyordu, üstelik biri hiçbir dilde
    değildi. İkinci bir sözlük açılsaydı (`hq.hafiza.rozet-*`) biri
    çevrilip öbürü unutulduğunda arıza aynen geri gelirdi.
    """
    kod = _intro()
    eslesme = dict(re.findall(r"\b(conversation|fact|preference|task)\s*:\s*'([^']+)'",
                              _sabit_govdesi(kod, "_MEMMGR_KAT")))
    assert len(eslesme) == 4, f"_MEMMGR_KAT eksik: {sorted(eslesme)}"

    markup = (FRONTEND / "index.html").read_text(encoding="utf-8")
    for kat, anahtar in eslesme.items():
        # Süzgeç düğmesi `data-scope="<kat>"` taşıyan bloğun içinde çizilir.
        blok = re.search(rf'data-scope="{kat}".{{0,400}}?data-i18n="([^"]+)"', markup, re.S)
        assert blok, f"süzgeçte '{kat}' düğmesi bulunamadı (markup değişmiş olabilir)"
        assert blok.group(1) == anahtar, (
            f"rozet '{kat}' → {anahtar!r}, süzgeç → {blok.group(1)!r}: iki yüzey "
            "aynı kategoriye iki ad veriyor"
        )


def test_hafiza_tarihi_SABIT_tr_TR_ye_bagli_DEGIL():
    """🔴 Biçim de çeviriye dahildir.

    `toLocaleDateString('tr-TR', {month:'short'})` İngilizce ekranda
    *"15 Eyl 2026"* basar — Türkçe bir ay kısaltması, hiçbir sözlükte
    olmayan bir kalem. Tarayıcı bunu GÖREMEZ çünkü kaynakta Türkçe bir
    string yok: metin çalışma anında doğuyor (Blok 3'ün "TR BİÇİM"
    dersinin dosya tarafındaki karşılığı).
    """
    govde = _memmgr_govdesi(_intro())
    assert "'tr-TR'" not in govde, (
        "hafıza odasında sabit 'tr-TR' biçimi var — dil değişince tarih Türkçe kalır"
    )
    assert "toLocaleDateString(yerelKod()" in govde, (
        "tarih `yerelKod()` (dil.js::yerel) üzerinden biçimlenmiyor"
    )


def test_yerel_eslemesi_DESTEKLENEN_her_dili_taniyor():
    """`dil.js::YEREL` sözlüklerle aynı kümeyi kapsamalı: eksik dil sessizce
    ham koda (`'ja'`) düşer ve `toLocale*` onu kabul etse de biçim
    beklenmedik olur."""
    dil_js = (FRONTEND / "js" / "dil.js").read_text(encoding="utf-8")
    m = re.search(r"var YEREL\s*=\s*\{([^}]*)\}", dil_js)
    assert m, "`YEREL` eşlemesi yok"
    kodlar = set(re.findall(r"(\w+)\s*:", m.group(1)))
    diller = {y.stem for y in (FRONTEND / "js" / "diller").glob("*.js")}
    assert diller <= kodlar, f"YEREL'de eksik dil: {sorted(diller - kodlar)}"


def test_cogul_sozlesmesi_BACKEND_Mc_ILE_AYNI():
    """`dil.js::tc` ile `mesajlar/__init__.py::Mc` aynı kuralı uygulamalı:
    `n === 1` → tekil, değilse `-cogul`, o yoksa tekile düş.

    Ayrışırlarsa aynı sayı backend mesajında "5 minutes", arayüzde
    "5 minute" olur — ve ikisini yan yana kimse görmez.
    """
    dil_js = (FRONTEND / "js" / "dil.js").read_text(encoding="utf-8")
    m = re.search(r"function tc\(anahtar, sayi, degerler\)\s*\{(.*?)\n  \}", dil_js, re.S)
    assert m, "`tc` yok — arayüzde çoğul kuralı taşınmıyor"
    govde = m.group(1)
    assert "sayi !== 1" in govde, "tc tekil/çoğul eşiğini `!== 1` ile kurmuyor"
    assert "'-cogul'" in govde, "tc `-cogul` ekini aramıyor"
    # Tekile düşüş: çoğul anahtar YOKSA `t(anahtar, …)` ile dönülmeli.
    assert re.search(r"return t\(anahtar, d\);\s*$", govde.strip()), (
        "tc, çoğul anahtar bulunmadığında tekile DÜŞMÜYOR — `ja` gibi kısmi "
        "sözlüklerde metin anahtar olarak ekrana çıkardı"
    )


def test_cogul_anahtari_YALNIZ_ingilizce_sozlukte():
    """Türkçe'de sayıdan sonra çoğul eki gelmez ("5 kayıt"). `-cogul`
    Türkçe sözlüğe girerse aynı cümlenin iki hâli oluşur ve biri bayatlar."""
    tr, en = sozluk("tr"), sozluk("en")
    assert not [k for k in tr if k.endswith("-cogul")], (
        "tr sözlüğünde `-cogul` var — Türkçe'de gereksiz, ikinci bir gerçek üretir"
    )
    coguller = [k for k in en if k.endswith("-cogul")]
    assert coguller, "en sözlüğünde hiç çoğul yok — çoğul hattı kurulmamış"
    for k in coguller:
        assert k[: -len("-cogul")] in tr, f"kökü olmayan çoğul (ölü): {k}"


def test_hafiza_odasinda_HAM_TR_metin_kalmadi():
    """Odanın gövdesinde Türkçe harf taşıyan string literal kalmamalı.

    ⚠️ Ölçü yorumsuz gövde üzerinde koşar (`yorumsuz`): bu dosyanın
    açıklamaları Türkçe ve onları saymak kapıyı kalıcı kırmızı yapardı.
    """
    govde = _memmgr_govdesi(_intro())
    kalanlar = [s for s in re.findall(r"'((?:[^'\\]|\\.)*)'", govde)
                if re.search(r"[çğıöşüÇĞİÖŞÜ]", s)]
    assert not kalanlar, f"çevrilmemiş TR metin: {kalanlar[:10]}"


def test_hafiza_ucu_HAM_TR_detail_tasimiyor():
    """🔑 Backend `detail`'i panelin bildirimine DOĞRUDAN basılıyor
    (`_memmgrHata`). Uç çevrilmezse oda "temiz" ölçülürken İngilizce
    ekranda Türkçe bir sebep belirir — Blok 4B'nin dersi: bir paneli onu
    DOLDURAN her kaynak çevrilene kadar çevrilmiş sayma."""
    kaynak = (KOK / "backend" / "app" / "api" / "memory.py").read_text(encoding="utf-8")
    ham = [d for d in re.findall(r'detail=(?:f?")([^"]*)"', kaynak)
           if re.search(r"[çğıöşüÇĞİÖŞÜ]", d)]
    assert not ham, f"memory.py'de ham TR detail: {ham}"
    assert 'from app.mesajlar import M' in kaynak, "katalog bağlanmamış"


def test_uc_hatasi_ayrintisi_BOSKEN_iki_nokta_basmiyor():
    """Eski kod `'Silinemedi: '+(d.detail||'')` yazıyordu: sebep boş
    geldiğinde ekranda sebepsiz sarkan bir ":" kalıyordu.

    🔁 Blok 9: `_memmgrHata` → `_ucHatasi`. İkinci oda (SES) ve ortak `hqSet`
    yolu aynı davranışı istedi; kopyalamak `esc()`/`af()` borcunun üçüncü
    örneği olurdu (`DEVIR.md` kısıt ③). Biçim anahtarı da ortaklaştı.
    """
    kod = _intro()
    m = re.search(r"function _ucHatasi\(anahtar, d\)\{(.*?)\n  \}", kod, re.S)
    assert m, "`_ucHatasi` yok"
    govde = m.group(1)
    assert "ortak.hata-ayrinti" in govde, "ayrıntılı dal sözlükten gelmiyor"
    # ⚠️ Desen `;` ile biter: `{mesaj: t(anahtar), …}` nesnesinin içinde de
    #    `: t(anahtar)` geçiyor ve noktalı virgülsüz bir kalıp ONU eşleştirip
    #    kapıyı boşa düşürüyordu (mutasyon denetiminde ölçüldü, kapı yeşil
    #    kaldı). Aranan şey ifadenin SONU, herhangi bir geçişi değil.
    assert re.search(r":\s*t\(anahtar\);", govde), (
        "boş sebep dalı yok — sebepsiz bir ':' ekranda sarkar"
    )


def test_suzgec_sayaci_CATEGORY_okuyor_scope_DEGIL():
    """🔴 Karede bulundu (2026-09-20), sayısal ölçüm göremedi.

    Süzgeç düğmeleri listeyi `?category=` ile filtreliyor ama sayaçlar
    `scopes`'tan besleniyordu. İki arıza birden:
      ① Her anının `scope`'u varsayılan `conversation` → "Gerçek 0 ·
        Tercih 0 · Görev 0" yazıyordu, liste doluyken.
      ② `scopes[x]` bir NESNE (`{count, avg_importance}`) → ekranda
        `[object Object]` görünüyordu.

    ②'yi tek başına düzeltmek ①'i GÖRÜNMEZ yapardı: ham nesne bariz bir
    arıza, yanlış "0" sessiz bir yalan. Kapı ikisini de tutuyor.
    """
    kod = _intro()
    m = re.search(r"window\.memmgrLoadStats\s*=\s*async function\(\)\{(.*?)\n  \};", kod, re.S)
    assert m, "`memmgrLoadStats` bulunamadı"
    govde = m.group(1)
    assert "d.categories" in govde, (
        "sayaçlar `categories` alanını okumuyor — süzgeç kategoriyle filtreliyor"
    )
    assert "d.scopes" not in govde, (
        "`scopes` hâlâ okunuyor: girdisi nesne, ekrana `[object Object]` basar"
    )
    # ⚠️ Desen veriye BAĞLI olanı arar: yalnız `"categories"` aramak, yetkisiz
    #    dalın sabit `"categories": {}` satırıyla eşleşip kapıyı boşa düşürüyordu
    #    (mutasyon denetiminde ölçüldü — uç satırı silindi, kapı yeşil kaldı).
    api = (KOK / "backend" / "app" / "api" / "memory.py").read_text(encoding="utf-8")
    assert 'data.get("categories"' in api, "uç `categories` döndürmüyor — panel hep 0 gösterir"
    for motor in ("memory.py", "memory_sqlite.py"):
        kaynak = (KOK / "backend" / "app" / "services" / motor).read_text(encoding="utf-8")
        assert '"categories"' in kaynak, (
            f"{motor} `categories` üretmiyor — uç boş sözlük döndürür, sayaçlar 0 kalır"
        )


def test_hafiza_paneli_DIL_DEGISIMINDE_tazeleniyor():
    """🔴 Canlı turda ölçüldü, kod okuyarak görünmüyordu.

    Panelin statik kabuğu `data-i18n` taşıyor, yani `dil.js::ciz` onu
    çeviriyor — ama LİSTE tamamen JS'ten doğuyor. Kayıt yazılmadan İngilizce
    ekranda rozetler *Konuşma / Gerçek / Tercih / Görev*, sayaç *"4 kayıt
    gösteriliyor"* olarak kalıyordu: panel çevrilmiş, içi Türkçe.

    `_memmgrOffset` sıfırlaması kapının parçası: offset>0 iken
    `memmgrLoadList` satırları listenin SONUNA ekler (`ekle` dalı), yani
    tazeleme listeyi ikiye katlardı.
    """
    kod = _intro()
    m = re.search(r"memmgr:\s*function\(\)\{(.*?)\n    \}", kod, re.S)
    assert m, "`_dilTazeleyici.memmgr` yok — liste dil değişiminde eski dilde donar"
    govde = m.group(1)
    assert "memmgrInit()" in govde, "tazeleyici listeyi yeniden çizmiyor"
    assert "_memmgrOffset=0" in govde.replace(" ", ""), (
        "offset sıfırlanmıyor — sayfalama açıkken tazeleme listeyi ikiye katlar"
    )
    assert "offsetParent" in govde, (
        "panel kapalıyken de çiziliyor — `switchHqTab` kapanışı haber vermez, "
        "tek fren görünürlük denetimi (HQ monitörünün dersi)"
    )


# --------------------------------------------------------------------------- #
# BLOK 9 — 🔊 SES & TTS odası (2026-09-20)
# --------------------------------------------------------------------------- #

SES_AYARLARI = ("USE_FISH_TTS", "USE_ELEVENLABS_TTS",
                "EDGE_VOICE_RATE", "EDGE_VOICE_PITCH")


def _tts_govdesi(kod: str) -> str:
    """`_ttsGetVoices`'tan Evolution bölümünün başına kadar — TTS odasının
    gövdesi. Blok 8'in sınırı buranın başına çapalıydı; ikisi karışmasın
    diye bu da KODA çapalanıyor (yorum başlıkları `yorumsuz()`ta yok)."""
    bas = kod.index("function _ttsGetVoices")
    # ⚠️ Sınır `function _evolGet` DEĞİL: Evolution'ın modül düzeyi sabitleri
    #    (`_EVOL_LABELS` · `_EVOL_TRAITS`, 20 kalem) o fonksiyondan ÖNCE
    #    geliyor ve ilk yazımda bu bloğa fatura ediliyordu — yani kapı Blok
    #    10'un işini Blok 9'dan istiyordu. Çapa bölümün İLK satırı.
    son = kod.index("'yukiEvolution'", bas)
    return kod[bas:son]


def test_ses_odasinda_HAM_TR_metin_kalmadi():
    """Odanın gövdesinde Türkçe harf taşıyan string literal kalmamalı."""
    govde = _tts_govdesi(_intro())
    kalanlar = [s for s in re.findall(r"'((?:[^'\\]|\\.)*)'", govde)
                if re.search(r"[çğıöşüÇĞİÖŞÜ]", s)]
    assert not kalanlar, f"çevrilmemiş TR metin: {kalanlar[:10]}"


def test_ses_uclari_HAM_TR_detail_tasimiyor():
    """🔑 SES odasının iki besleyicisi de `detail`ini ekrana bastırıyor:
    `hqSet` (ses seçimi → `POST /api/settings/PERSONA_VOICES`) ve TTS
    testi/yüklemesi. Uçlar çevrilmezse oda "temiz" ölçülürken İngilizce
    ekranda Türkçe bir sebep belirir (Blok 4B + Blok 8 dersi)."""
    for ad in ("tts_api.py", "settings_api.py"):
        kaynak = (KOK / "backend" / "app" / "api" / ad).read_text(encoding="utf-8")
        ham = [d for d in re.findall(r'detail=(?:f?")([^"]*)"', kaynak)
               if re.search(r"[çğıöşüÇĞİÖŞÜ]", d)]
        # ⚠️ `/settings/reset` bilerek dışarıda: o bölüm yalnız `sifirla`
        #    bölümünü ilan eden odada çizilir, SES odasının ekranında yok.
        ham = [d for d in ham if "Sıfırlama" not in d]
        assert not ham, f"{ad} içinde ham TR detail: {ham}"
        assert "from app.mesajlar import M" in kaynak, f"{ad}: katalog bağlanmamış"


def test_tts_hata_sebebi_EKRANA_ulasiyor():
    """🔴 Blok 9'da bulundu: `/tts/test` ve `/tts/reference` başarısız
    yanıtı `throw new Error(r.status)` ile karşılıyordu — backend "WAV veya
    MP3 formatı gerekli." derken ekranda `TTS hatası: Error: 415` çıkıyordu.

    Uç çevrilse bile metni kimse görmeyecekti; bu yüzden ÖNCE görünür
    yapıldı. Kapı iki şeyi birden tutar: ham durum kodu fırlatılmıyor VE
    sebep çevrilmiş biçimlendiriciden geçiyor."""
    kod = _intro()
    # ⚠️ Ölçü BU İKİ FONKSİYONLA sınırlı. `ttsLoadStatus`'un aynı satırı
    #    bilerek duruyor: onun sebebi ekrana değil zincir kutusuna düşüyor
    #    ve orada zaten çevrilmiş bir cümle + `agHatasi()` var. Kapıyı
    #    dosyanın tamamına açmak, ilgisiz bir dalı da bu bloğa fatura ederdi.
    for ad, anahtar in (("ttsTest", "hq.ses.tts-hatasi"),
                        ("ttsUploadRef", "hq.ses.yukleme-hatasi")):
        m = re.search(rf"window\.{ad}\s*=\s*async function\(\)\{{(.*?)\n  \}};",
                      kod, re.S)
        assert m, f"`{ad}` bulunamadı"
        govde = m.group(1)
        assert "throw new Error(r.status)" not in govde, (
            f"{ad}: başarısız yanıt hâlâ ham durum koduna çevriliyor — "
            "backend'in çevrilmiş sebebi ekrana ulaşmaz"
        )
        assert f"_ucHatasi('{anahtar}'" in govde, (
            f"{anahtar} `_ucHatasi` üzerinden basılmıyor"
        )


def test_ayar_satiri_SOZLUKTEN_geliyor_backende_dusuyor():
    """Satır etiketleri backend şemasında sabit Türkçe. `_ayarAd`, `_catAd`
    ile aynı kademeli sahipliği kurar: sözlük varsa o, yoksa backend.

    ⚠️ Anahtar KEBAB olmak zorunda: panel turunun "sızan anahtar" süzgeci
    `^[a-z]+\\.[a-z-]` arıyor, büyük harfli bir anahtar ekrana düşse
    görünmezdi."""
    kod = _intro()
    m = re.search(r"function _ayarAd\(s\)\{(.*?)\n  \}", kod, re.S)
    assert m, "`_ayarAd` yok — satır etiketi sözlüğe hiç sorulmuyor"
    govde = m.group(1)
    assert "'ayar.'" in govde, "anahtar ad alanı `ayar.` değil"
    assert "toLowerCase()" in govde and "replace(/_/g" in govde, (
        "anahtar kebab'a çevrilmiyor — `ayar.USE_FISH_TTS` sızan-anahtar "
        "süzgecinden kaçar"
    )
    assert "m === a" in govde, (
        "çeviri yokluğu `m === a` ile sorulmuyor — `!m` yazılırsa ekrana "
        "anahtarın kendisi basılır"
    )
    assert "s.label" in govde, "backend etiketine düşmüyor"
    assert "esc(_ayarAd(s))" in kod, "`renderSetRow` hâlâ `s.label` basıyor"


def test_ses_ayar_etiketleri_BACKEND_ile_AYNI():
    """Çift sahiplik kapısı — `test_kategori_adi_backend_ile_AYNI`'nın satır
    düzeyindeki hâli. Sözlük İngilizce'yi EKLER, Türkçe'yi yeniden yazmaz;
    ayrışırsa backend'i güncelleyen kişi ekranda eski adı görür."""
    import ast
    kaynak = (KOK / "backend" / "app" / "api" / "settings_api.py").read_text(encoding="utf-8")
    agac = ast.parse(kaynak)
    sema = None
    for dugum in ast.walk(agac):
        if isinstance(dugum, ast.AnnAssign) and getattr(dugum.target, "id", "") == "SETTINGS_SCHEMA":
            sema = ast.literal_eval(dugum.value)
    assert sema, "SETTINGS_SCHEMA okunamadı — desen bayatlamış olabilir"
    etiket = {s["key"]: s["label"] for s in sema}

    tr, en = sozluk("tr"), sozluk("en")
    for key in SES_AYARLARI:
        anahtar = "ayar." + key.lower().replace("_", "-")
        assert anahtar in tr, f"'{anahtar}' tr sözlüğünde yok → satır Türkçe kalır"
        assert tr[anahtar] == etiket[key], (
            f"{anahtar}: sözlük '{tr[anahtar]}' ≠ backend '{etiket[key]}'"
        )
        assert anahtar in en, f"'{anahtar}' en sözlüğünde yok"


def test_tts_paneli_DIL_DEGISIMINDE_tazeleniyor_AMA_aga_gitmiyor():
    """🔴 Panel `hqSelectCat` üzerinden açılıyor, yani `_dilTazeleyici.ayarlar`
    zaten koşuyor — ama o yalnız kabuğu tazeliyordu. TTS panelinin JS'ten
    doğan üç yüzeyi (zincir · not · ses ızgarası) `_ttsInited` kilidi
    yüzünden eski dilde donuyordu.

    🔑 Tazeleme AĞA GİTMEMELİ: zincir düğümleri marka adı, ses kimlikleri
    Edge TTS değeri — ikisi de dil değişince değişmez (Blok 7'nin
    `renderModesList` kararı)."""
    kod = _intro()
    assert "else _ttsCiz();" in kod, (
        "panel yeniden açıldığında yeniden çizilmiyor — dil değişiminde donar"
    )
    m = re.search(r"function _ttsCiz\(\)\{(.*?)\n  \}", kod, re.S)
    assert m, "`_ttsCiz` yok"
    govde = m.group(1)
    assert "_ttsRenderChain" in govde and "ttsRenderVoiceGrid()" in govde, (
        "tazeleyici üç yüzeyin hepsini çizmiyor"
    )
    assert "af(" not in govde and "ttsInit" not in govde, (
        "tazeleme ağa gidiyor — dil değişimi iki uç birden yokluyor"
    )
    # Not satırı çizicinin İÇİNDE olmalı: `ttsLoadStatus`ta kalsaydı yalnız
    # ağ isteğiyle tazelenirdi (bu turda bizzat taşındı).
    mc = re.search(r"function _ttsRenderChain\(chain\)\{(.*?)\n  \}", kod, re.S)
    assert mc and "tts-chain-note" in mc.group(1), (
        "`Aktif: …` notu çizicide değil — yeniden çizim onu güncelleyemez"
    )


def test_test_metni_VALUE_kancasi_tasiyor():
    """🪤 Panel turu bunu göremedi: `<input value=…>` metin düğümü değil,
    TreeWalker'a görünmez. İngilizce ekranda kutuda Türkçe bir cümle
    duruyordu ve ölçüm "0 kaçak" diyordu."""
    html = (FRONTEND / "index.html").read_text(encoding="utf-8")
    m = re.search(r"<input[^>]*id=\"tts-test-text\"[^>]*>", html, re.S)
    assert m, "`#tts-test-text` bulunamadı"
    assert 'data-i18n-value="hq.ses.test-metni"' in m.group(0), (
        "test metni kutusunun `value`si çeviri kancası taşımıyor"
    )
    dil_js = (FRONTEND / "js" / "dil.js").read_text(encoding="utf-8")
    assert "'value'" in dil_js.split("OZNITELIKLER")[1].split("]")[0], (
        "`value` çizicinin öznitelik listesinde yok — kanca sessizce ölür"
    )
    for dil in ("tr", "en"):
        assert "hq.ses.test-metni" in sozluk(dil), f"{dil}: test metni sözlükte yok"


def test_ZINCIR_yer_tutucusu_yukleme_metniyle_KARISMIYOR():
    """🪤 Dalga 1'de inmiş bir yanlış çeviri: `hq.ses.yukleniyor`
    (`#tts-chain-display`in yer tutucusu) İngilizce'ye `Uploading…` diye
    çevrilmişti. Aynı Türkçe kelimenin ("Yükleniyor…") iki ayrı anlamı tek
    anahtara binmişti; dosya yolu Blok 9'da kendi anahtarını aldı."""
    en = sozluk("en")
    assert "upload" not in en["hq.ses.yukleniyor"].lower(), (
        "zincir yer tutucusu 'Uploading…' diyor — o metin dosya yüklerken "
        "değil zincir yüklenirken çıkıyor"
    )
    assert "upload" in en["hq.ses.yukleniyor-dosya"].lower(), (
        "dosya yükleme bildirimi kendi anlamını taşımıyor"
    )


# --------------------------------------------------------------------------- #
# BLOK 10 — Evolution · hatırlatıcı · push günlüğü (2026-09-20)
# --------------------------------------------------------------------------- #

def _bildirim_govdesi(kod: str) -> str:
    """`'yukiEvolution'` çapasından dosyanın sonuna — Evolution + BİLDİRİM
    odası. Blok 9'un kapısı (`_tts_govdesi`) bu çapada BİTİYOR; ikisi
    bitişik ve örtüşmüyor."""
    return kod[kod.index("'yukiEvolution'"):]


# Modül düzeyi DİZİ sabitleri: `alan: 'değer'` deseni yok, elemanın KENDİSİ
# anahtar. `SABITLER` tablosu bunları göremezdi (Blok 7'de alan adına göre
# yazılmıştı) — ölçüyü genişletmek yerine ikinci bir biçim eklendi.
DIZI_SABITLERI = [(INTRO, "_EVOL_LABELS"), (INTRO, "_EVOL_TRAITS")]


def test_EVOL_dizileri_ANAHTAR_tasiyor():
    """🔴 BEŞİNCİ kez aynı sınıf (ODA_AMAC · PERF_KADEMELERI · gfx.TIERS ·
    _MEMMGR_KAT). `var X = [...]` dosya yüklenirken bir kez değerlenir; içine
    `t()` yazılsaydı metin o anki dilde DONARDI ve hata vermezdi."""
    kod = _intro()
    for yol, ad in DIZI_SABITLERI:
        govde = _sabit_govdesi(yorumsuz(yol.read_text(encoding="utf-8")), ad)
        assert "t(" not in govde, (
            f"{ad} içinde çeviri ÇAĞRISI var — sabit yüklemede bir kez değerlenir"
        )
        degerler = re.findall(r"'([^']+)'", govde)
        assert degerler, f"{ad}: hiç eleman yok — desen bayatlamış olabilir"
        for deger in degerler:
            assert re.fullmatch(ANAHTAR_BICIMI, deger), (
                f"{ad} = {deger!r} — ham metin; anahtar biçiminde olmalı"
            )
    # Dizi kısa kalırsa satır KAYBOLMAMALI: `_catAd`/`_ayarAd` deseninin
    # üçüncü hâli — yedek numaralı etiket.
    assert "t('evol.seviye-n'" in kod, (
        "seviye etiketi yedeksiz — `_EVOL_LABELS` kısa kalırsa boş görünür"
    )


def test_seviye_atlama_toastu_CUMLEYI_BIRLESTIRMIYOR():
    """🔑 Evolution'ın TEK canlı yüzeyi bu toast (`evolAddXP` her kullanıcı
    mesajında çağrılıyor — `core.js`). Panel ölü, toast değil.

    Cümle `karakter + ' Seviye ' + n + ' — ' + etiket` diye birleştirilseydi
    çeviri sözlüğe konsa bile SIRA kodda kilitli kalırdı (Blok 9 `hqSet`
    bildiriminin dersi)."""
    kod = _intro()
    m = re.search(r"function _evolShowLevelUp\(charKey, level\)\{(.*?)\n  \}", kod, re.S)
    assert m, "`_evolShowLevelUp` yok — desen bayatlamış olabilir"
    govde = m.group(1)
    assert "t('evol.seviye-atlandi'" in govde, "seviye cümlesi tek anahtarda değil"
    assert "tc('evol.yeni-yetenek'" in govde, (
        "yetenek satırı çoğul sözleşmesinden geçmiyor — İngilizce'de "
        "'New ability' ile 'New abilities' ayrı cümledir"
    )
    assert "' Seviye '" not in govde and "'Yeni yetenek: '" not in govde, (
        "ham TR parça hâlâ birleştiriliyor"
    )


def test_bildirim_odasinda_HAM_TR_metin_kalmadi():
    """Odanın gövdesinde Türkçe harf taşıyan string literal kalmamalı."""
    govde = _bildirim_govdesi(_intro())
    kalanlar = [s for s in re.findall(r"'((?:[^'\\]|\\.)*)'", govde)
                if re.search(r"[çğıöşüÇĞİÖŞÜ]", s)]
    assert not kalanlar, f"çevrilmemiş TR metin: {kalanlar[:10]}"


def test_bildirim_uclari_HAM_TR_detail_tasimiyor():
    """Odayı dolduran İKİ uç ailesi de `detail`ini ekrana bastırıyor:
    `/api/push/*` (gönder · düzenle · sil) ve `/api/reminders/*` (iptal).
    Uçlar çevrilmezse oda "temiz" ölçülürken İngilizce ekranda Türkçe bir
    sebep belirir (Blok 4B + 8 + 9 dersi, dördüncü kez)."""
    for ad in ("push.py", "tools_api.py"):
        kaynak = (KOK / "backend" / "app" / "api" / ad).read_text(encoding="utf-8")
        ham = [d for d in re.findall(r'detail=(?:f?")([^"]*)"', kaynak)
               if re.search(r"[çğıöşüÇĞİÖŞÜ]", d)]
        assert not ham, f"{ad} içinde ham TR detail: {ham}"
        assert "from app.mesajlar import M" in kaynak, f"{ad}: katalog bağlanmamış"


def test_hatirlatici_bildirimi_KATALOGDAN_geliyor():
    """🔴 `_fire_reminder` metni ÜÇ yere birden gidiyor: sohbet balonu,
    telefon bildirimi ve `push_notifications` tablosu — yani BİLDİRİM
    odasının listesi. Sabit `"Hatırlatma: "` öneki İngilizce ekranda her
    satırda görünüyordu ve panel turu bunu GÖREMİYORDU (liste boşken
    ölçülüyor)."""
    kaynak = (KOK / "backend" / "app" / "services" / "scheduler.py").read_text(encoding="utf-8")
    assert 'M("hatirlatici.bildirim"' in kaynak, "bildirim metni katalogdan gelmiyor"
    assert 'f"Hatırlatma: {message}"' not in kaynak, "sabit TR önek duruyor"


def test_hatirlatici_araligi_KAYDA_YAZILMIYOR_OKUMADA_kuruluyor():
    """🔴 `her 20 dakikada` cümlesi `reminders.json`'a YAZILIYORDU: kullanıcı
    hatırlatıcıyı Türkçe arayüzdeyken kurduysa, arayüzü İngilizce'ye alsa
    bile o satır sonsuza kadar Türkçe kalıyordu — kaydın kendisi bir dil
    seçimi taşıyordu. `_EVOL_LABELS`'in depo katmanındaki eşi.

    Yapı (`interval`) zaten kayıtlıydı; eksik olan onu kullanmaktı."""
    import importlib
    sch = importlib.import_module("app.services.scheduler")
    assert sch.insan_aralik({"minutes": 20}, dil="en") == "every 20 minutes"
    assert sch.insan_aralik({"minutes": 20}, dil="tr") == "her 20 dakikada"
    # n == 1 ayrı CÜMLEDİR, sayısı değişen aynı cümle değil.
    assert sch.insan_aralik({"hours": 1}, dil="en") == "every hour"
    assert sch.insan_aralik({"hours": 1}, dil="tr") == "her saatte"
    assert sch.insan_aralik(None) is None and sch.insan_aralik({}) is None

    kaynak = (KOK / "backend" / "app" / "services" / "scheduler.py").read_text(encoding="utf-8")
    m = re.search(r"def list_reminders\(\).*?\n    return out", kaynak, re.S)
    assert m and "insan_aralik(r.get(\"interval\"))" in m.group(0), (
        "`list_reminders` diskteki donmuş metni olduğu gibi döndürüyor"
    )
    assert 'or r.get("human")' in m.group(0), (
        "eski kayıtlar için yedek yok — 09-20 öncesi hatırlatıcıların aralığı "
        "boş görünür (kayıt KAYBOLMAZ, yalnız çevrilemez)"
    )


def test_yukleme_hatasi_ISIM_EKLEYEREK_cumle_KURMUYOR():
    """🔴 Eski `_yuklemeHatasi(e, 'hatırlatıcılar')` cümleyi ismi büyük harfe
    çevirip birleştiriyordu. İki arıza:
      ① İngilizce'de "Reminders could not be loaded" sırası TR'ninkiyle aynı
         değil — çeviri sözlüğe konsa bile sıra kodda kilitli kalırdı.
      ② `charAt(0).toUpperCase()` Türkçe'de 'i' → 'I' basar ('İ' değil).
         Bugün iki isim de 'h'/'b' ile başlıyor, yani kusur GÖRÜNMÜYORDU."""
    kod = _intro()
    m = re.search(r"function _yuklemeHatasi\(e, on\)\{(.*?)\n  \}", kod, re.S)
    assert m, "`_yuklemeHatasi` imzası değişmiş — ikinci parametre anahtar ÖN EKİ olmalı"
    govde = m.group(1)
    assert "charAt(0).toUpperCase()" not in govde, (
        "isim hâlâ büyük harfe çevrilip cümleye ekleniyor"
    )
    assert govde.count("t(on + '-") == 3, "üç durumun üçü de ayrı tam cümle değil"
    tr, en = sozluk("tr"), sozluk("en")
    for on in ("hq.bildirim.hatirlatici", "hq.bildirim.gecmis"):
        for son in ("-kilitli", "-yuklenemedi-http", "-yuklenemedi"):
            assert on + son in tr and on + son in en, f"{on}{son} sözlükte eksik"


def test_bildirim_paneli_DIL_DEGISIMINDE_tazeleniyor():
    """🔴 `_dilTazeleyici`de `pushlog` YOKTU: oda açıkken dil değiştirilince
    kabuk çevriliyor (`data-i18n`), JS'ten doğan iki liste eski dilde
    kalıyordu — üstelik ikisi de TARİH biçimi taşıyor.

    🔑 SES odasından farklı olarak AĞA GİTMESİ doğru: satırların kaynağı
    sunucu ve elde tutulan ham kopya yok."""
    kod = _intro()
    m = re.search(r"var _dilTazeleyici = \{(.*?)\n  \};", kod, re.S)
    assert m, "`_dilTazeleyici` bulunamadı"
    tablo = m.group(1)
    assert re.search(r"\n    pushlog: function\(\)\{", tablo), (
        "BİLDİRİM odası tazeleyici tablosunda yok — açık panel donar"
    )
    govde = re.search(r"pushlog: function\(\)\{(.*?)\n    \}", tablo, re.S).group(1)
    assert "offsetParent" in govde, (
        "görünürlük denetimi yok — panel kapalıyken de ağa gidilir "
        "(`switchHqTab` panel kapanışını haber vermez)"
    )
    assert "pushlogInit" in govde, "iki listeden yalnız biri tazeleniyor"


def test_bildirim_tarihi_SABIT_tr_TR_ye_bagli_DEGIL():
    """🪤 `iso.replace('T',' ').slice(0,16)` dilden bağımsız GÖRÜNÜR ama
    değildir: ISO sırası (YYYY-MM-DD) bir biçim seçimidir ve iki arayüzde de
    aynı kalıyordu. Biçim de çeviriye dahildir (Blok 8, `yerel()` dersi)."""
    kod = _intro()
    m = re.search(r"function _zamanMetni\(iso\)\{(.*?)\n  \}", kod, re.S)
    assert m, "`_zamanMetni` yok — tarih biçimi hâlâ elle kesiliyor"
    assert "yerelKod()" in m.group(1), "biçim sabit bir dile bağlı"
    govde = _bildirim_govdesi(kod)
    assert "replace('T',' ')" not in govde.replace(" ", ""), (
        "ISO kesme hâlâ kullanılıyor"
    )
    # 🪤 Ölçüm ilk yazımda `govde.count(...) == 2` diyordu ve KIRMIZI yandı —
    #    ürün doğruydu: `_zamanMetni`in TANIMI da bu aralığın içinde ve üçüncü
    #    eşleşmeyi o üretiyordu. Tanımı düşür, çağrı yerlerini say.
    cagrilar = govde.count("_zamanMetni(") - len(
        re.findall(r"function _zamanMetni\(", govde))
    assert cagrilar == 2, (
        f"iki listeden (hatırlatıcı + bildirim kartı) yalnız biri yerelleşmiş "
        f"({cagrilar} çağrı)"
    )


def test_pushlog_OZNITELIKLERI_tirnak_kacisli_esc_kullaniyor():
    """🔴 GÜVENLİK — çeviri turunda bulundu. `_esc()` gövdesi
    `textContent`→`innerHTML` idi; o serileştirme `&`, `<`, `>` kaçırır ama
    **tırnağı kaçırmaz**. Üç değer de `value="…"` özniteliğine giriyordu,
    yani içinde `"` geçen bir başlık özniteliği kapatıp kendi olay kancasını
    yazabilirdi.

    🪤 Değerler kullanıcının yazdığıyla SINIRLI DEĞİL: hatırlatıcı
    bildirimlerinin gövdesi LLM'in ürettiği metinden doğuyor
    (`scheduler._fire_reminder` → `push_notifications.body`) — CLAUDE.md
    § Bağlam Hijyeni kural 6b'nin tam vakası."""
    kod = _intro()
    assert "function _esc(" not in kod, (
        "`_esc` geri gelmiş — tırnak kaçırmayan ikinci bir kaçış fonksiyonu"
    )
    assert "_esc(" not in kod, "`_esc` çağrısı kalmış"
    govde = _bildirim_govdesi(kod)
    # Öznitelik içine giren her enterpolasyon `esc()`ten geçmeli.
    # 🔑 2026-09-27 (GELEN KUTUSU): düzenleme formu (`curTitle/curBody/curUrl`)
    #    söküldü — günlük artık düzenlenmiyor. Ölçü formdan ÖZNİTELİKLERE taşındı:
    #    kayıt metni (LLM'den doğar) ve alarm mesajı (kullanıcıdan) hâlâ `title="…"`
    #    ve `data-id="…"` içine giriyor.
    ozler = re.findall(r"""(?:title|data-id)="'\s*\+\s*([^+]+?)\s*\+""", govde)
    assert len(ozler) >= 3, f"öznitelik ölçüsü boş döndü — desen değişmiş ({ozler})"
    for oz in ozler:
        assert oz.startswith(("esc(", "Number(")), f"öznitelik kaçışsız: {oz!r}"
    assert "function esc(s)" in kod and '.replace(/"/g,\'&quot;\')' in kod, (
        "`esc` tırnağı kaçırmıyor — öznitelik bağlamı güvenli değil"
    )


def test_ayar_etiketlerinin_TAMAMI_BACKEND_ile_AYNI():
    """Blok 9 mekanizmayı kurup yalnız `ses` kategorisinin 6 satırını
    çevirmişti. Bu kapı ŞEMANIN TAMAMINI ister: yeni bir ayar eklenip
    sözlüğe yazılmazsa satır Türkçe kalır ve kimse fark etmez.

    Çift sahiplik kuralı aynı: sözlük İngilizce'yi EKLER, Türkçe'yi
    yeniden yazmaz."""
    import ast
    kaynak = (KOK / "backend" / "app" / "api" / "settings_api.py").read_text(encoding="utf-8")
    sema = None
    for dugum in ast.walk(ast.parse(kaynak)):
        if isinstance(dugum, ast.AnnAssign) and getattr(dugum.target, "id", "") == "SETTINGS_SCHEMA":
            sema = ast.literal_eval(dugum.value)
    # 09-27: 36→35 — NEWS_WATCHER_INTERVAL_MIN (haber izleyici söküldü)
    # 10-17: 35→31 — yerel TTS (3) + geliştirici araçları (1) açık kaynaktan çıktı
    assert sema and len(sema) >= 31, "SETTINGS_SCHEMA okunamadı ya da küçüldü"

    tr, en = sozluk("tr"), sozluk("en")
    eksik, ayrik = [], []
    for s in sema:
        anahtar = "ayar." + s["key"].lower().replace("_", "-")
        if anahtar not in tr or anahtar not in en:
            eksik.append(anahtar)
        elif tr[anahtar] != s["label"]:
            ayrik.append(f"{anahtar}: sözlük {tr[anahtar]!r} ≠ backend {s['label']!r}")
    assert not eksik, f"sözlükte olmayan ayar etiketi (satır TR kalır): {eksik}"
    assert not ayrik, f"çift sahiplik ayrışmış: {ayrik}"


def test_SIFIRLA_bolumu_sozlukten_geliyor():
    """Blok 9'un ikinci açık maddesi. Bölüm yalnız `sifirla` ilan eden odada
    çizildiği için SES odasının ekranında yoktu ve ölçüm onu hiç görmedi."""
    kod = _intro()
    for anahtar in ("oda.sifirla-bas", "oda.sifirla-metin", "oda.sifirla-dugme"):
        assert f"t('{anahtar}')" in kod, f"{anahtar} koda bağlanmamış"
        for dil in ("tr", "en"):
            assert anahtar in sozluk(dil), f"{dil}: {anahtar} sözlükte yok"
    kaynak = (KOK / "backend" / "app" / "api" / "settings_api.py").read_text(encoding="utf-8")
    assert '"Sıfırlama başarısız"' not in kaynak, "reset ucu hâlâ ham TR"
