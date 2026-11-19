"""FAZ 3 — metin çevirisi (2026-09-18).

FAZ 2 çeviri **iskelesini** kurmuştu (`YukiDil.t()`); bu faz metinleri taşıyor.
Dalga 1 kapsamı: `frontend/index.html` (379 anahtar) + arayüz yoluna atıf
yapan backend mesajları (`app/mesajlar/`).

Bu dosyanın ölçtüğü beş şey — hepsi "unutulursa SESSİZ kalan" sınıftan:

  ① Kapsam    — çapasız, dil-nötr olmadığı ilan edilmemiş metin KALDI mı
  ② Kanca     — `data-i18n` / `data-i18n-html` doğru yerde mi (yanlış kanca
                JS'in doldurduğu düğümü siler)
  ③ Parite    — `en` sözlüğü `tr`'yi tam kapsıyor mu · `ja` kapsamı DÜŞTÜ mü
  ④ FOUT      — çizici ilk `<script src>` bloğundan ÖNCE çağrılıyor mu
  ⑤ Kısıt ⑥   — backend mesajlarındaki arayüz etiketi frontend'le aynı mı

🔴 ① neden en önemlisi: ilk tarama "bu metin Türkçe mi?" diye soruyordu
(diakritik VEYA sözlük). O soru `Tercih` · `Modlar` · `DEPREM` gibi ~70 kalemi
kaçırdı — hepsi Türkçe, hiçbiri iki kapıdan geçmiyor. Burada soru tersine
çevrildi: **harf taşıyan her metin çevrilir**, istisna `NOTR`'da tek tek ilan
edilir. Böylece "kaçırdık mı" sorusu göz kararı olmaktan çıkıp mekanik oldu.
"""
from __future__ import annotations

import ast
import html
import re
from html.parser import HTMLParser
from pathlib import Path

KOK = Path(__file__).resolve().parents[2]
FRONTEND = KOK / "frontend"
BACKEND_APP = KOK / "backend" / "app"

DILLER = ("tr", "ja", "en")
KAYNAK = "tr"

# `ja` kapsamının TABANI — cırcır kapısı. Kapsam kararı "yalnız en" (2026-09-18),
# yani `ja` bilerek kısmi. Bu sayı DÜŞERSE test kırmızı yanar: gecikme görünür
# kalır, sessizce büyüyemez. Japonca çeviri geldiğinde bu sayı YÜKSELTİLİR.
JA_TABAN = 4


# --------------------------------------------------------------------------- #
# Dil-NÖTR metinler — çeviri kapsamının dışı, tek tek ilan edilmiş
# --------------------------------------------------------------------------- #
# Buraya bir şey eklemek "çevirmeyeceğiz" kararıdır ve gerekçesi olmalı:
#   marka/ürün adı · teknik kısaltma/birim · borsa kodu · veri kaynağı özel adı ·
#   kaynakta zaten İngilizce olan HUD etiketi · yer tutucu/süsleme
# ⚠️ Türkçe bir NİTELEME özel adın parçası DEĞİLDİR: "GDELT Askeri" buraya
#    girmez, çünkü "Askeri" çevrilir; "NASA FIRMS" girer.
NOTR = {
    # marka · ürün · sürüm
    "Yuki", "YUKI", "YUKI // AI COMPANION", "UNIT // YUKI",
    # Ayar sekmesinin köşe etiketi (sekme başlığı tek tarz, 11-13) — ürün adı, her dilde aynı
    "YUKI HQ",
    # 11-14: eski açılış sinematiği (opening-anim.js) silindi, sahte terminal kodları listeden düştü;
    # yeni açılışın (acilis-v4) metinleri sözlükte (acilis.*).
    "OK",
    "GPT-4.1", "Claude", "Edge TTS",
    # sekme adları — vitrinde ve klavye kısayolunda bu adlarla geçiyorlar
    # 11-13 : PANEL sekmesi kalktı → "PANEL"/"[5] PANEL" listeden düştü.
    "CHAT", "PLAN", "MAP", "[1] CHAT", "[2] PLAN", "[4] MAP",
    # HUD / durum — kaynakta zaten İngilizce
    # 10-04 ( MAP "HARİTA ÖNCE"): haritanın Yuki portresi, SİSTEM kartı ve
    # metinli araç düğmeleri kalktı → oradaki durum kodları listeden düştü
    # (ölü istisna kapısı aşağıda). Araçlar artık SVG simge + çevrilen aria-label.
    "MEM", "EMO", "NEUTRAL", "SYS", "NET", "UPTIME",
    "● LIVE", "◈ TIMELINE", "MIN MAG",
    "EO", "FLIR", "NV", "CRT",
    # donanım / teknik kısaltma · birim
    "CPU", "RAM", "GPU", "PID", "THR", "MB/s", "↑ MB/s", "CPU%", "PM2.5",
    "LAT", "LON", "LAT — · LON —", "Kp", "· ISS", "POI",   # 11-13 harita Gözlemevi: yer kartında "· Kp" yerine "· ISS"
    "CCTV", "ADSB", "ADS-B", "ISS",
    # 10-04: 3D başlığı + sayaçları (TACTICAL 3D, EQ/FIRE/…) artık `harita.h3d.*` ile çevriliyor.
    # (piyasa kodları 10-04'te PİYASA kartıyla birlikte gitti)
    # 3D görünüm düğmesi — teknik kısaltma, her dilde aynı ("◈ 3D" simgesi kalktı)
    "3D",
    # veri kaynağı ÖZEL ADI
    "NASA FIRMS", "NASA EONET", "NASA NeoWs", "OpenAQ PM2.5",
    # yer tutucu / süsleme
    "/", "—", "·",
}

CEVRILIR_OZNITELIK = {"placeholder", "title", "alt", "aria-label"}
ATLANAN_ETIKET = {"script", "style"}
GOVDESIZ = {"br", "img", "input", "hr", "meta", "link", "source", "track"}


def _oku(*parcalar: str) -> str:
    return FRONTEND.joinpath(*parcalar).read_text(encoding="utf-8")


def _sozluk(kod: str) -> dict[str, str]:
    metin = _oku("js", "diller", f"{kod}.js")
    govde = metin.split("= {", 1)[1]
    ham = re.findall(r"^\s*'((?:[^'\\]|\\.)*)':\s*'((?:[^'\\]|\\.)*)',\s*$", govde, re.M)
    coz = lambda s: s.replace("\\'", "'").replace("\\\\", "\\")  # noqa: E731
    return {coz(k): coz(v) for k, v in ham}


class _Tarayici(HTMLParser):
    """Çapası OLMAYAN metin ve öznitelikleri toplar.

    `data-i18n-html` bir elemanı kapatır: içindeki her şey o anahtarın
    gövdesidir, ayrıca çapa beklemeyiz. `data-i18n-yok` da kapatır — o,
    "metnini JS yazıyor" ya da "içeriği dil-nötr" beyanıdır.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.atla = 0
        self.yigin: list[bool] = []
        self.kalan: list[tuple[str, str]] = []
        self.capalar: list[tuple[str, str]] = []   # (öznitelik, anahtar)
        self.i18n_cocuklu: list[str] = []          # data-i18n + eleman çocuğu
        self.html_js_dugumlu: list[str] = []       # data-i18n-html + id/onclick çocuk
        self._i18n_derinlik: list[str | None] = []
        self._html_derinlik: list[str | None] = []

    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        if tag in ATLANAN_ETIKET:
            self.atla += 1
            return
        ust_kapali = self.yigin[-1] if self.yigin else False
        kapali_oz = "data-i18n-yok" in d

        for ad, deger in attrs:
            if ad.startswith("data-i18n-") and ad[len("data-i18n-"):] in CEVRILIR_OZNITELIK:
                self.capalar.append((ad, deger))
            elif ad in ("data-i18n", "data-i18n-html") and deger:
                self.capalar.append((ad, deger))
            if (ad in CEVRILIR_OZNITELIK and deger and not ust_kapali
                    and not kapali_oz and f"data-i18n-{ad}" not in d):
                self.kalan.append(("attr:" + ad, re.sub(r"\s+", " ", deger).strip()))

        # `data-i18n` (textContent) taşıyan elemanın ELEMAN ÇOCUĞU olamaz
        if self._i18n_derinlik and self._i18n_derinlik[-1] is not None:
            self.i18n_cocuklu.append(self._i18n_derinlik[-1])
        # `data-i18n-html` içinde id/onclick taşıyan düğüm olamaz
        if self._html_derinlik and self._html_derinlik[-1] is not None:
            if "id" in d or "onclick" in d:
                self.html_js_dugumlu.append(self._html_derinlik[-1])

        if tag not in GOVDESIZ:
            self.yigin.append(ust_kapali or kapali_oz or "data-i18n" in d
                              or "data-i18n-html" in d)
            self._i18n_derinlik.append(d.get("data-i18n"))
            self._html_derinlik.append(d.get("data-i18n-html")
                                       if "data-i18n-html" in d
                                       else (self._html_derinlik[-1]
                                             if self._html_derinlik else None))

    def handle_endtag(self, tag):
        if tag in ATLANAN_ETIKET:
            self.atla = max(0, self.atla - 1)
            return
        for depo in (self.yigin, self._i18n_derinlik, self._html_derinlik):
            if depo:
                depo.pop()

    def handle_data(self, veri):
        if self.atla or (self.yigin and self.yigin[-1]):
            return
        metin = re.sub(r"\s+", " ", veri).strip()
        # 🔴 2026-09-19 (Dalga 2): ölçü `{2}` idi — **ARDIŞIK** iki harf. O
        # hâliyle kapı "çapasız metin 0" diyordu ve ALTI kalem gerçekten
        # çevrilmemişti: `1S` `24S` `7G` (geçmiş aralığı: Saat/Gün) ve
        # `1s` `1g` `1h` (dönem seçicisi: saat/gün/HAFTA). Hiçbiri iki ardışık
        # harf taşımıyor, yani "metin değil" sayılıp taranmıyordu.
        #
        # Bunlardan biri canlı arızaydı: `1h` Türkçe'de "1 hafta"dır, ama
        # İngilizce okuyan müşteri "1 hour" olarak okur ve 1 saatlik veri
        # sandığı yerde 1 haftalık aralık açar.
        #
        # 📏 Ders: *"0 kalem" bir ÖLÇÜMÜN sonucudur ve ölçümün kör noktası
        # kadar doğrudur.* Kapı mutasyonla sınanmıştı; sınanmayan şey ölçünün
        # NEYİ GÖRMEDİĞİYDİ. Ölçü artık TOPLAM harf sayıyor, ardışıklık
        # aramıyor — tek harfli meşru birimler (`W` · `°C` · `G`/`M`) `NOTR`'da
        # tek tek ilan ediliyor.
        if metin and re.search(r"[A-Za-zÇĞİÖŞÜçğıöşü]", metin):
            self.kalan.append(("metin", metin))


def _tara(sayfa: str) -> _Tarayici:
    t = _Tarayici()
    t.feed(_oku(sayfa))
    t.close()
    return t


# --------------------------------------------------------------------------- #
# ① Kapsam
# --------------------------------------------------------------------------- #

def test_index_html_capasiz_metin_birakmiyor():
    """Çevrilmemiş metin bir DEĞERDEN değil, GÖZDEN kaçar. Kapı bunu mekanikleştirir.

    Kırmızı yanarsa iki seçenek var: kalemi çevir (`data-i18n*` ekle) ya da
    dil-nötr olduğunu `NOTR`'da **gerekçesiyle** ilan et. Üçüncü seçenek yok.
    """
    t = _tara("index.html")
    kalan = [(tur, m) for tur, m in t.kalan if m not in NOTR]
    assert not kalan, (
        f"{len(kalan)} kalem çevrilmemiş ve nötr ilan edilmemiş:\n"
        + "\n".join(f"  {tur:16s} {m[:90]}" for tur, m in kalan[:25])
    )


# `planner.html`'in KENDİ nötr listesi — PLAN ekranı ayrı bir belge ve ayrı bir
# alan sözlüğü taşıyor (birim · tuş adı · İngilizce egzersiz örneği). `NOTR`'la
# birleştirilmedi: oradaki bir kalemin ölü kalıp kalmadığını ölçen kapı
# `index.html`'e bakıyor, birleşseydi PLAN'a özgü istisnalar orada "ölü" görünür
# ve kapı kendi kendine boşa düşerdi.
PLANNER_NOTR = {
    # sayfa başlığı — sekme adı (NOTR'da zaten `PLAN`) + marka
    "PLAN — Yuki",
    # teknik/marka adı — İngilizce'de de aynı yazılır
    "POMODORO",
    # birim · para birimi simgesi (bütçe TRY cinsinden tutulur, çevrilmez)
    "₺", "kcal", "kg",
    # sayısal yer tutucu — harf taşımıyor, öznitelik taraması yine de görür
    "90", "0",
    # klavye tuşu — tuşun üstünde ne yazıyorsa o
    "N", "L", "SPC", "Del",
}


def test_planner_html_capasiz_metin_birakmiyor():
    """PLAN ekranı `index.html` DEĞİL — kendi belgesi, kendi kapısı.

    Bu kapı 2026-09-20'ye kadar YOKTU ve o gün ölçüldüğünde `planner.html`
    **sıfır** `data-i18n` taşıyordu: 4.226 satırlık ekranın tamamı ham
    Türkçeydi. Dalga 1 `index.html`'i kapatmış, kapı da yalnız onu ölçtüğü için
    boşluk bir gün bile kırmızı yanmamıştı.

    📏 Ders: *bir kapının yeşili, YALNIZ baktığı dosya kadar geniştir.*
    """
    t = _tara("planner.html")
    kalan = [(tur, m) for tur, m in t.kalan if m not in NOTR and m not in PLANNER_NOTR]
    assert not kalan, (
        f"{len(kalan)} kalem çevrilmemiş ve nötr ilan edilmemiş:\n"
        + "\n".join(f"  {tur:16s} {m[:90]}" for tur, m in kalan[:25])
    )


def test_planner_notr_listesi_gercekten_kullaniliyor():
    kaynak = html.unescape(_oku("planner.html"))
    olu = [m for m in PLANNER_NOTR if m not in kaynak]
    assert not olu, f"PLANNER_NOTR'da karşılığı kalmamış kalem: {sorted(olu)}"


def test_planner_kancalari_YAPISAL_olarak_dogru():
    """`data-i18n` çocuklu elemana, `data-i18n-html` id/onclick taşıyan düğüme
    yazılırsa çizim ekranı SİLER — ikisi de hata vermez."""
    t = _tara("planner.html")
    assert not t.i18n_cocuklu, (
        f"data-i18n taşıyan elemanın eleman çocuğu var: {sorted(set(t.i18n_cocuklu))}"
    )
    assert not t.html_js_dugumlu, (
        f"data-i18n-html içinde id/onclick düğümü var: {sorted(set(t.html_js_dugumlu))}"
    )


def test_planner_ciz_BUYUK_betikten_ONCE_ve_govde_sonunda_cagriliyor():
    """`planner.html`'in bloklayan betiği gövdenin ORTASINDA (satır ~929, 3.270
    satırlık satır içi blok). Çizim yalnız gövde sonunda olsaydı tarayıcı o
    bloğu ayrıştırırken üstteki markup'ı Türkçe boyayabilirdi.

    İki çağrı da gerekli: erken olan görev/bütçe/fitnes markup'ını, geç olan
    büyük betikten SONRA gelen mobil alt şeridi çevirir.
    """
    metin = _oku("planner.html")
    cagri = [m.start() for m in re.finditer(r"YukiDil\.ciz\(document\)", metin)]
    assert len(cagri) >= 2, (
        f"planner.html {len(cagri)} senkron çizim çağrısı taşıyor, en az 2 gerek"
    )
    buyuk = metin.find("// ── YEREL GÜN / DAKİKA")
    assert buyuk > 0, "büyük betik bloğunun çapası bulunamadı — test boşa düşmüş olabilir"
    mobil = metin.find('id="mobile-nav"')
    assert mobil > 0, "mobil şerit çapası bulunamadı"
    assert cagri[0] < buyuk, "ilk çizim çağrısı büyük betikten SONRA → üst markup Türkçe boyanabilir"
    assert cagri[-1] > mobil, "son çizim çağrısı mobil şeritten ÖNCE → alt şerit çevrilmez"


def test_notr_listesi_gercekten_kullaniliyor():
    """Ölü istisna, yanlış bir güven verir: liste 'düşündük' izlenimi bırakır
    ama karşılığı ekranda yoktur. Kaynakta hiç geçmeyen bir nötr ilanı, bir
    kalemin silindiğini ya da yeniden yazıldığını gösterir."""
    # `convert_charrefs=True` ile tarayıcı entity'leri ÇÖZÜYOR, yani `NOTR`
    # çözülmüş metinle eşleşir (`S&P500`). Bu kapı ham kaynakta arıyordu ve
    # kaynakta `S&amp;P500` yazıyor → meşru bir istisna "ölü" görünüyordu.
    kaynak = html.unescape(_oku("index.html"))
    olu = [m for m in NOTR if m not in kaynak]
    assert not olu, f"NOTR'da karşılığı kalmamış kalem: {sorted(olu)}"


# --------------------------------------------------------------------------- #
# ② Kanca doğruluğu
# --------------------------------------------------------------------------- #

def test_data_i18n_elemani_eleman_cocugu_tasimiyor():
    """`data-i18n` → `textContent = t(k)`. Elemanın çocuğu varsa o atama
    çocukları SİLER. Böyle bir yerde `data-i18n-html` kullanılmalı ya da
    çıplak metin kendi `<span>`'ine sarılmalı (FAZ 3'ün 'önce yeniden yaz'
    adımı tam olarak budur)."""
    t = _tara("index.html")
    assert not t.i18n_cocuklu, (
        "data-i18n taşıyan eleman(lar)ın eleman çocuğu var — çizim onları siler: "
        f"{sorted(set(t.i18n_cocuklu))}"
    )


def test_data_i18n_html_js_dugumu_silmiyor():
    """`data-i18n-html` → `innerHTML = t(k)`. İçinde `id=` ya da `onclick=`
    taşıyan bir düğüm varsa o düğüm her dil değişiminde yok edilir; JS'in
    `getElementById` ile doldurduğu canlı değer (ör. `#mon-cpu-temp`) kaybolur.
    Bu kanca YALNIZ sunumsal satır-içi markup için."""
    t = _tara("index.html")
    assert not t.html_js_dugumlu, (
        "data-i18n-html içinde id/onclick taşıyan düğüm var — innerHTML onu siler: "
        f"{sorted(set(t.html_js_dugumlu))}"
    )


def test_her_capa_sozlukte_karsilik_buluyor():
    """Anahtarı sözlükte olmayan çapa ekrana ANAHTARIN KENDİSİNİ basar
    (`dil.js::t` tasarımı). Çökmez — yani gözle bakılmazsa fark edilmez."""
    tr = _sozluk("tr")
    for sayfa in ("index.html", "planner.html"):
        t = _tara(sayfa)
        eksik = sorted({a for _, a in t.capalar if a not in tr})
        assert not eksik, f"{sayfa}: sözlükte karşılığı olmayan çapa: {eksik}"


# --------------------------------------------------------------------------- #
# ③ Parite
# --------------------------------------------------------------------------- #

def test_en_sozlugu_tr_yi_TAM_kapsiyor():
    tr, en = _sozluk("tr"), _sozluk("en")
    assert tr, "kaynak sözlük boş"
    assert not (set(tr) - set(en)), f"en'de eksik: {sorted(set(tr) - set(en))[:20]}"
    # `-cogul` İngilizce'ye ÖZGÜ — Türkçe'de sayıdan sonra çoğul eki gelmez
    # ("5 kayıt"), İngilizce'de gelir ("5 records"). Backend kapısının
    # (`test_backend_en_katalogu_tr_yi_kapsiyor`) tanıdığı istisnanın aynısı;
    # frontend'de 2026-09-20'ye kadar hiç çoğul metin olmadığı için yazılmamıştı.
    fazla = {k for k in set(en) - set(tr) if not k.endswith("-cogul")}
    assert not fazla, f"en'de fazla (ölü): {sorted(fazla)[:20]}"
    for k in set(en) - set(tr):
        # Kökü olmayan çoğul = ölü anahtar; istisna kapıyı boşaltmamalı.
        assert k[: -len("-cogul")] in tr, f"karşılıksız çoğul: {k}"


def test_ja_kapsami_DUSMUYOR():
    """`ja` bilerek kısmi (kapsam kararı: yalnız `en`). Kapı çeviriyi
    zorlamıyor — **gerilemeyi** yasaklıyor. Gecikme kayıtlı olduğu sürece
    dürüsttür; sessizleştiği an bayat belgeye dönüşür."""
    tr, ja = _sozluk("tr"), _sozluk("ja")
    kapsam = len(set(ja) & set(tr))
    assert kapsam >= JA_TABAN, (
        f"ja kapsamı düştü: {kapsam} < {JA_TABAN}. Anahtar silindiyse geri koy; "
        "bilerek azaltılıyorsa JA_TABAN'ı gerekçesiyle güncelle."
    )
    assert not (set(ja) - set(tr)), f"ja'da ölü anahtar: {sorted(set(ja) - set(tr))}"


# --------------------------------------------------------------------------- #
# ④ FOUT — çizici ne zaman koşuyor
# --------------------------------------------------------------------------- #

def test_ciz_ilk_betik_blogundan_ONCE_cagriliyor():
    """Çizici gövdenin sonunda kalsaydı tarayıcı, ayrıştırmayı durduran ilk
    `<script src=…>` bloğunda o ana kadarki markup'ı BOYAYABİLİRDİ → İngilizce
    kullanıcı her açılışta bir Türkçe flaş görürdü. `tema.js:7-9`'un FOUC
    gerekçesinin metin hâli."""
    metin = _oku("index.html")
    i_ciz = metin.find("YukiDil.ciz(document)")
    assert i_ciz > 0, "index.html senkron `ciz(document)` çağrısı taşımıyor"
    i_betik = metin.find('<script src="/ui/js/bildirim.js')
    assert i_betik > 0, "çapa betiği bulunamadı — test kendi kendine boşa düşmüş olabilir"
    assert i_ciz < i_betik, (
        "çizici ilk bloklayan betikten SONRA çağrılıyor → ilk kare Türkçe boyanabilir"
    )


def test_ciz_gövde_sonunda_da_cagriliyor():
    """Erken çağrı yalnız kendinden ÖNCEKİ markup'ı çevirir; harita panelleri,
    galeri seçici ve `#nav-fab` ondan sonra geliyor."""
    metin = _oku("index.html")
    son = metin.rindex("YukiDil.ciz(document)")
    assert son > metin.find("<script src=\"/ui/js/intro-sequences.js"), (
        "gövde sonundaki ikinci çizim çağrısı yok — geç gelen markup çevrilmez"
    )


def test_core_js_dil_basligini_ARTIK_yazmiyor():
    """`#lang-baslik` artık `data-i18n="dil.baslik"` taşıyor, sahibi çizici.
    `_applyLangUI` de yazsaydı aynı alanın iki sahibi olurdu — bu depoda o
    arıza sınıfı `data-theme`/`data-tema` ile bir kez ödendi (core.js:1-14)."""
    kod = _yorumsuz(_oku("js", "core.js"))
    assert "lang-baslik" not in kod, (
        "core.js hâlâ #lang-baslik'e yazıyor — çizici ile çift sahiplik"
    )


def test_lang_label_cizicinin_disinda():
    """`#lang-label` SEÇİLİ DİLİN ADI; sunucunun `available` listesinden gelir.
    Çizici sahiplenseydi İngilizce'ye geçen kullanıcı düğmede sözlükteki sabit
    değeri ("Turkish") görürdü."""
    metin = _oku("index.html")
    m = re.search(r'<span id="lang-label"[^>]*>', metin)
    assert m, "#lang-label bulunamadı"
    assert "data-i18n-yok" in m.group(0), (
        "#lang-label `data-i18n-yok` taşımıyor — çizici dinamik değeri ezer"
    )


def _yorumsuz(js: str) -> str:
    """`//` ve `/* */` sıyırıcı (FAZ 2'den devralındı).

    Gerekçe ölçülmüş: bu depoda kaldırılan kusurlar gerekçeleriyle YORUMDA
    alıntılanıyor. Ham metinde arayan kapı kendi açıklamasına takılır —
    FAZ 1'de ve FAZ 2'de birer kez tam olarak bu oldu.
    """
    js = re.sub(r"/\*.*?\*/", " ", js, flags=re.S)
    return "\n".join(s for s in js.splitlines() if not s.lstrip().startswith("//"))


# --------------------------------------------------------------------------- #
# ⑤ Önbellek kapısı — sözlük değişti, damga bumplandı mı
# --------------------------------------------------------------------------- #

def test_sozluk_damgasi_HER_SAYFADA_bumplanmis():
    """`sw.js` cache-first. FAZ 2'nin kapısı yalnız `index.html`'i ölçüyordu;
    `planner.html` ayrı bir belge ve kendi `?v=` damgalarını taşıyor — orada
    unutulursa PLAN ekranı eski sözlükle koşar ve kimse fark etmez."""
    damgalar = {}
    for sayfa in ("index.html", "planner.html"):
        metin = _oku(sayfa)
        bulunan = dict(re.findall(r"js/(dil\.js|diller/\w+\.js)\?v=(\d+)", metin))
        assert bulunan, f"{sayfa}: dil betiklerinde ?v= damgası yok"
        for ad, v in bulunan.items():
            damgalar.setdefault(ad, {})[sayfa] = v

    for ad, sayfa_damga in damgalar.items():
        assert len(set(sayfa_damga.values())) == 1, (
            f"{ad} damgası sayfalar arasında ayrışmış: {sayfa_damga}"
        )

    sw = _oku("sw.js")
    for ad, sayfa_damga in damgalar.items():
        v = next(iter(sayfa_damga.values()))
        assert f"'/ui/js/{ad}?v={v}'" in sw, (
            f"sw.js precache'i {ad}?v={v} ile eşleşmiyor"
        )
    m = re.search(r"CACHE_VERSION = 'yuki-v(\d+)'", sw)
    assert m and int(m.group(1)) >= 249, "FAZ 3 frontend'i değiştirdi, CACHE_VERSION bumplanmamış"


# --------------------------------------------------------------------------- #
# ⑥ Backend kataloğu ve KISIT ⑥ (backend ↔ frontend eşzamanlılığı)
# --------------------------------------------------------------------------- #

BAGLANAN_DOSYALAR = [
    "hata_yaniti.py",
    "main.py",
    "api/todo.py",
    "api/chat.py",
    "services/startup_validator.py",
    "services/llm.py",
    "services/tools/ui_tools.py",
]


def test_backend_en_katalogu_tr_yi_kapsiyor():
    from app.mesajlar import KATALOG

    tr, en = KATALOG["tr"], KATALOG["en"]
    assert not (set(tr) - set(en)), f"en katalogda eksik: {sorted(set(tr) - set(en))}"
    # Tek meşru fazlalık: çoğul biçimler. TR'de sayıdan sonra çoğul eki gelmez,
    # EN'de gelir → `-cogul` yalnız gereken dilde tanımlanır (bkz. `Mc`).
    fazla = {k for k in set(en) - set(tr) if not k.endswith("-cogul")}
    assert not fazla, f"en katalogda ölü anahtar: {sorted(fazla)}"
    for k in set(en) - set(tr):
        assert k[: -len("-cogul")] in tr, f"karşılıksız çoğul: {k}"


def test_arayuz_etiketi_cumleye_GOMULMEMIS():
    """🔴 Bağlayıcı kısıt ⑥'nın mekanik hâli.

    Mesajlardaki arayüz yolu (*"⚙ AYAR → 🔑 ANAHTAR"*) cümleye sabit yazılırsa,
    frontend `AYAR`'ı `SETTINGS` yaptığı gün mesaj **olmayan bir menüyü** tarif
    eder. Etiket tek yerde (`ui.*`) durmalı ve `{ui_…}` ile girmeli.
    """
    from app.mesajlar import KATALOG

    etiketler = {"AYAR", "SETTINGS", "ANAHTAR", "SAĞLIK", "HEALTH", "LİSANS", "LICENCE"}
    for dil, katalog in KATALOG.items():
        for anahtar, metin in katalog.items():
            if anahtar.startswith("ui."):
                continue
            for e in etiketler:
                assert e not in metin, (
                    f"{dil}:{anahtar} arayüz etiketini cümleye gömmüş ({e!r}) — "
                    "`ui.*` anahtarını {ui_…} ile çağır"
                )


def test_baglanan_dosyalarda_ham_arayuz_yolu_KALMADI():
    """Katalog kurulduktan sonra bağlanan dosyalarda gömülü arayüz yolu kalırsa
    mesaj iki kaynaktan gelir ve biri çevrilmez. Yorumlar hariç — onlar
    kullanıcıya gitmez (AST zaten yorumu görmez)."""
    for goreli in BAGLANAN_DOSYALAR:
        yol = BACKEND_APP / goreli
        agac = ast.parse(yol.read_text(encoding="utf-8"))
        docstringler = set()
        for dugum in ast.walk(agac):
            if isinstance(dugum, (ast.Module, ast.ClassDef, ast.FunctionDef,
                                  ast.AsyncFunctionDef)):
                govde = getattr(dugum, "body", [])
                if (govde and isinstance(govde[0], ast.Expr)
                        and isinstance(govde[0].value, ast.Constant)
                        and isinstance(govde[0].value.value, str)):
                    docstringler.add(id(govde[0].value))
        for dugum in ast.walk(agac):
            if (isinstance(dugum, ast.Constant) and isinstance(dugum.value, str)
                    and id(dugum) not in docstringler):
                assert "⚙ AYAR" not in dugum.value and "⚙ SETTINGS" not in dugum.value, (
                    f"{goreli}:{dugum.lineno} arayüz yolu hâlâ gömülü: {dugum.value[:60]!r}"
                )


def test_ui_ayar_etiketi_FRONTEND_ILE_AYNI():
    """Katalogdaki `ui.ayar` ile frontend'in sekme etiketi (`nav.ayar`) aynı
    kelimeyi söylemek ZORUNDA. İkisi ayrı dosyada yaşıyor; ayrışmalarını
    engelleyen tek şey bu kapı."""
    from app.mesajlar import KATALOG

    for dil in ("tr", "en"):
        sekme = _sozluk(dil)["nav.ayar"]
        backend = KATALOG[dil]["ui.ayar"]
        assert backend.endswith(sekme), (
            f"{dil}: backend '{backend}' ile frontend sekmesi '{sekme}' ayrışmış"
        )


def test_ja_backend_ingilizceye_dusuyor():
    """Frontend `dil.js::YEDEK` ile aynı kural. Japonca konuşan kullanıcıya
    Türkçe göstermek, İngilizce göstermekten kötüdür."""
    from app.mesajlar import KATALOG, M

    assert "ja" not in KATALOG, "ja kataloğu eklendiyse bu testin gerekçesi değişti"
    assert M("llm.ulasilamadi", dil="ja") == KATALOG["en"]["llm.ulasilamadi"]


def test_bilinmeyen_anahtar_ANAHTARIN_KENDISINI_dondurur():
    """Boş string 'kayıp metin' üretir ve ekrana bakan kimse sebebini anlamaz;
    anahtar görünürse kusur kendini söyler (frontend `t()` ile aynı tasarım)."""
    from app.mesajlar import M

    assert M("olmayan.anahtar") == "olmayan.anahtar"


# --------------------------------------------------------------------------- #
# AYAR sekmesi çökmesi (FAZ 3'ün ürünü DEĞİL, ama FAZ 3'ü görünmez
# kılıyordu: 127 HQ anahtarı o panelin içinde)
# --------------------------------------------------------------------------- #

def test_switchTab_tanimsiz_intel_fonksiyonu_CAGIRMIYOR():
    """`switchTab('hq')` → `intelPollStatus is not defined` → ekran boşalıyordu.

    Kök neden: `intel*` ailesi kişisel Alice'in `js/hq-monitor.js`'inde tanımlı
    ve o dosya ürüne BİLEREK taşınmadı (ürün CLAUDE.md § HQ). `map-engine.js`
    aynı blokta dört `intel*` çağrısı yapıyordu; **ikisi korumalı, ikisi çıplak**
    — yani taşıma yarım bırakılmış. AYAR Free kademede olduğu için her müşteriyi
    vuruyordu.

    Kapı, "o iki adı düzelt" demiyor: taşınmamış bir aileden gelen HER çağrının
    korumalı olmasını istiyor. Yarın beşinci bir `intel*` eklenirse yine yanar.
    """
    kaynak = _yorumsuz((FRONTEND / "js" / "map-engine.js").read_text(encoding="utf-8"))
    ciplak = []
    for n, satir in enumerate(kaynak.splitlines(), 1):
        for m in re.finditer(r"(?<![.\w])(intel\w+)\s*\(", satir):
            ad = m.group(1)
            if f"typeof {ad}" in satir or f"function {ad}" in satir:
                continue
            ciplak.append(f"{n}: {ad}")
    assert not ciplak, (
        "map-engine.js taşınmamış `intel*` ailesini KORUMASIZ çağırıyor — "
        f"switchTab ortasında kesilir ve ekran boşalır: {ciplak}"
    )


def test_map_engine_sekme_yonlendirmesini_GOLGELEMIYOR():
    """🔴 AYAR sekmesinin hiç açılmamasının asıl sebebi.

    `tab-nav.js:683` `window.switchTab = sekmeGec` atıyor ve görünürlüğü
    `hidden` özniteliğiyle yönetiyor (`kabuk.css:434` sözleşmesi,
    `temel.css:183` `!important`). `map-engine.js` `index.html`'de ondan SONRA
    yükleniyor; tepesinde bir **üst düzey `function switchTab` bildirimi**
    varken hoisting o atamayı eziyordu ve kazanan eski sürüm yalnız
    `style.display` yazıyordu → tıklama hata vermiyor, panel de açılmıyor.

    🔑 Kapı "bu üç adı yazma" demiyor — **bildirim ile süsleyiciyi** ayırıyor:
      · üst düzey `function switchTab(...)`  → GÖLGE, yasak
      · `window.switchTab = function(...)`   → yalnız önceki değeri YAKALAYIP
        çağırıyorsa meşru (süsleyici deseni; haritanın tembel kurulumu böyle)
    Ayrım şart: yasak listesi yazsaydık meşru süsleyici de kırmızı yanardı ve
    biri onu "testi geçmek için" bozardı.
    """
    kaynak = _yorumsuz((FRONTEND / "js" / "map-engine.js").read_text(encoding="utf-8"))
    satirlar = kaynak.splitlines()

    golge = [ad for ad in ("switchTab", "switchTabFromDropdown", "toggleTabDropdown")
             if re.search(rf"^function\s+{ad}\s*\(", kaynak, re.M)]
    assert not golge, (
        f"map-engine.js üst düzey bildirimle tab-nav.js'i gölgeliyor: {golge} — "
        "yönlendirmenin tek sahibi tab-nav.js olmalı"
    )

    yazan = [n + 1 for n, s in enumerate(satirlar)
             if re.match(r"\s*window\.switchTab\s*=", s)]
    assert not yazan, (
        f"map-engine.js:{yazan} `window.switchTab`'e yazıyor. Sarmalamak bile "
        "yanlış: `sekmeGec` gövdesini View Transition callback'inde, BİR SONRAKİ "
        "FRAME'de koşturuyor — sarmalayıcı `origSwitch(tab)` dönüşünde panel hâlâ "
        "`hidden`'dır ve ölçtüğü her şey yanlış çıkar (Leaflet 0 yükseklikli kapta "
        "kurulur, üstelik HATA VERMEZ). Doğru kanca `tabchange` olayıdır."
    )


def test_tab_nav_urunun_TUM_sekmelerini_tanir():
    """Gölgeleme kalkınca yönlendirmenin tek sahibi `tab-nav.js`. O yüzden
    ürünün altı sekmesinin hepsi onun listesinde olmak zorunda: eksik kalan
    bir sekme artık hiçbir yerden açılamaz (eski dosya yedeğe düşmüyor)."""
    kod = _yorumsuz((FRONTEND / "js" / "tab-nav.js").read_text(encoding="utf-8"))
    for sekme in ("chat", "planner", "hq", "map", "ajan", "yedek", "galeri", "dosya"):   # 11-13: panel yok, yedek var
        assert f"ad: '{sekme}'" in kod, f"tab-nav.js '{sekme}' sekmesini tanımıyor"


def test_sekme_yan_etkileri_tabchange_KANCASINDAN_besleniyor():
    """Sekmeye bağlı yan etkiler (harita tembel kurulumu, duvar kâğıdı, portal
    kanvası) `switchTab`'i sarmalayarak DEĞİL, `tabchange` olayını dinleyerek
    bağlanır. Sebep yukarıdaki kapıda: sarmalayıcı bir frame erken koşar.

    Kapı ayrıca olayın YAYINLANDIĞINI da denetliyor — dinleyici yazıp yayıncıyı
    silmek, hiçbir şeyin çalışmadığı ama hiçbir testin de yanmadığı bir hâl
    üretirdi (`duvar.js` bu olaya bağlı)."""
    nav = _yorumsuz((FRONTEND / "js" / "tab-nav.js").read_text(encoding="utf-8"))
    assert "CustomEvent('tabchange'" in nav, (
        "tab-nav.js `tabchange` olayını yayınlamıyor — ona bağlı her kanca sessizce ölür"
    )
    for dosya in ("map-engine.js", "duvar.js"):
        kod = _yorumsuz((FRONTEND / "js" / dosya).read_text(encoding="utf-8"))
        assert "addEventListener('tabchange'" in kod, f"{dosya} tabchange dinlemiyor"
