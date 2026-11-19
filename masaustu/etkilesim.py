"""Masaüstü Yuki — arayüzle etkileşim: saf karar modülü (GTK'siz, test edilebilir).

NEDEN VAR: kullanıcı 10-25 ~21:00 (iki ekran görüntüsü): Yuki ana penceredeki PANEL'in üst kenarına bacak bacak üstüne
oturur, giriş çubuğunun üstüne dirseğine dayanıp uzanır, arada kendi kendine el sallar. Bu modül yalnız karar verir;
pencere/WebKit çağrısı host'ta (`yuki_govde.YukiTamGovde`).

Çapa zinciri:
  ön yüz (`frontend/js/masaustu-capa.js`) PANEL (`#hr-side`) ve giriş hapının (`#giris-hap`) getBoundingClientRect'ini
  CSS px olarak `/ws/realtime`'a `{type: "masaustu_capa"}` yollar → backend aynen yayınlar → `baglanti.py` buraya
  (`capa_dogrula`). Electron penceresi Wayland'de kendi ekran konumunu bilemez (README § Neden Electron değil);
  konumu ve boyu pencere kaynağından (`pencere_json`) okunur. Ölçek = istemci boyu / görünüm (vw, vh): zoom
  ya da kesirli ölçek varsa da doğru.
Kararlar:
  - `capa_ekran`: CSS kutusu → global mantıksal px (monitör koordinatı, Gdk ile aynı).
  - `capa_sec` / `yakin_capa`: Yuki ayakta dururken hangi çapanın yanında (bir panelin önünde → otur, çubuğun sağ
    ucunda → uzan). 2. tur: paneller = PANEL + açık pencere-paneller (AKIŞ…); sürükleyip bırakınca
    geniş bölgeyle HEMEN yapışır (`EtkilesimHost.yapis`), sığmıyorsa balonla nedenini söyler.
  - `poz_yeri`: pozun temas noktası çapaya otursun diye katman marjı; ekran dışına taşıyorsa ya da çubuk boyu
    taşımıyorsa None + neden (şef 21:42: "çubuk taşımıyorsa uzanma").
  - `Planlayici`: ne sıklıkla (açılışta 20–50 sn'de bir "merhaba" selamı, uyanıkken 45–110 sn'de bir, uykudayken
    3–6 dk'da bir uyanıp el sallar; poza 3–7 sn yakın bekleyince; pozda 60–180 sn; sonra 40–120 sn ara). Etkileşim
    (tık, sürükle) sayaçları erteler; uykuda poza girmez. Uyku 60 sn'de geldiği için uykuda selam olmasaydı el sallama
    pratikte hiç görülmezdi (canlıya alma 7 incelemesi: ilk selamın ≤110 sn'de gelme olasılığı ≈%23).
"""
from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass, field

SINIF = "yuki"                # ana Yuki penceresinin pencere-kaynağındaki sınıfı
CAPA_TAZE_SN = 12.0           # ön yüz 5 sn'de bir tazeler; bundan eskiyse pencere kapandı/gizlendi say
CAPA_EN = 20000               # CSS px üst sınırı (bozuk/kötü niyetli değer)
PANEL_EN_COK = 12             # `paneller` listesinden en çok bu kadarı alınır
# Oturma noktası panelin soldan %62'si: bacak bacak üstü pozda baldırlar sarkıyor. PANEL'de
# yazılar/simgeler solda, ◀ sağ üstte; 1900×1015 taramasında %55–70 aralığında bacaklar bunlara 0 px biniyor
# (%20'de 1190 px, %75'te 151 px). Eskiden Yuki'nin durduğu yere en yakın nokta seçiliyordu.
OTUR_ORAN = 0.62
# Uzanma pozu KAPALI: 1280×800'de uzanan Yuki durum satırını örtüyordu (daily 10-26).
# Çubuk çapa adayı olmaz, `gir("uzan")` geri çevrilir; poz kodu (`web/poz.js`) yerinde — geri açmak için True.
UZAN_ACIK = False


# ── çapa iletisi ─────────────────────────────────────────────────────────
def _kutu(v) -> tuple[float, float, float, float] | None:
    if not isinstance(v, (list, tuple)) or len(v) != 4:
        return None
    try:
        x, y, w, h = (float(t) for t in v)
    except (TypeError, ValueError):
        return None
    if not all(math.isfinite(t) for t in (x, y, w, h)) or w < 24 or h < 8 or w > CAPA_EN or h > CAPA_EN \
            or abs(x) > CAPA_EN or abs(y) > CAPA_EN:
        return None
    return x, y, w, h


def capa_dogrula(olay: dict) -> dict | None:
    """`masaustu_capa` iletisi → {"vw", "vh", "panel", "cubuk", "paneller"} ya da None. Kutu yoksa/bozuksa o çapa None.

    paneller: açık pencere-paneller (AKIŞ, HAFIZA…); bozuk kutu atlanır. Eski ön yüz/backend
    göndermezse boş demet: yalnız PANEL'e oturulur (geri uyumlu).
    """
    if not isinstance(olay, dict) or olay.get("type") != "masaustu_capa":
        return None
    try:
        vw, vh = float(olay.get("vw")), float(olay.get("vh"))
    except (TypeError, ValueError):
        return None
    if not (100 <= vw <= CAPA_EN and 100 <= vh <= CAPA_EN):
        return None
    pl = olay.get("paneller")
    paneller = tuple(k for k in (_kutu(v) for v in (pl[:PANEL_EN_COK] if isinstance(pl, list) else [])) if k)
    return {"vw": vw, "vh": vh, "panel": _kutu(olay.get("panel")), "cubuk": _kutu(olay.get("cubuk")),
            "paneller": paneller}


# ── pencere kaynağı ─────────────────────────────────────────────────────
def pencere_json(komut: str) -> list | dict | None:
    """Ana Yuki penceresinin ekran konumunu veren kaynak (`clients` / `monitors`). Platformdan bağımsız, güvenli bir
    kaynak YOK (Wayland başka pencerenin konumunu vermez; pencere denetimi bu kopyaya girmez) → None: çapa ekrana
    çevrilemez, panele oturma/el sallama tetiklenmez, Yuki ayakta kalır. Testler ve ileride bir kaynak `pencere=` verir."""
    return None


def istemci_bul(istemciler, sinif: str = SINIF) -> dict | None:
    """Ana Yuki penceresi: sınıf eşleşen, eşlenmiş, gizli olmayan; birden çoksa (site pencereleri) en büyüğü."""
    if not isinstance(istemciler, list):
        return None
    adaylar = [c for c in istemciler if isinstance(c, dict) and c.get("class") == sinif
               and c.get("mapped", True) and not c.get("hidden")]
    if not adaylar:
        return None
    return max(adaylar, key=lambda c: (c.get("size") or [0, 0])[0] * (c.get("size") or [0, 0])[1])


def gorunur_mu(istemci: dict, monitorler) -> bool:
    """İstemcinin çalışma alanı kendi monitöründe şu an açık mı (normal ya da özel/scratchpad alan)."""
    ws = (istemci.get("workspace") or {}).get("id")
    for m in monitorler if isinstance(monitorler, list) else []:
        if m.get("id") != istemci.get("monitor"):
            continue
        return ws is not None and ws in ((m.get("activeWorkspace") or {}).get("id"),
                                         (m.get("specialWorkspace") or {}).get("id"))
    return False


def capa_ekran(capa: dict, istemci: dict) -> dict:
    """CSS kutuları → global mantıksal px kutuları {"panel": (x,y,w,h)|None, "cubuk": …, "paneller": (…)}."""
    at, boy = istemci.get("at") or [0, 0], istemci.get("size") or [0, 0]
    sx, sy = boy[0] / capa["vw"], boy[1] / capa["vh"]
    cevir = lambda k: (round(at[0] + k[0] * sx), round(at[1] + k[1] * sy), round(k[2] * sx), round(k[3] * sy))  # noqa: E731
    out = {ad: (cevir(capa[ad]) if capa.get(ad) else None) for ad in ("panel", "cubuk")}
    out["paneller"] = tuple(cevir(k) for k in capa.get("paneller") or ())
    return out


def paneller(ekran: dict | None) -> list:
    """Oturulabilecek kutular: önce PANEL (`#hr-side`), sonra açık pencere-paneller (aynı kutu iki kez sayılmaz)."""
    if not ekran:
        return []
    out = [ekran["panel"]] if ekran.get("panel") else []
    out += [k for k in ekran.get("paneller") or () if k not in out]
    return out


def capa_izle(eski: tuple, adaylar: list) -> tuple | None:
    """Pozdayken oturulan panelin yeni kutusu: aynı boyda (±6 px) olanlardan en az kayanı; yoksa (kapandı) None."""
    ayni = [k for k in adaylar if abs(k[2] - eski[2]) <= 6 and abs(k[3] - eski[3]) <= 6]
    return min(ayni, key=lambda k: abs(k[0] - eski[0]) + abs(k[1] - eski[1])) if ayni else None


# ── yer ──────────────────────────────────────────────────────────────────
def yakin_capa(yuki: tuple[int, int, int, int], ekran: dict | None) -> str | None:
    """Ayaktaki Yuki (global kutu x, y, w, h) hangi çapanın yanında: 'otur' | 'uzan' | None (bkz. `capa_sec`)."""
    a = capa_sec(yuki, ekran)
    return a[0][0] if a else None


def capa_sec(yuki: tuple[int, int, int, int], ekran: dict | None, genis: bool = False) -> list:
    """Ayaktaki Yuki (global kutu x, y, w, h) için aday çapalar [(ad, kutu), …], en uygunu önde.

    Dar (kendiliğinden poz, genis=False):
      otur: orta çizgisi bir panelin eni içinde ve panelin üst kenarı bedeninin alt %75'inde (önünde duruyor).
      uzan: orta çizgisi çubuğun sağ yarısıyla sağ ucunun bir Yuki eni ötesi arasında, çubuk bedeninin alt yarısında.
      İkisi birden tutarsa panel (önünde durmak daha açık niyet); paneller `paneller()` sırasıyla.
    Geniş (sürükleyip bıraktı, genis=True;: "geçiremedim" → bırakılan yer kabaca yeterli):
      otur: orta çizgisi panelin ±%30 Yuki eni içinde, panelin üstü başının biraz üstüyle ayağının %30 altı arasında.
      uzan: orta çizgisi çubuğun ±%30–60 Yuki eni içinde, çubuk bedeninin alt %70'inden ayağının %35 altına kadar.
      Sıra: kalçanın (boyun %62'si) panelin üstüne, ayağın çubuğa en yakın olduğu aday önde.
    """
    if not ekran:
        return []
    x, y, w, h = yuki
    cx = x + w / 2
    dis = lambda a, b: max(0.0, a - cx, cx - b) / w      # noqa: E731  orta çizginin [a, b] dışına uzaklığı (Yuki eni)
    adaylar = []
    for p in paneller(ekran):
        if not genis:
            if p[0] <= cx <= p[0] + p[2] and y + 0.25 * h <= p[1] <= y + h:
                return [("otur", p)]
        elif p[0] - 0.3 * w <= cx <= p[0] + p[2] + 0.3 * w and y - 0.1 * h <= p[1] <= y + 1.3 * h:
            adaylar.append((abs(p[1] - (y + 0.62 * h)) / h + dis(p[0], p[0] + p[2]), "otur", p))
    c = ekran.get("cubuk") if UZAN_ACIK else None
    if c and not genis:
        if c[0] + c[2] * 0.5 <= cx <= c[0] + c[2] + w * 0.6 and y + 0.5 * h <= c[1] <= y + h + 0.1 * h:
            return [("uzan", c)]
    elif c and c[0] - 0.3 * w <= cx <= c[0] + c[2] + 0.6 * w and y + 0.3 * h <= c[1] <= y + 1.35 * h:
        adaylar.append((abs(c[1] - (y + h)) / h + dis(c[0], c[0] + c[2]), "uzan", c))
    return [(ad, k) for _s, ad, k in sorted(adaylar, key=lambda t: t[0])]


def poz_yeri(ad: str, kadraj: dict, ekran: dict, mon: tuple[int, int, int, int],
             simdiki_cx: float, kutu: tuple | None = None) -> tuple[tuple[int, int] | None, str]:
    """Pozun temas noktası çapaya otursun diye (sol, alt) katman marjı; olmuyorsa (None, neden).

    kadraj (sayfadan, `yukiPozHazirla`): w, h, temas [x, y] pencere px, govde [sol x, sağ x] pencere px.
    otur: temas (oturma yüzeyi: kalçanın altı) `kutu`nun (verilmezse PANEL'in) üst kenarında; yatayda panelin soldan
          `OTUR_ORAN`'ında (bacaklar panelin yazılarına sarkmasın).
    uzan: temas (bedenin alt çizgisi) çubuğun üstünde; baştan ayağa beden çubuğun içinde (6 px pay), baş çubuğun SAĞ
          ucunda: ortadaki "…bir şey sor" başlığı
          ve durum satırı ortalı → baş yazının altına girmez, yazının altında alçak bacaklar kalır. Paneller çubuğun
          üstüne biniyorsa beden onlara girmez.
    Pencere monitörden taşarsa None.
    """
    w, h = int(kadraj["w"]), int(kadraj["h"])
    tx, ty = kadraj["temas"]
    if ad == "otur":
        p = kutu or ekran.get("panel") or next(iter(paneller(ekran)), None)
        if not p:
            return None, "panel_yok"
        sx = p[0] + OTUR_ORAN * p[2]                                #: bacaklar yazı/simge/◀ üstüne sarkmaz
        sy = p[1]
    elif ad == "uzan":
        c = ekran.get("cubuk")
        if not c:
            return None, "cubuk_yok"
        g0, g1 = kadraj["govde"]
        if g1 - g0 > c[2] - 12:
            return None, "cubuk_kisa"
        lo, hi = c[0] + 6 + (tx - g0), c[0] + c[2] - 6 - (g1 - tx)   # temas x'in alabileceği aralık
        araliklar = [(lo, hi)]
        for p in paneller(ekran):                                    # panel çubuğun üstüne biniyorsa bedeni ona sokma
            if p[1] < c[1] and p[1] + p[3] > c[1] - ty:              # panelin dikey aralığı uzanan bedeninkiyle kesişir
                yeni = []
                for a, b in araliklar:
                    yeni += [(a, min(b, p[0] - 4 - (g1 - tx))), (max(a, p[0] + p[2] + 4 + (tx - g0)), b)]
                araliklar = [(a, b) for a, b in yeni if a <= b]
        if not araliklar:
            return None, "panel_cakisir"
        sx = max(b for _a, b in araliklar)                          # baş sağda (aynalı poz): sığan en sağ yer
        sy = c[1]
    else:
        return None, "poz_yok"
    gx, gy = round(sx - tx), round(sy - ty)                        # pencerenin global sol-üst köşesi
    sol, alt = gx - mon[0], mon[1] + mon[3] - (gy + h)
    if sol < 0 or alt < 0 or sol + w > mon[2] or alt + h > mon[3]:
        return None, "ekran_disi"
    return (sol, alt), "tamam"


def capa_monitorde(ekran: dict, mon: tuple[int, int, int, int]) -> bool:
    """Çapalardan en az biri Yuki'nin monitöründe mi (Yuki monitör değiştirmez; başka monitördeki pencere = poz yok)."""
    for k in paneller(ekran) + [(ekran or {}).get("cubuk")]:
        if k and mon[0] <= k[0] + k[2] / 2 <= mon[0] + mon[2] and mon[1] <= k[1] <= mon[1] + mon[3]:
            return True
    return False


# ── ne sıklıkla ──────────────────────────────────────────────────────────
SELAM_ILK = (20.0, 50.0)      # açılıştan sonra ilk "merhaba" selamı (sn)
SELAM_ARA = (45.0, 110.0)     # uyanıkken kendi kendine el sallama aralığı (sn)
SELAM_UYKU_ARA = (180.0, 360.0)   # uykudayken: uyanıp el sallar (60 sn'lik uyku yüzünden yoksa hiç görülmezdi)
SESSIZ_SN = 6.0               # son etkileşimden (tık/sürükle/konuşma) bu kadar sonra kendiliğinden bir şey yapar
POZ_BEKLE = (3.0, 7.0)        # çapanın yanında bu kadar durunca poza girer
POZ_SURE = (60.0, 180.0)      # pozda kalma
POZ_ARA = (40.0, 120.0)       # pozdan kalktıktan sonra aynı yere yeniden geçmeden önce
BIRAK_BEKLE = 0.8             # sürükleyip çapanın yanına bıraktıysan (niyet açık) kısa bekleme


@dataclass
class Planlayici:
    """Her turda (≈1 sn) `adim()` → eylem listesi: ("selam",) · ("poz", ad) · ("kalk",).

    durum: uyku, gizli, surukle (bool) · poz (None | ad) · yakin (None | ad, ayaktayken) · gecerli (pozdayken
    çapa hâlâ yerinde ve sığıyor mu). `etkilesim(simdi)` tık/sürükle/konuşmada çağrılır.
    """
    rnd: random.Random = field(default_factory=random.Random)
    son_etkilesim: float = -1e9
    sonraki_selam: float | None = None
    sonraki_uyku_selam: float | None = None
    yakin_ad: str | None = None
    yakin_t: float | None = None
    poz_bitis: float | None = None
    ara_bitis: float = -1e9
    yakin_bekle: float = 0.0
    birak_t: float | None = None
    gecmis: list = field(default_factory=list)

    def etkilesim(self, simdi: float) -> None:
        self.son_etkilesim = simdi

    def birakildi(self, simdi: float) -> None:
        """Sürükleme bitti: çapa yanına bırakıldıysa kısa bekleyip poza geçsin (ara sayacı da sıfırlanır)."""
        self.son_etkilesim = simdi - SESSIZ_SN          # bırakmak "rahatsız etme" değil, niyet
        self.yakin_ad, self.yakin_t = None, None
        self.ara_bitis = -1e9
        self.birak_t = simdi

    def poz_basladi(self, simdi: float) -> None:
        """Host pozu kendisi başlattı (bırakınca yapışma): pozda kalma süresi buradan sayılır."""
        self.poz_bitis = simdi + self.rnd.uniform(*POZ_SURE)
        self.yakin_ad, self.yakin_t, self.birak_t = None, None, None

    def _kaydet(self, simdi: float, e: tuple) -> list:
        self.gecmis.append((round(simdi, 2),) + e)
        return [e]

    def adim(self, simdi: float, durum: dict) -> list:
        if self.sonraki_selam is None:
            self.sonraki_selam = simdi + self.rnd.uniform(*SELAM_ILK)
            self.sonraki_uyku_selam = simdi + self.rnd.uniform(*SELAM_UYKU_ARA)
        poz = durum.get("poz")
        if durum.get("gizli"):
            return []
        if poz:
            if durum.get("surukle") or not durum.get("gecerli", True):
                return self._bitir(simdi)
            if self.poz_bitis is not None and simdi >= self.poz_bitis and not durum.get("uyku"):
                return self._bitir(simdi)
        sessiz = simdi - self.son_etkilesim >= SESSIZ_SN
        if durum.get("uyku") and sessiz and not durum.get("surukle") and poz != "uzan" \
                and simdi >= self.sonraki_uyku_selam:          # uykudan uyanıp el sallar
            return self._selam(simdi)
        if durum.get("uyku") or durum.get("surukle") or not sessiz:
            if not sessiz or durum.get("surukle"):
                self.yakin_t = None
            return []
        if not poz:
            yakin = durum.get("yakin")
            if yakin != self.yakin_ad:
                self.yakin_ad, self.yakin_t = yakin, simdi
                self.yakin_bekle = BIRAK_BEKLE if self.birak_t is not None else self.rnd.uniform(*POZ_BEKLE)
                self.birak_t = None
            elif yakin and self.yakin_t is None:
                self.yakin_t, self.yakin_bekle = simdi, self.rnd.uniform(*POZ_BEKLE)
            if yakin and simdi >= self.ara_bitis and simdi - self.yakin_t >= self.yakin_bekle:
                self.poz_bitis = simdi + self.rnd.uniform(*POZ_SURE)
                self.yakin_t = None
                return self._kaydet(simdi, ("poz", yakin))
        if simdi >= self.sonraki_selam and poz != "uzan":          # uzanırken destek kolu el sallamaz
            return self._selam(simdi)
        return []

    def _selam(self, simdi: float) -> list:
        self.sonraki_selam = simdi + self.rnd.uniform(*SELAM_ARA)
        self.sonraki_uyku_selam = simdi + self.rnd.uniform(*SELAM_UYKU_ARA)
        return self._kaydet(simdi, ("selam",))

    def _bitir(self, simdi: float) -> list:
        self.poz_bitis = None
        self.ara_bitis = simdi + self.rnd.uniform(*POZ_ARA)
        self.yakin_ad, self.yakin_t = None, None
        return self._kaydet(simdi, ("kalk",))


# ── host bağı ────────────────────────────────────────────────────────────
_CAPA_ADI = {"otur": "panel", "uzan": "cubuk"}
KALK_MS = 650                 # sayfanın POZ_SN'i (0,6 sn) + bir kare: pozdan çıkış bitince ayakta boyuna dön
# Bırakınca yapışamadıysa balonla neden: kullanıcı "geçiremedim" dedi; sessiz vazgeçiş neden olmadığını saklıyordu
# (örn. PANEL üst çubuğun hemen altındayken oturunca baş ekrandan taşar → ekran_disi).
YAPISAMADI = {"ekran_disi": "Burada sığmıyorum — paneli biraz aşağı çeker misin?",
              "cubuk_kisa": "Bu çubuk bana kısa geldi.",
              "panel_cakisir": "Panel çubuğu örtüyor, uzanacak yer yok."}


class EtkilesimHost:
    """Host ile karar arasındaki ince katman. `yuki_govde.YukiTamGovde` bir örnek tutar.

    GTK'ye doğrudan dokunmaz: gövdenin (`g`) alanları (sol, alt, w, h, mon, gizli, uyku, arg) ve yöntemleri
    (_js, _marj_uygula, _girdi_bolgesi, _ilk_bolge, _geo, boyut_uygula) üzerinden çalışır → sahte gövdeyle test edilir.
    Sayfaya yalnız olayda ve YANITSIZ komutla gider (`_js(kod)`, canlıda JSC'siz SSE akışı); sayfadan soru
    sorulmaz: poz kadrajları sayfanın saniyelik durum POST'uyla gelir (`kadraj_geldi`). evaluate_javascript sonucu
    okumak arayüz sürecinde JSC'yi dolduruyor, ~39 sn'de donma yapıyordu.
    Pencere kaynağı yalnız çapa tazeyken okunur (ön yüz kapalıyken 0 IPC).
    """

    def __init__(self, g, saat=None, pencere=None, rnd=None, zamanla=None, log=None) -> None:
        import time as _t
        self.g = g
        # log: masaüstünün çıktısı ($XDG_RUNTIME_DIR/yuki-masaustu.log). Yalnız olayda (ilk çapa, selam, poz, vazgeç,
        # kalk) — canlı ölçüm bunlara bakar; her turda satır yok.
        self.log = log or (lambda m: print(m, flush=True))
        self.saat = saat or _t.monotonic
        self.pencere = pencere or pencere_json
        self.plan = Planlayici(rnd or random.Random())
        self._zamanla = zamanla
        self.capa, self.capa_t = None, -1e9
        self.poz = None             # {"ad", "durum": hazirlik|aktif|kalkiyor, "ayakta": (sol, alt, w, h), "kadraj", "kutu"}
        self._yakin_kutu = None     # son turda yanında durduğu çapanın kutusu (hangi panel)
        self.son_neden = None
        self.kadraj: dict = {}      # ad → {w, h, temas, govde} (sayfanın durum POST'undan)
        self.kayit: list = []

    def zamanla(self, ms: int, f) -> None:
        if self._zamanla:
            return self._zamanla(ms, f)
        from gi.repository import GLib
        GLib.timeout_add(ms, lambda: (f(), False)[1])

    # ── girdiler ──
    def kadraj_geldi(self, d) -> None:
        """Sayfanın durum iletisindeki `poz_kadraj` ({ad: {w, h, temas, govde}}); bozuk olanı alma."""
        if not isinstance(d, dict):
            return
        for ad, k in d.items():
            try:
                if ad in _CAPA_ADI and 16 <= int(k["w"]) <= 4000 and 16 <= int(k["h"]) <= 4000 \
                        and len(k["temas"]) == 2 and len(k["govde"]) == 2:
                    self.kadraj[ad] = {"w": int(k["w"]), "h": int(k["h"]), "temas": [float(v) for v in k["temas"]],
                                       "govde": [float(v) for v in k["govde"]]}
            except (KeyError, TypeError, ValueError):
                continue

    def capa_geldi(self, c: dict) -> None:
        if self.capa is None:
            self.log(f"[etkilesim] çapa geldi panel={c.get('panel')} cubuk={c.get('cubuk')} görünüm={c.get('vw')}x{c.get('vh')}")
        self.capa, self.capa_t = c, self.saat()

    def etkilesim(self) -> None:
        self.plan.etkilesim(self.saat())

    def surukle_basladi(self) -> None:
        self.plan.etkilesim(self.saat())
        if self.poz:
            self.log("[etkilesim] kalk sürükleme")
            self.kalk()

    def birakildi(self) -> None:
        """Sürükleme bitti. Bir panelin ya da çubuğun üstüne/yanına kabaca bırakıldıysa HEMEN poza geçer
."""
        self.plan.birakildi(self.saat())
        if not self.poz:
            self.yapis()

    def yapis(self) -> bool:
        """Bırakılan yerin geniş aday çapalarını sırayla dener; ilk sığana girer. Aday var ama hiçbiri sığmıyorsa
        balonla nedenini söyler. Döner: poza girdi mi."""
        ekran = self.ekran()
        if not ekran:
            return False
        x, _y, w, _h = kutu = self._ayakta_kutu()
        neden = None
        for ad, k in capa_sec(kutu, ekran, genis=True):
            kd = self.kadraj.get(ad)
            if not kd:
                neden = neden or "kadraj_yok"
                continue
            yer, n = poz_yeri(ad, kd, ekran, self.g._geo(), x + w / 2, kutu=k)
            if yer is None:
                neden = neden or n
                continue
            self.log(f"[etkilesim] yapış {ad} kutu={k}")
            self.kayit.append(("yapis", ad))
            self.plan.poz_basladi(self.saat())
            self.gir(ad, ekran, k)
            return bool(self.poz)
        if neden:
            self.son_neden = neden
            self.kayit.append(("yapisamadi", neden))
            self.log(f"[etkilesim] yapışamadı {neden}")
            balon = getattr(getattr(self.g, "kopru", None), "balon", None)
            if balon and neden in YAPISAMADI:
                balon.goster(YAPISAMADI[neden], 3.5)
        return False

    def ayakta_marj(self) -> tuple[int, int]:
        """Konum kaydı için: pozdayken ayaktaki yer (poz yeri kalıcı konum değildir)."""
        return self.poz["ayakta"][:2] if self.poz and self.poz.get("ayakta") else (self.g.sol, self.g.alt)

    # ── çapa → ekran ──
    def ekran(self) -> dict | None:
        if self.capa is None or self.saat() - self.capa_t > CAPA_TAZE_SN:
            return None
        ist = istemci_bul(self.pencere("clients"))
        if not ist or not gorunur_mu(ist, self.pencere("monitors")):
            return None
        e = capa_ekran(self.capa, ist)
        return e if capa_monitorde(e, self.g._geo()) else None

    def _ayakta_kutu(self) -> tuple[int, int, int, int]:
        mx, my, _mw, mh = self.g._geo()
        sol, alt, w, h = self.poz["ayakta"] if self.poz and self.poz.get("ayakta") else \
            (self.g.sol, self.g.alt, self.g.w, self.g.h)   # hazırlıkta pencere henüz ayaktaki
        return mx + sol, my + mh - alt - h, w, h

    # ── 1 sn'lik tur ──
    def tur(self) -> bool:
        g, simdi = self.g, self.saat()
        if g.gizli:
            return True
        ekran = self.ekran()
        gecerli = True
        if self.poz and self.poz["durum"] == "aktif":
            k = self._capa_bul(ekran) if ekran else None
            yer, neden = poz_yeri(self.poz["ad"], self.poz["kadraj"], ekran, g._geo(), self._hedef_x(k), kutu=k) \
                if k else (None, "capa_yok")
            if k:
                self.poz["kutu"] = k
            gecerli = yer is not None
            if not gecerli:
                self.son_neden = neden
            elif yer != (g.sol, g.alt):                       # çapa kaydı (PANEL sürüklendi) → izle
                g.sol, g.alt = yer
                g._marj_uygula()
        aday = [] if self.poz else capa_sec(self._ayakta_kutu(), ekran)
        yakin, self._yakin_kutu = aday[0] if aday else (None, None)
        durum = {"gizli": g.gizli, "uyku": g.uyku, "surukle": bool(getattr(g, "_bas", None) and g._bas.get("surukle")),
                 "poz": self.poz["ad"] if self.poz else None, "yakin": yakin, "gecerli": gecerli}
        if self.poz and self.poz["durum"] != "aktif":         # geçişte karar verme
            return True
        for e in self.plan.adim(simdi, durum):
            self.uygula(e, ekran)
        return True

    def _temas_x(self) -> float:
        """Pozdayken temas noktasının global x'i."""
        return self.g._geo()[0] + self.g.sol + self.poz["kadraj"]["temas"][0]

    def _capa_bul(self, ekran: dict) -> tuple | None:
        """Pozdayken oturulan/uzanılan çapanın şimdiki kutusu (panel kapandıysa None → kalkar)."""
        if self.poz["ad"] == "uzan":
            return ekran.get("cubuk")
        eski = self.poz.get("kutu")
        return capa_izle(eski, paneller(ekran)) if eski else ekran.get("panel")

    def _hedef_x(self, k: tuple | None) -> float:
        """Çapa kayınca temas noktası çapaya göre aynı yerde kalsın (PANEL'i sürükleyince Yuki onunla gider)."""
        return k[0] + self.poz["goreli"] if k else self._temas_x()

    def uygula(self, e: tuple, ekran: dict | None) -> None:
        self.kayit.append(e)
        self.log("[etkilesim] " + " ".join(str(x) for x in e))
        if e[0] == "selam":
            self.g._js("window.yukiKendiSelam && window.yukiKendiSelam()")
        elif e[0] == "poz" and ekran:
            self.gir(e[1], ekran, self._yakin_kutu)
        elif e[0] == "kalk":
            self.kalk()

    # ── poza gir / kalk ──
    def gir(self, ad: str, ekran: dict, kutu: tuple | None = None) -> None:
        if self.poz or (ad == "uzan" and not UZAN_ACIK):
            return
        kutu = kutu or (ekran.get("cubuk") if ad == "uzan" else ekran.get("panel"))
        self.poz = {"ad": ad, "durum": "hazirlik", "kutu": kutu}
        self._yerles(ad, self.kadraj.get(ad), ekran)

    def _yerles(self, ad: str, k: dict | None, ekran: dict) -> None:
        g = self.g
        if not self.poz or self.poz["ad"] != ad:
            return
        if not k:
            self.poz, self.son_neden = None, "kadraj_yok"
            self.log(f"[etkilesim] vazgeç {ad} kadraj_yok")
            return
        x, _y, w, _h = self._ayakta_kutu()
        kutu = self.poz.get("kutu")
        yer, neden = poz_yeri(ad, k, ekran, g._geo(), x + w / 2, kutu=kutu)
        if yer is None:
            self.poz, self.son_neden = None, neden
            self.kayit.append(("vazgec", ad, neden))
            self.log(f"[etkilesim] vazgeç {ad} {neden}")
            return
        self.poz.update(durum="aktif", kadraj=k, ayakta=(g.sol, g.alt, g.w, g.h))
        g.w, g.h = int(k["w"]), int(k["h"])
        g.boyut_uygula()
        g.sol, g.alt = yer
        g._marj_uygula()
        self.poz["goreli"] = self._temas_x() - kutu[0]
        g.bolge = [(g.w // 4, g.h // 4, g.w // 2, g.h // 2)]    # siluet ≈1 sn'de sayfadan gelir
        g._girdi_bolgesi()
        g._js(f"window.yukiPozBasla({json.dumps(ad)})")
        self.log(f"[etkilesim] poz {ad} marj={yer} pencere={g.w}x{g.h}")

    def kalk(self, hemen: bool = False) -> None:
        """Pozdan çık: sayfa 0,6 sn'de yumuşakça kalkar, sonra ayakta boyuna dönülür. hemen: monitör değişimi."""
        if not self.poz:
            return
        if self.poz["durum"] == "hazirlik":                   # kadraj yanıtı gelmeden: hiçbir şey değişmedi
            self.poz = None
            return
        if self.poz["durum"] == "kalkiyor":
            return
        self.poz["durum"] = "kalkiyor"
        self.g._js("window.yukiPozBitir && window.yukiPozBitir()")
        if hemen:
            self._ayaga()
        else:
            self.zamanla(KALK_MS, self._ayaga)

    def _ayaga(self) -> None:
        g, p = self.g, self.poz
        if not p:
            return
        g.sol, g.alt, g.w, g.h = p["ayakta"]
        g.boyut_uygula()
        g._marj_uygula()
        g._js(f"window.yukiBoyut && window.yukiBoyut({g.w}, {g.h})")
        g.bolge = g._ilk_bolge()
        g._girdi_bolgesi()
        self.poz = None
