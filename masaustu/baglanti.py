"""Masaüstü Yuki F2 — aynı Yuki'ye bağlantı: /ws/realtime dinleyicisi + olay → beden komutu çevirici.

NEDEN VAR: masaüstü Yuki ayrı bir yapay zekâ değil, aynı Yuki'nin ikinci ekranı (PLAN § Yuki bağlantısı).
Kendi LLM çağrısı YOK: mesaj ana pencerenin kullandığı yoldan (`/ws/realtime` → `{"type":"text"}` →
`chat_stream`, tek motor) gider; duygu, durum, yazı ve bildirim aynı sokketten dinlenir.

Ölçülen backend gerçekleri:
- Bağlantı Python tarafında kurulur, Origin başlığı GÖNDERİLMEZ: `_check_ws_origin` başlıksız bağlantıyı kabul
  eder. Sayfadan (WebKit) bağlansaydık Origin `http://127.0.0.1:<rastgele>` olurdu ve `ALLOWED_ORIGINS` TAM
  eşleşme istediği için 4003 alırdık → backend/config değişikliği gerekmez.
- `text` / `done` / `behavior` / `proactive_message` herkese (`_manager.broadcast`); `emotion` / `state` olay
  veri yolundan her bağlantıya. `audio` ise YALNIZ mesajı gönderen sokete gider:
    · ana pencereden konuşulunca masaüstüne ses gelmez → ağız konuşma boyunca yapay hareketle oynar;
    · masaüstünden gönderilen turun sesi yalnız buraya gelir → o turu masaüstü ÇALAR (tek kaynak, çift ses yok);
    · proaktif/zamanlayıcı sesi herkese gider, ana pencere çalar → masaüstü ÇALMAZ, yalnız seviyesini ağza verir.
- Her sokketin turu kendine aittir: masaüstünden gönderilen mesaj ana penceredeki turu iptal etmez.

Token: env (`YUKI_TOKEN` / `AUTH_TOKEN`) → depo `.env` → `backend/.env`.
Token hiçbir yere yazılmaz: log, özet ve hata metinleri adresi tokensiz basar.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
from pathlib import Path
from typing import Callable
from urllib.parse import quote

DUYGULAR = ("happy", "sad", "angry", "surprised", "shy", "tired")   # yuki.html / yuki-tam.html YUZ/DUYGU
DUYGU_SN = 8.0                       # PLAN: 8 sn sonra sakine döner
BALON_SN = 6.0                       # PLAN: kısa balon 6 sn
BILDIRIM_SN = 10.0
BALON_KRK = 140                      # bundan uzun cevap → son cümle + "devamı ana pencerede"
MESAJ_KRK = 2000
KONUSMA_KRK_SN = 14.0                # ana pencerede çalan sesin tahmini hızı (krk/sn) — ses buraya gelmez
KONUSMA_SN_MAX = 60.0
_ETIKET = re.compile(r"[\[\(](?:EMOTION|BEHAVIOR):\s*\{[^}]*\}[\]\)]", re.IGNORECASE)
_YARIM_ETIKET = re.compile(r"[\[\(](?:EMOTION|BEHAVIOR):[^\]\)]*$", re.IGNORECASE)
_CUMLE = re.compile(r"(?<=[.!?…])\s+")
_BILDIRIM_TIPLERI = ("proactive_message", "state_info", "disaster_alert")


# ───────────────────────────── token / adres ─────────────────────────────

def _env_oku(yol: Path, ad: str = "AUTH_TOKEN") -> str:
    try:
        for satir in yol.read_text(encoding="utf-8").splitlines():
            satir = satir.strip()
            if satir.startswith(ad + "="):
                return satir.split("=", 1)[1].strip().strip("'\"")
    except OSError:
        pass
    return ""


def token_bul(depo: Path, ortam: dict | None = None) -> str:
    """Önce ortam (`YUKI_TOKEN` / `AUTH_TOKEN`), sonra depo `.env` / `backend/.env`. Sabit varsayılan YOK."""
    ortam = os.environ if ortam is None else ortam
    t = ortam.get("YUKI_TOKEN") or ortam.get("AUTH_TOKEN", "")
    if t:
        return t
    for yol in (depo / ".env", depo / "backend" / ".env"):
        t = _env_oku(yol)
        if t:
            return t
    return ""


def ws_adresi(taban: str, token: str = "") -> str:
    """`http://127.0.0.1:8001` ya da `ws://…` → `/ws/realtime?token=…` (token boşsa sorgusuz)."""
    t = taban.rstrip("/")
    t = "ws://" + t[7:] if t.startswith("http://") else "wss://" + t[8:] if t.startswith("https://") else t
    if not t.endswith("/ws/realtime"):
        t += "/ws/realtime"
    return t + ("?token=" + quote(token, safe="") if token else "")


def tokensiz(adres: str) -> str:
    return re.sub(r"token=[^&]*", "token=***", adres)


# ───────────────────────────── saf çevirici ─────────────────────────────

def etiketsiz(metin: str) -> str:
    return re.sub(r"\s{2,}", " ", _YARIM_ETIKET.sub("", _ETIKET.sub("", metin))).strip()


def balon_metni(metin: str, sinir: int = BALON_KRK) -> tuple[str, bool]:
    """Kısa balon: kısa cevap aynen; uzun cevapta son cümle (o da uzunsa kırpılır) + devamı ana pencerede."""
    m = etiketsiz(metin)
    if len(m) <= sinir:
        return m, False
    cumleler = [c for c in _CUMLE.split(m) if c.strip()]
    son = cumleler[-1].strip() if cumleler else m
    if len(son) > sinir:
        son = son[: sinir - 1].rstrip() + "…"
    return son, True


class Cevirici:
    """WS olayı → beden komutları. GTK'siz, saf (testli).

    Komut biçimi: (ad, *argümanlar)
      ("yuz", duygu, ms) · ("dusun", bool) · ("konus", bool) · ("ses", base64, cal: bool) ·
      ("balon", metin, sn, devami: bool) · ("selam",) · ("konus_sure", sn) · ("capa", dict)

    `konus_sure`: ana pencereden gelen turda ses masaüstüne gelmez ve `done` sesin bitişini değil sesin
    GÖNDERİLDİĞİNİ söyler (ana pencere çalmayı sürdürür). Kalan konuşma, cevap uzunluğundan tahmin edilir.
    """

    def __init__(self, saat: Callable[[], float] = time.monotonic) -> None:
        self.saat = saat
        self.konus_t: float | None = None
        self.metin: dict[str, str] = {}     # tur → biriken yazı
        self.bizim: set[str] = set()        # masaüstünün gönderdiği turlar (sesini masaüstü çalar)
        self.iptal: set[str] = set()
        self.son_tur: str | None = None

    def tur_ekle(self, tur: str) -> None:
        self.bizim.add(tur)

    def cevir(self, olay: dict) -> list[tuple]:
        if not isinstance(olay, dict):
            return []
        tip = olay.get("type")
        tur = olay.get("tur")
        if tur is not None and tur in self.iptal and tip in ("text", "audio", "done"):
            return []
        if tip == "masaustu_capa":         #: ön yüzün PANEL / giriş hapı kutuları (etkilesim.py)
            from etkilesim import capa_dogrula
            c = capa_dogrula(olay)
            return [("capa", c)] if c else []
        if tip == "emotion":
            d = olay.get("emotion")
            return [("yuz", d, int(DUYGU_SN * 1000))] if d in DUYGULAR else []
        if tip == "state":
            hedef = olay.get("to")
            if hedef == "thinking":
                return [("dusun", True)]
            if hedef == "talking":
                if self.konus_t is None:
                    self.konus_t = self.saat()
                return [("dusun", False), ("konus", True)]
            if hedef in ("idle", "listening"):
                # yazı bekleyen tur varsa ağız `done`a kadar sürer (idle `done`dan hemen önce gelir)
                return [("dusun", False)] if any(self.metin.values()) else [("dusun", False), ("konus", False)]
            return []
        if tip == "text":
            parca = olay.get("chunk")
            if not isinstance(parca, str):
                return []
            anahtar = tur or "_"
            self.metin[anahtar] = self.metin.get(anahtar, "") + parca
            self.son_tur = anahtar
            return []
        if tip == "done":
            anahtar = tur or self.son_tur or "_"
            metin = self.metin.pop(anahtar, "")
            self.son_tur = None
            baslangic, self.konus_t = self.konus_t, None
            if anahtar in self.bizim or not metin.strip():
                konus = ("konus", False)          # kendi turumuzun sesi burada çalar, ağzı o sürer
            else:
                gecen = self.saat() - baslangic if baslangic is not None else 0.0
                kalan = min(KONUSMA_SN_MAX, max(0.0, len(etiketsiz(metin)) / KONUSMA_KRK_SN - gecen))
                konus = ("konus_sure", round(kalan, 1))
            m, devami = balon_metni(metin)
            return [konus] + ([("balon", m, BALON_SN, devami)] if m else [])
        if tip == "cancelled":
            if tur:
                self.iptal.add(tur)
                self.metin.pop(tur, None)
            self.konus_t = None
            return [("dusun", False), ("konus", False)]
        if tip == "audio":
            veri = olay.get("data")
            if not isinstance(veri, str) or not veri:
                return []
            return [("ses", veri, bool(tur) and tur in self.bizim)]
        if tip in _BILDIRIM_TIPLERI:
            metin = olay.get("text") or olay.get("message") or olay.get("baslik") or ""
            if not isinstance(metin, str) or not metin.strip():
                return []
            m, devami = balon_metni(metin)
            return [("selam",), ("balon", m, BILDIRIM_SN, devami)]
        return []


# ───────────────────────────── WS dinleyici ─────────────────────────────

class Baglanti:
    """Arka iş parçacığında /ws/realtime dinler; komutları `teslim(komut)` ile verir (GTK'de GLib.idle_add).

    Backend kapalıysa sessizce yeniden dener (2 → 30 sn); Yuki bu sırada nefes alır, konuşmaz.
    """

    def __init__(self, adres: str, teslim: Callable[[tuple], None], bekle_max: float = 30.0) -> None:
        self.adres = adres
        self.teslim = teslim
        self.cevirici = Cevirici()
        self.bekle_max = bekle_max
        self.bagli = False
        self.deneme = 0
        self.olay_say: dict[str, int] = {}
        self.son_hata: str | None = None
        self._ws = None
        self._kilit = threading.Lock()
        self._dur = threading.Event()
        self._sayac = 0
        self._is = threading.Thread(target=self._dongu, name="yuki-baglanti", daemon=True)

    def baslat(self) -> "Baglanti":
        self._is.start()
        return self

    def durdur(self) -> None:
        self._dur.set()
        with self._kilit:
            ws = self._ws
        if ws is not None:
            try:
                ws.close()
            except Exception:
                pass

    def _dongu(self) -> None:
        from websockets.sync.client import connect
        bekle = 2.0
        while not self._dur.is_set():
            self.deneme += 1
            try:
                # origin=None: Origin başlığı gönderilmez (backend başlıksız bağlantıyı kabul eder)
                with connect(self.adres, origin=None, open_timeout=5, max_size=32 * 1024 * 1024,
                             user_agent_header="yuki-masaustu") as ws:
                    with self._kilit:
                        self._ws = ws
                    self.bagli, self.son_hata, bekle = True, None, 2.0
                    for ham in ws:
                        if self._dur.is_set():
                            break
                        self._isle(ham)
            except Exception as e:     # bağlantı yok / koptu / reddedildi — token'sız kısa iz
                self.son_hata = tokensiz(f"{type(e).__name__}: {e}")[:160]
            finally:
                with self._kilit:
                    self._ws = None
                if self.bagli:
                    self.bagli = False
                    self.teslim(("dusun", False))
                    self.teslim(("konus", False))
            if self._dur.wait(bekle):
                break
            bekle = min(self.bekle_max, bekle * 2)

    def _isle(self, ham) -> None:
        if not isinstance(ham, str):
            return
        try:
            olay = json.loads(ham)
        except ValueError:
            return
        tip = olay.get("type") if isinstance(olay, dict) else None
        if tip:
            self.olay_say[tip] = self.olay_say.get(tip, 0) + 1
        for komut in self.cevirici.cevir(olay):
            self.teslim(komut)

    def gonder(self, metin: str) -> str | None:
        """Ana pencereyle aynı biçim (core.js: `{type:'text', message, tur}`). Bağlı değilse None."""
        metin = (metin or "").strip()[:MESAJ_KRK]
        if not metin:
            return None
        with self._kilit:
            ws = self._ws
        if ws is None or not self.bagli:
            return None
        self._sayac += 1
        tur = f"m{int(time.time() * 1000):x}-{self._sayac}"
        self.cevirici.tur_ekle(tur)
        try:
            ws.send(json.dumps({"type": "text", "message": metin, "tur": tur}, ensure_ascii=False))
        except Exception as e:
            self.son_hata = tokensiz(f"{type(e).__name__}: {e}")[:160]
            return None
        return tur

    def ozet(self) -> dict:
        return {"adres": tokensiz(self.adres), "bagli": self.bagli, "deneme": self.deneme,
                "olay": dict(self.olay_say), "son_hata": self.son_hata}
