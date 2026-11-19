"""Masaüstü Yuki F2 — Yuki bağlantısı, ekrana çıkmadan ve canlı backend'e DOKUNMADAN ölçer.

Ölçer:
1. saf: token bulma (env → .env → backend/.env), WS adresi, token gizleme, etiket ayıklama, balon kısaltma,
   olay → beden komutu çevirici (duygu, düşünüyor, konuşma + kalan süre, yazı → balon, iptal, ses kimin, bildirim).
2. istemci: SAHTE /ws/realtime sunucusu — token sorguda, Origin başlığı YOK, olay → komut, mesaj ana pencereyle
   aynı biçimde (`{type:text, message, tur}`), kendi turunun sesi `cal`, sunucu kapalıyken çökmeden yeniden dener.
3. uçtan uca: gerçek WebKit sayfası (`masaustu.py --kuru`; kullanıcının VRM'i gerekir, `YUKI_TEST_VRM` yoksa atlanır) sahte sunucuya bağlanır:
   emotion → yüz (yukiYuz), düşünüyor, konuşma, ses seviyesi, balon kaydı; token çıktıda yok.
4. giriş kutusu + balon (pencere GÖSTERİLMEZ): Enter → gönder, boş gitmez, Esc kapatır, bağlantı yoksa uyarı balonu.

Kullanım:  python3 masaustu/tests/test_baglanti.py        (düz script)   Çıkış 0 = geçti.
"""
from __future__ import annotations

import base64
import io
import json
import math
import os
import struct
import subprocess
import sys
import tempfile
import threading
import time
import wave
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KOK))
import baglanti as bg  # noqa: E402

gecti = kaldi = 0
VRM = os.environ.get("YUKI_TEST_VRM")
SAHTE_TOKEN = "sahte-token-f2"


def kontrol(ad: str, kosul: bool, ayrinti: str = "") -> None:
    global gecti, kaldi
    if kosul:
        gecti += 1
        print("  ✓", ad)
    else:
        kaldi += 1
        print("  ✗", ad, ayrinti)


def wav_b64(sn: float = 0.6, hz: float = 220.0) -> str:
    b = io.BytesIO()
    with wave.open(b, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(22050)
        w.writeframes(b"".join(struct.pack("<h", int(12000 * math.sin(2 * math.pi * hz * i / 22050)))
                               for i in range(int(22050 * sn))))
    return base64.b64encode(b.getvalue()).decode()


# ───────────────────────────── 1. saf ─────────────────────────────

def saf() -> None:
    print("— saf: token / adres / metin")
    with tempfile.TemporaryDirectory() as d:
        k = Path(d)
        kontrol("env YUKI_TOKEN önce gelir", bg.token_bul(k, {"YUKI_TOKEN": "a", "AUTH_TOKEN": "b"}) == "a")
        kontrol("env yoksa ve .env yoksa boş (sabit varsayılan yok)", bg.token_bul(k, {}) == "")
        (k / "backend").mkdir()
        (k / "backend" / ".env").write_text("X=1\nAUTH_TOKEN='bk'\n")
        kontrol("backend/.env okunur, tırnak soyulur", bg.token_bul(k, {}) == "bk")
        (k / ".env").write_text("AUTH_TOKEN=kok\n")
        kontrol("kök .env backend/.env'den önce (yuki-widget deseni)", bg.token_bul(k, {}) == "kok")
    kontrol("http → ws + /ws/realtime + token", bg.ws_adresi("http://127.0.0.1:8001", "a b") ==
            "ws://127.0.0.1:8001/ws/realtime?token=a%20b")
    kontrol("token boşsa sorgu yok", bg.ws_adresi("ws://h:1/ws/realtime") == "ws://h:1/ws/realtime")
    kontrol("tokensiz() gizler", bg.tokensiz("ws://h/ws/realtime?token=gizli&x=1") == "ws://h/ws/realtime?token=***&x=1")
    kontrol("etiketler ayıklanır", bg.etiketsiz('Merhaba. [EMOTION: {"emotion":"happy"}] Nasılsın? (BEHAVIOR: {"a":1})')
            == "Merhaba. Nasılsın?")
    kontrol("yarım kalan etiket ayıklanır", bg.etiketsiz("Tamam [EMOTION: {\"emo") == "Tamam")
    kontrol("kısa cevap aynen", bg.balon_metni("Su iç.") == ("Su iç.", False))
    uzun = "Birinci cümle epey uzun bir açıklama yapıyor ve devam ediyor. " * 3 + "Son cümle bu."
    kontrol("uzun cevap → son cümle + devamı", bg.balon_metni(uzun) == ("Son cümle bu.", True), str(bg.balon_metni(uzun)))
    tek = "a" * 400
    m, dv = bg.balon_metni(tek)
    kontrol("tek dev cümle kırpılır (≤140)", dv and len(m) <= 140 and m.endswith("…"))

    print("— saf: olay → beden komutu")
    saat = [100.0]
    c = bg.Cevirici(saat=lambda: saat[0])
    kontrol("emotion happy → yüz 8 sn", c.cevir({"type": "emotion", "emotion": "happy", "intensity": .8}) == [("yuz", "happy", 8000)])
    kontrol("emotion neutral → komut yok (yüzü kendisi söndürür)", c.cevir({"type": "emotion", "emotion": "neutral"}) == [])
    kontrol("bilinmeyen duygu → komut yok", c.cevir({"type": "emotion", "emotion": "xyz"}) == [])
    kontrol("state thinking → düşün", c.cevir({"type": "state", "from": "idle", "to": "thinking"}) == [("dusun", True)])
    kontrol("state talking → düşünme biter, konuşur",
            c.cevir({"type": "state", "to": "talking"}) == [("dusun", False), ("konus", True)])
    kontrol("text parçası birikir, komut yok", c.cevir({"type": "text", "chunk": "Merhaba Deniz. ", "tur": "t1"}) == [])
    c.cevir({"type": "text", "chunk": "Bugün hava güzel.", "tur": "t1"})
    kontrol("yazı bekliyorken idle → ağız susmaz", c.cevir({"type": "state", "to": "idle"}) == [("dusun", False)])
    saat[0] = 101.0
    sonuc = c.cevir({"type": "done", "tur": "t1"})
    kalan = round(len("Merhaba Deniz. Bugün hava güzel.") / bg.KONUSMA_KRK_SN - 1.0, 1)
    kontrol("done (ana pencere turu) → kalan konuşma süresi + balon",
            sonuc == [("konus_sure", kalan), ("balon", "Merhaba Deniz. Bugün hava güzel.", bg.BALON_SN, False)], str(sonuc))
    kontrol("yazı yokken idle → konuşma da biter",
            c.cevir({"type": "state", "to": "idle"}) == [("dusun", False), ("konus", False)])
    kontrol("başkasının turunun sesi → sessiz (ana pencere çalar)", c.cevir({"type": "audio", "data": "QQ==", "tur": "t1"}) == [("ses", "QQ==", False)])
    kontrol("tursuz (proaktif) ses → sessiz", c.cevir({"type": "audio", "data": "QQ=="}) == [("ses", "QQ==", False)])
    c.tur_ekle("m1")
    kontrol("kendi turumuzun sesi → masaüstü çalar", c.cevir({"type": "audio", "data": "QQ==", "tur": "m1"}) == [("ses", "QQ==", True)])
    c.cevir({"type": "text", "chunk": "Tamam.", "tur": "m1"})
    kontrol("kendi turumuzda done → konuşma biter (ses burada çalıyor), balon",
            c.cevir({"type": "done", "tur": "m1"}) == [("konus", False), ("balon", "Tamam.", bg.BALON_SN, False)])
    c.cevir({"type": "text", "chunk": "yarım", "tur": "t2"})
    kontrol("cancelled → sus, düşünme biter", c.cevir({"type": "cancelled", "tur": "t2"}) == [("dusun", False), ("konus", False)])
    kontrol("iptal edilen turun geç parçası düşer", c.cevir({"type": "text", "chunk": "geç", "tur": "t2"}) == []
            and c.cevir({"type": "audio", "data": "QQ==", "tur": "t2"}) == [] and c.cevir({"type": "done", "tur": "t2"}) == [])
    kontrol("proactive_message → selam + bildirim balonu",
            c.cevir({"type": "proactive_message", "text": "Su içme vakti", "kaynak": "hatirlatma"}) ==
            [("selam",), ("balon", "Su içme vakti", bg.BILDIRIM_SN, False)])
    kontrol("bilinmeyen / bozuk olay → komut yok", c.cevir({"type": "live2d", "params": {}}) == [] and c.cevir("x") == []
            and c.cevir({"type": "text", "chunk": None}) == [])


# ───────────────────────────── 2. istemci ↔ sahte sunucu ─────────────────────────────

class SahteSunucu:
    """Sahte /ws/realtime: bağlantıyı kaydeder, verilen olayları yollar, gelen mesajları biriktirir."""

    def __init__(self, olaylar=(), gecikme: float = 0.0, cevap=None) -> None:
        from websockets.sync.server import serve
        self.olaylar, self.gecikme, self.cevap = list(olaylar), gecikme, cevap
        self.baglantilar: list[dict] = []
        self.gelen: list[dict] = []
        self.srv = serve(self._isle, "127.0.0.1", 0)
        self.port = self.srv.socket.getsockname()[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def _isle(self, ws) -> None:
        self.baglantilar.append({"yol": ws.request.path, "origin": ws.request.headers.get("Origin"),
                                 "ua": ws.request.headers.get("User-Agent")})
        time.sleep(self.gecikme)
        for o in self.olaylar:
            ws.send(json.dumps(o))
            time.sleep(0.05)
        try:
            for ham in ws:
                m = json.loads(ham)
                self.gelen.append(m)
                if self.cevap:
                    for o in self.cevap(m):
                        ws.send(json.dumps(o))
        except Exception:
            pass

    def kapat(self) -> None:
        self.srv.shutdown()


def bekle(kosul, sn: float = 5.0) -> bool:
    son = time.monotonic() + sn
    while time.monotonic() < son:
        if kosul():
            return True
        time.sleep(0.05)
    return kosul()


def istemci() -> None:
    print("— istemci ↔ sahte /ws/realtime")
    cevap = lambda m: [{"type": "text", "chunk": "Peki.", "tur": m["tur"]},           # noqa: E731
                       {"type": "audio", "data": "QUJD", "text": "Peki.", "tur": m["tur"]},
                       {"type": "done", "tur": m["tur"]}]
    s = SahteSunucu([{"type": "emotion", "emotion": "shy", "intensity": 0.7},
                     {"type": "state", "from": "idle", "to": "thinking"}], cevap=cevap)
    komutlar: list = []
    b = bg.Baglanti(bg.ws_adresi(f"http://127.0.0.1:{s.port}", SAHTE_TOKEN), komutlar.append).baslat()
    kontrol("bağlandı", bekle(lambda: b.bagli))
    kontrol("token sorguda (?token=)", bekle(lambda: s.baglantilar) and s.baglantilar[0]["yol"].endswith("?token=" + SAHTE_TOKEN))
    kontrol("Origin başlığı GÖNDERİLMEDİ (ALLOWED_ORIGINS'e takılmaz)", s.baglantilar[0]["origin"] is None, str(s.baglantilar[0]))
    kontrol("olay → komut (shy yüzü, düşünüyor)", bekle(lambda: len(komutlar) >= 2) and komutlar[:2] == [("yuz", "shy", 8000), ("dusun", True)], str(komutlar))
    tur = b.gonder("  merhaba Yuki  ")
    kontrol("gönder → tur kimliği", bool(tur))
    kontrol("mesaj ana pencereyle aynı biçim {type:text, message, tur}",
            bekle(lambda: s.gelen) and s.gelen[0] == {"type": "text", "message": "merhaba Yuki", "tur": tur}, str(s.gelen))
    kontrol("kendi turumuzun sesi → cal=True", bekle(lambda: ("ses", "QUJD", True) in komutlar), str(komutlar))
    kontrol("kendi turumuzun done'u → balon 'Peki.'", bekle(lambda: any(k[0] == "balon" and k[1] == "Peki." for k in komutlar)))
    kontrol("boş mesaj gönderilmez", b.gonder("   ") is None and len(s.gelen) == 1)
    kontrol("mesaj 2000 karakterde kesilir", b.gonder("x" * 5000) and bekle(lambda: len(s.gelen) == 2) and len(s.gelen[1]["message"]) == 2000)
    kontrol("özet token'sız", SAHTE_TOKEN not in json.dumps(b.ozet()) and b.ozet()["olay"].get("emotion") == 1, str(b.ozet()))
    s.kapat()
    kontrol("sunucu kapanınca bağlantı düşer, çökme yok", bekle(lambda: not b.bagli, 6))
    kontrol("koptuğunda ağız/düşünme sıfırlanır", ("konus", False) in komutlar[-3:] and ("dusun", False) in komutlar[-3:], str(komutlar[-3:]))
    kontrol("bağlı değilken gönder → None", b.gonder("selam") is None)
    b.durdur()

    print("— istemci: backend kapalı")
    import socket
    k = socket.socket(); k.bind(("127.0.0.1", 0)); port = k.getsockname()[1]; k.close()
    b2 = bg.Baglanti(bg.ws_adresi(f"http://127.0.0.1:{port}", SAHTE_TOKEN), lambda _k: None).baslat()
    time.sleep(2.6)
    o = b2.ozet()
    kontrol("kapalı backend: bağlı değil, yeniden deniyor (≥2 deneme)", not o["bagli"] and o["deneme"] >= 2, str(o))
    kontrol("hata iz'i token'sız", SAHTE_TOKEN not in (o["son_hata"] or ""), str(o["son_hata"]))
    b2.durdur()


# ───────────────────────────── 3. uçtan uca (WebKit, kuru) ─────────────────────────────

def uctan_uca(kip: str) -> None:
    print(f"— uçtan uca: gerçek sayfa (kip {kip}) ↔ sahte sunucu")
    if not VRM:
        print("  – atlandı: YUKI_TEST_VRM yok")
        return
    olaylar = [
        {"type": "state", "from": "idle", "to": "thinking"},
        {"type": "emotion", "emotion": "happy", "intensity": 0.8},
        {"type": "state", "from": "thinking", "to": "talking"},
        {"type": "text", "chunk": 'Merhaba Deniz. [EMOTION: {"emotion":"happy"}] ', "tur": "t9"},
        {"type": "text", "chunk": "Bugün hava güzel.", "tur": "t9"},
        {"type": "audio", "data": wav_b64(0.6), "text": "Merhaba", "tur": "t9"},
        {"type": "state", "from": "talking", "to": "idle"},
        {"type": "done", "tur": "t9"},
        {"type": "proactive_message", "text": "Su içme vakti.", "kaynak": "hatirlatma"},
    ]
    s = SahteSunucu(olaylar, gecikme=2.5)
    ortam = {**os.environ, "AUTH_TOKEN": SAHTE_TOKEN}
    r = subprocess.run([sys.executable, str(KOK / "masaustu.py"), "--kuru", "--model", VRM, "--sure", "6", "--tezgah", "0",
                        "--backend", f"http://127.0.0.1:{s.port}"], capture_output=True, text=True, timeout=120, env=ortam)
    s.kapat()
    kontrol("çıkış 0", r.returncode == 0, r.stderr[-300:])
    try:
        o = json.loads(r.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError) as e:
        kontrol("JSON özet", False, str(e) + r.stdout[-300:])
        return
    d, bag = o.get("durum") or {}, o.get("baglanti") or {}
    g = d.get("gecmis", [])
    kontrol("token stdout/stderr'de yok", SAHTE_TOKEN not in r.stdout and SAHTE_TOKEN not in r.stderr)
    kontrol("Origin'siz bağlandı, token sorguda", s.baglantilar and s.baglantilar[0]["origin"] is None
            and "token=" + SAHTE_TOKEN in s.baglantilar[0]["yol"])
    kontrol("bağlantı özeti: 9 olay alındı", sum(bag.get("olay", {}).values()) == 9, str(bag.get("olay")))
    i = g.index("bag:yuz:happy") if "bag:yuz:happy" in g else -1
    kontrol("emotion happy → sayfada yüz değişti (yukiYuz, bağlantı çağrısının hemen ardından)",
            0 <= i < len(g) - 1 and g[i + 1].startswith("happy"), str(g))
    kontrol("düşünüyor → başladı ve bitti", "bag:dusun" in g and "bag:dusun-bitti" in g, str(g))
    kontrol("konuşma başladı", "bag:konus" in g, str(g))
    kontrol("ana pencerenin sesi sessiz oynatıldı (seviye ağza)", any(x.startswith("bag:ses:sessiz:0.6") for x in g), str(g))
    kontrol("ağız gerçekten açıldı (seviye tepe > 0,2)", (d.get("agiz_tepe") or 0) > 0.2, str(d.get("agiz_tepe")))
    kontrol("done → kalan konuşma süresi", any(x.startswith("bag:konus-sure:") for x in g), str(g))
    kontrol("bildirim → selam (el kaldırır)", "bag:selam" in g, str(g))
    balon = [b["metin"] for b in bag.get("balon", [])]
    kontrol("balon: etiketsiz cevap", "Merhaba Deniz. Bugün hava güzel." in balon, str(balon))
    kontrol("balon: hatırlatma", "Su içme vakti." in balon, str(balon))
    kontrol("motor yine hazır, hata yok", d.get("hazir") is True and not d.get("hata"), str(d.get("hata")))


def uctan_uca_kapali() -> None:
    print("— uçtan uca: backend kapalıyken Yuki yine kalkar")
    if not VRM:
        print("  – atlandı: YUKI_TEST_VRM yok")
        return
    import socket
    k = socket.socket(); k.bind(("127.0.0.1", 0)); port = k.getsockname()[1]; k.close()
    r = subprocess.run([sys.executable, str(KOK / "masaustu.py"), "--kuru", "--model", VRM, "--sure", "3", "--tezgah", "0",
                        "--backend", f"http://127.0.0.1:{port}"], capture_output=True, text=True, timeout=120,
                       env={**os.environ, "AUTH_TOKEN": SAHTE_TOKEN})
    try:
        o = json.loads(r.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        o = {}
    d, bag = o.get("durum") or {}, o.get("baglanti") or {}
    kontrol("çıkış 0, motor hazır (nefes alır)", r.returncode == 0 and d.get("hazir") is True, r.stderr[-200:])
    kontrol("bağlı değil, deniyor, sessiz", bag.get("bagli") is False and bag.get("deneme", 0) >= 1 and not bag.get("komut"), str(bag))
    kontrol("tık tepkisi sürüyor", any(x.startswith("happy") for x in d.get("gecmis", [])), str(d.get("gecmis")))


# ───────────────────────────── 4. giriş kutusu + balon (gösterilmez) ─────────────────────────────

def giris_kutusu() -> None:
    print("— giriş kutusu + balon (pencere gösterilmez)")
    import types
    import balon as bl
    from gi.repository import Gdk
    arg = types.SimpleNamespace(kuru=False, katman="top", x=100, zemin=0, baglantisiz=False, backend=None)
    govde = types.SimpleNamespace(arg=arg, mon=None, w=240, h=480, KIP="tam", katman=False, win=None,
                                  _js=lambda *a, **k: None)
    giden = []
    gr = bl.Giris(govde, lambda m: (giden.append(m), "m1")[1])
    gr.alan.set_text("  bugün ne yaptım  ")
    kontrol("Enter → mesaj gider (boşluk kırpılır)", gr.yolla() == "m1" and giden == ["bugün ne yaptım"])
    kontrol("gönderince kutu boşalır", gr.alan.get_text() == "")
    kontrol("boş mesaj gitmez", gr.yolla() is None and len(giden) == 1)
    gr.alan.set_text("yarım")
    olay = Gdk.Event.new(Gdk.EventType.KEY_PRESS)
    olay.keyval = Gdk.KEY_Escape
    kontrol("Esc kapatır ve yazıyı siler", gr._tus(None, olay) is True and gr.alan.get_text() == "")
    kontrol("kutu en çok 2000 karakter", gr.alan.get_max_length() == 2000)
    kontrol("giriş klavyeyi yalnız açıkken alır (ON_DEMAND)", "ON_DEMAND" in Path(bl.__file__).read_text())
    b = bl.Balon(govde, gorunmez=True)
    b.goster("Merhaba", 6, False)
    kontrol("kuru/gizli balon yalnız kayda geçer", b.win is None and b.kayit[-1]["metin"] == "Merhaba")
    kontrol("balon yeri: tam boyda başın solunda", bl.balon_yeri(1500, 0, 240, 480, 300, "tam") == (1260, 384))
    kontrol("balon yeri: solda yer yoksa sağına", bl.balon_yeri(0, 0, 240, 480, 300, "tam")[0] == 180)
    kopru = bl.Kopru.__new__(bl.Kopru)
    kopru.govde, kopru.balon = govde, b
    kopru.baglanti = types.SimpleNamespace(gonder=lambda m: None)
    kontrol("bağlantı yokken gönder → uyarı balonu", kopru.gonder("selam") is None
            and "Bağlantı yok" in b.kayit[-1]["metin"])


if __name__ == "__main__":
    saf()
    istemci()
    giris_kutusu()
    uctan_uca("tam")
    uctan_uca_kapali()
    print(f"\n{gecti} geçti · {kaldi} kaldı")
    sys.exit(0 if kaldi == 0 else 1)
