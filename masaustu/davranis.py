"""Masaüstü Yuki F1 — saf davranış seçici (GTK'siz, test edilebilir).

NEDEN VAR: F1 dokunma tepkileri, sürükleme, konum kaydı ve bakış kararını host'tan
(`yuki_govde.py`) ayırır: pencere ve WebKit olmadan birim testle ölçülür.

- `Dokunma`: tık sayısı / basılı tutma süresi / tıklanan yer (baş mı) → duygu.
- `surukle_marj`: imleç farkından katman marjı, ekran sınırına kenetli.
- `konum_oku` / `konum_yaz`: ~/.local/state/yuki-masaustu.json (XDG_STATE_HOME'a uyar).
- `bakis_hedefi`: imleç Yuki'ye yakınsa pencere içi bakış noktası, uzaksa None (izleyene bakar).
- `imlec_oku`: Gdk küresel imleç (yalnız X11'de; Wayland'de None → yerel fark).
"""
from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, field
from pathlib import Path

# ── dokunma ──────────────────────────────────────────────────────────────
ZINCIR_SN = 1.2        # iki tık arası bundan kısaysa aynı "art arda" zincirin parçası
SASKIN_TIK = 3         # zincirin 3. tıkı → şaşkın
KIZGIN_TIK = 5         # 5. tıkı → kızgın (zincir sıfırlanır)
UZUN_BAS_SN = 0.8      # kıpırdamadan bu kadar basılı tut → mutlu
SURUKLE_PX = 6         # basılıyken imleç bu kadar kayarsa sürükleme (tık sayılmaz)


@dataclass
class Dokunma:
    """Tık zinciri. `tik()` duygu adı ya da None (değişiklik yok, mevcut tepki sürsün) döner.

    Kural ("başa tık → utangaç, çok tık → şaşkın/kızgın, uzun bas → mutlu"):
      1. tık → başa: shy · gövdeye: happy (F0 davranışı: gülümse + el salla)
      2. ve 4. tık → None (klip baştan başlamasın, mevcut tepki sürer)
      3. tık → surprised · 5. tık → angry, zincir sıfırlanır (6. tık yeniden 1. tık)
      uzun basma → happy_uzun (sevinç klibi); zinciri sıfırlar
    """
    son_tik: float | None = None
    sayac: int = 0
    gecmis: list[str] = field(default_factory=list)

    def tik(self, simdi: float, basta: bool) -> str | None:
        if self.son_tik is None or simdi - self.son_tik > ZINCIR_SN:
            self.sayac = 0
        self.son_tik = simdi
        self.sayac += 1
        n = self.sayac
        if n >= KIZGIN_TIK:
            duygu, self.sayac = "angry", 0
        elif n == SASKIN_TIK:
            duygu = "surprised"
        elif n == 1:
            duygu = "shy" if basta else "happy"
        else:
            duygu = None
        self.gecmis.append(duygu or "-")
        return duygu

    def uzun_bas(self, simdi: float) -> str:
        self.sayac, self.son_tik = 0, simdi
        self.gecmis.append("happy_uzun")
        return "happy_uzun"


def basta_mi(x: float, y: float, bas: tuple[float, float, float] | None) -> bool:
    """(x, y) pencere pikselinde baş dairesinin (cx, cy, r) içinde mi. Baş bilgisi yoksa False (gövde)."""
    if not bas:
        return False
    cx, cy, r = bas
    return (x - cx) ** 2 + (y - cy) ** 2 <= r * r


def suruklendi_mi(dx: float, dy: float) -> bool:
    return dx * dx + dy * dy >= SURUKLE_PX * SURUKLE_PX


# ── yer ──────────────────────────────────────────────────────────────────
def kenetle(sol: float, alt: float, w: int, h: int, mon_w: int, mon_h: int) -> tuple[int, int]:
    """Sol-alt çapalı katman marjı: pencere monitörün içinde kalır (sol 0..mon_w-w, alt 0..mon_h-h)."""
    sol = min(max(0, round(sol)), max(0, mon_w - w))
    alt = min(max(0, round(alt)), max(0, mon_h - h))
    return sol, alt


def surukle_marj(bas_marj: tuple[int, int], bas_imlec: tuple[float, float], imlec: tuple[float, float],
                 w: int, h: int, mon_w: int, mon_h: int) -> tuple[int, int]:
    """Sürükleme başındaki marj + imlecin o andan beri yer değiştirmesi → yeni (sol, alt) marjı.

    Ekran y'si aşağı artar, alt marj yukarı artar → dy ters işaretle girer. Mutlak imleç farkı kullanılır:
    pencere-içi koordinat pencere kaydıkça değişir (geri besleme titremesi), global imleç değişmez.
    """
    dx, dy = imlec[0] - bas_imlec[0], imlec[1] - bas_imlec[1]
    return kenetle(bas_marj[0] + dx, bas_marj[1] - dy, w, h, mon_w, mon_h)


def durum_yolu() -> Path:
    kok = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
    return Path(kok) / "yuki-masaustu.json"


def konum_oku(yol: Path | None = None) -> dict:
    """{kip: {"monitor": ad, "sol": px, "alt": px}} — dosya yoksa/bozuksa {}."""
    try:
        d = json.loads((yol or durum_yolu()).read_text())
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def konum_yaz(kip: str, kayit: dict, yol: Path | None = None) -> Path:
    """Yalnız `kip` anahtarını günceller; geçici dosya + rename (yarım yazılmış JSON kalmaz)."""
    yol = yol or durum_yolu()
    d = konum_oku(yol)
    d[kip] = kayit
    yol.parent.mkdir(parents=True, exist_ok=True)
    gecici = yol.with_suffix(".json.tmp")
    gecici.write_text(json.dumps(d, ensure_ascii=False, indent=1))
    os.replace(gecici, yol)
    return yol


def monitor_sec(adlar: list[str], kayitli: str | None, varsayilan: int) -> int:
    """Kayıtlı monitör adı hâlâ bağlıysa onun sırası, değilse `varsayilan` (mod sayı)."""
    if kayitli and kayitli in adlar:
        return adlar.index(kayitli)
    return varsayilan % len(adlar) if adlar else 0


# ── bakış ────────────────────────────────────────────────────────────────
BAKIS_YARICAP = 0.9    # imleç başa pencere boyunun bu katı kadar yakınsa bakar


def bakis_hedefi(imlec: tuple[float, float], pencere: tuple[int, int, int, int],
                 bas: tuple[float, float, float] | None) -> tuple[int, int] | None:
    """Global imleç → pencere içi (x, y) bakış noktası; uzaksa ya da baş bilinmiyorsa None.

    pencere = (x, y, w, h) global (monitör konumu + marj). Nokta pencere dışında olabilir (sayfa 3B'ye çevirir).
    """
    if not bas:
        return None
    px, py = imlec[0] - pencere[0], imlec[1] - pencere[1]
    if math.hypot(px - bas[0], py - bas[1]) > BAKIS_YARICAP * pencere[3]:
        return None
    return round(px), round(py)


def pencere_kutusu(mon: tuple[int, int, int, int], sol: int, alt: int, w: int, h: int) -> tuple[int, int, int, int]:
    """Sol-alt çapalı pencerenin global kutusu. mon = (x, y, w, h) Gdk mantıksal koordinat."""
    return mon[0] + sol, mon[1] + mon[3] - alt - h, w, h


def imlec_oku() -> tuple[float, float] | None:
    """Küresel imleç konumu (Gdk). Yalnız X11'de güvenilir: Wayland istemciye küresel imleci vermez → None
    (bakış varsayılana döner, sürükleme yerel farkla yapılır). Hiçbir süreç/JS çağrısı yok."""
    try:
        import gi
        gi.require_version("Gdk", "3.0")
        from gi.repository import Gdk
        disp = Gdk.Display.get_default()
        if disp is None or "X11" not in type(disp).__name__:
            return None
        _ekran, x, y = disp.get_default_seat().get_pointer().get_position()
        return float(x), float(y)
    except (ImportError, ValueError, AttributeError):
        return None


# ── takılma sayacı ────────────────────────────────────────────
# Sayfa (web/takilma.js) kare döngüsünü, host GTK'nın ekrana basışlarını (frame clock after-paint) sayar.
# İkisi ayrı sorudur: sayfa geç kare üretiyorsa iş web sürecinde; sayfa zamanında üretip host geç basıyorsa
# iş arayüz sürecinde (yazılımsal birleştirme, imleç okuma). Kural sayfayla aynı: eşik max(120, 2,5 kare) ms,
# ≥ 2 sn boşluk takılma değil (gizli/örtülü pencerede kare gelmez) → `uzun`.
TAKILMA_MIN_MS, TAKILMA_KAT, TAKILMA_UZUN_MS, TAKILMA_SON_N = 120.0, 2.5, 2000.0, 20
OZET_SN = 60           # takılma olmasa da bu aralıkla tek özet satırı (log şişmesin: saniyede satır YOK)


def takilma_esik(fps: float) -> float:
    return max(TAKILMA_MIN_MS, TAKILMA_KAT * 1000.0 / max(1.0, fps))


@dataclass
class KareSayaci:
    """Kare aralıkları → takılma sayısı + son 20 [duvar saati ms, aralık ms]. `web/takilma.js` ile aynı kural."""
    kare: int = 0
    sayi: int = 0
    uzun: int = 0
    max_ms: float = 0.0
    son: list = field(default_factory=list)

    def ekle(self, aralik_ms: float, fps: float, saat_ms: float) -> str | None:
        self.kare += 1
        if not aralik_ms > 0:
            return None
        if aralik_ms >= TAKILMA_UZUN_MS:
            self.uzun += 1
            return "uzun"
        if aralik_ms <= takilma_esik(fps):
            return None
        self.sayi += 1
        self.max_ms = max(self.max_ms, round(aralik_ms, 1))
        self.son = (self.son + [[saat_ms, round(aralik_ms)]])[-TAKILMA_SON_N:]
        return "takilma"

    def ozet(self) -> dict:
        return {"kare": self.kare, "sayi": self.sayi, "uzun": self.uzun, "max_ms": self.max_ms, "son": list(self.son)}


GORUNUR_ONCE_MS, GORUNUR_SONRA_MS = 250.0, 150.0   # takılma başlamadan bu pencerede host bastıysa ekrandaydı


def _yeni(son: list, sinir_ms: float) -> list:
    return [(t, a) for t, a in (son or []) if t > sinir_ms]


def gorunurde_mi(bitis_ms: float, aralik_ms: float, boyalar) -> bool:
    """Sayfa takılması ekrandayken mi oldu? Takılmadan önceki kare host'ça basıldıysa evet.

    Örtülü/gizli pencerede compositor kare istemez → host basmaz, WebKit zamanlayıcıyı ~0,4-1 sn'ye kısar;
    o aralıklar takılma değildir (ölçüldü: --kuru'da 1000 ms'lik 3 "takılma"). boyalar = host basış duvar saatleri (ms).
    """
    bas = bitis_ms - aralik_ms
    return any(bas - GORUNUR_ONCE_MS <= b <= bas + GORUNUR_SONRA_MS for b in boyalar)


def takilma_satiri(saat: str, sayfa: dict | None, sayfa_once: dict | None, host: dict, host_once: dict | None,
                   ozet_zamani: bool, ek: str = "", boyalar=None) -> str | None:
    """İki ölçüm anı arası fark → tek log satırı. Yeni takılma/uzun boşluk yoksa ve özet zamanı değilse None.

    sayfa/host = sayaç özeti (yukiDurum.takilma ya da KareSayaci.ozet()); *_once = önceki satırdaki hali.
    Aralıklar duvar saatiyle ayıklanır: yalnız önceki satırdan SONRA olanlar basılır. `boyalar` verilirse sayfa
    takılmalarından yalnız ekrandayken olanlar sayılır (öbürleri `örtülü`).
    """
    s, so = sayfa or {}, sayfa_once or {}
    h, ho = host or {}, host_once or {}
    s_yeni = _yeni(s.get("son"), max((t for t, _ in so.get("son") or []), default=0))
    h_yeni = _yeni(h.get("son"), max((t for t, _ in ho.get("son") or []), default=0))
    s_gor = s_yeni if boyalar is None else [x for x in s_yeni if gorunurde_mi(x[0], x[1], boyalar)]
    ortulu = len(s_yeni) - len(s_gor)
    ds, dh = len(s_gor), len(h_yeni)
    du = (s.get("uzun", 0) - so.get("uzun", 0)) + (h.get("uzun", 0) - ho.get("uzun", 0))
    if ds <= 0 and dh <= 0 and du <= 0 and not ozet_zamani:
        return None
    etiket = "[takilma]" if ds > 0 or dh > 0 else "[kare]"
    parca = [f"{etiket} {saat}",
             f"sayfa +{ds} {[a for _, a in s_gor]}ms kare {s.get('kare', 0) - so.get('kare', 0)}"
             f" iş_max {s.get('is_max_ms', 0)}ms bölge {s.get('bolge_son_ms', 0)}/{s.get('bolge_max_ms', 0)}ms",
             f"host_boya +{dh} {[a for _, a in h_yeni]}ms boya {h.get('kare', 0) - ho.get('kare', 0)}"]
    if ortulu:
        parca.append(f"örtülü {ortulu}")
    if du > 0:
        parca.append(f"uzun_bosluk +{du}")
    if ek:
        parca.append(ek)
    return " · ".join(parca)


# ── arayüz GL'i ───────────────────────────────────────────────
# GTK arayüz süreci bazı makinelerde GL bağlamını yazılımsal (llvmpipe) açıp her kareyi işlemcide birleştirir;
# GDK_GL=disable ile GTK GL açmaz, WebKit kareyi GL'siz basar (ölçüldü: işlemci %32,7 → %1,0, saydamlık aynı).
GL_KIPLERI = ("kapali", "acik")


def ayar_yolu() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "yuki-masaustu.json"


def arayuz_gl_ortami(env, yol: Path | None = None) -> str:
    """GDK_GL'i ayarla — Gtk YÜKLENMEDEN önce çağrılmalı (GTK3 değişkeni gtk_init'te okur). Dönen: kapali|acik.

    Öncelik: env YUKI_GL → ayar dosyası {"gl": …} (XDG config dizininde yuki-masaustu.json) → "kapali". Dosya backend
    yeniden başlamadan geri dönüş yolu: {"gl": "acik"} yaz, masaüstü Yuki'yi kapat-aç. Elle GDK_GL verildiyse ezilmez.
    """
    kip = env.get("YUKI_GL")
    if kip not in GL_KIPLERI:
        try:
            kip = json.loads((yol or ayar_yolu()).read_text()).get("gl")
        except (OSError, ValueError, AttributeError):
            kip = None
    kip = kip if kip in GL_KIPLERI else "kapali"
    if kip == "kapali":
        env.setdefault("GDK_GL", "disable")
    return kip


def ses_ozeti(bag: dict | None) -> str:
    """Log eki: sayfanın ses sayaçları (yukiBag.durum().sesSay) → ' · ses çalınan/sessiz/hata'. Yoksa boş.

    "Konuşmuyor" denince ilk bakılacak yer: masaüstünden yazılan turun sesi burada ÇALINIR (cal),
    ana pencerenin turu yalnız ağza seviye verir (sessiz). Üçü de artmıyorsa ses komutu sayfada koşmuyordur.
    """
    say = (bag or {}).get("sesSay") if isinstance(bag, dict) else None
    if not isinstance(say, dict):
        return ""
    return f" · ses {say.get('cal', 0)}/{say.get('sessiz', 0)}/{say.get('hata', 0)} çal/sessiz/hata"
