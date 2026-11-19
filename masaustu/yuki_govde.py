"""Masaüstü Yuki — kip tam gövdesi: kullanıcının kendi VRM'i baştan ayağa, saydam yüzeyde (WebKit2GTK + WebGL2).

Yüzey: gtk-layer-shell destekliyse katman yüzeyi (alt kenara çapalı, marj konumu); değilse X11'de normal
çerçevesiz, üstte kalan pencere (konum `move`). İkisi de yoksa `masaustu.py` "desteklenmiyor" der.
Model depoda yok: `--model` ile gelen dosya yerel sunucudan `/_yuki/model.vrm` olarak sunulur.

Donma dersi korunur: sayfa durumunu POST `/_yuki/durum` ile yollar, host komutları SSE `/_yuki/komut`'tan
gönderir; canlıda `evaluate_javascript` ile sonuç okunmaz, periyodik yoklama yoktur (bkz. `_Isleyici`).

Dokunma tepkileri (kararı davranis.Dokunma verir), basılı tut + sürükle → marj (ekrana kenetli), orta tık /
SIGUSR2 → sonraki monitör, konum XDG durum dizinindeki yuki-masaustu.json'da, SIGUSR1 → göster/gizle.
Bakış: imleç Gdk'den (yalnız X11'de küresel konum), 150 ms'de bir, yalnız uyanık + görünürken.
"""
from __future__ import annotations

import collections
import functools
import http.server
import json
import os
import queue
import secrets
import signal
import socketserver
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
gi.require_version("WebKit2", "4.1")
try:                                    # katman kabuğu kitaplığı yoksa X11 yolu kalır
    gi.require_version("GtkLayerShell", "0.1")
    from gi.repository import GtkLayerShell
except (ValueError, ImportError):
    GtkLayerShell = None
from gi.repository import Gdk, GdkPixbuf, GLib, Gtk, WebKit2  # noqa: E402
import cairo  # noqa: E402

from yuki_sprite import tam_boy_olcu  # noqa: E402
from davranis import (OZET_SN, UZUN_BAS_SN, Dokunma, KareSayaci, bakis_hedefi, basta_mi, durum_yolu,  # noqa: E402
                      imlec_oku, kenetle, konum_oku, konum_yaz, monitor_sec, pencere_kutusu, surukle_marj,
                      ses_ozeti, suruklendi_mi, takilma_satiri)
from balon import kopru_kur  # noqa: E402  F2 bağlantı
from etkilesim import EtkilesimHost  # noqa: E402  arayüzle etkileşim pozları

KOK = Path(__file__).resolve().parent
NAMESPACE = "yuki-masaustu"
DEPO = KOK.parent                      # depo kökü (sunucunun kökü)
MODEL_YOLU = "/_yuki/model.vrm"        # kullanıcının kendi VRM'i (host `--model`); depoda model yok
KLIP_ONEK = "/_yuki/klip/"             # isteğe bağlı VRMA klipleri (YUKI_MASAUSTU_VRMA_DIZINI); bu kopyada klip gelmez
SUNULAN = ("frontend/vendor/three-0.160.0/", "frontend/vendor/three-vrm-3.1.6/", "masaustu/web/")
SURE_MS = {"shy": 3500, "happy": 3000, "surprised": 3000, "angry": 4000, "happy_uzun": 4000}   # tepki süresi
BAKIS_MS = 150          # imleç okuma aralığı (soket ≈0,02 ms; yalnız uyanık + görünürken)
SURUKLE_MS = 16         # sürüklerken marj en çok bu sıklıkta yazılır (son konum bırakınca yazılır)


def gpu_ortami() -> str:
    """WebKit'in GPU yolunu seç (WebView kurulmadan ÖNCE çağrılır). `YUKI_GPU`:
    mesa (varsayılan): sürücü seçimine karışılmaz, yalnız birleştirme kipi sabitlenir · nvidia: aynı, NVIDIA EGL ·
    software: DMABUF kapalı (yazılım çizim)."""
    kip = os.environ.get("YUKI_GPU", "mesa")
    if kip in ("mesa", "nvidia"):
        os.environ.setdefault("WEBKIT_DISABLE_DMABUF_RENDERER", "0")
        os.environ.setdefault("WEBKIT_FORCE_COMPOSITING_MODE", "1")
    else:
        os.environ.setdefault("WEBKIT_DISABLE_DMABUF_RENDERER", "1")
    return kip


def surec_olc(ana: int | None = None) -> dict:
    """Bu sürecin WebKit alt süreçleri: işlemci sn, RSS, amdgpu gfx motor ns + VRAM (fdinfo). Yalnız --kuru ölçümü."""
    ana = ana or os.getpid()
    tik = os.sysconf("SC_CLK_TCK")
    out = {}
    for d in Path("/proc").iterdir():
        if not d.name.isdigit():
            continue
        try:
            stat = (d / "stat").read_text()
            alan = stat[stat.rindex(")") + 2:].split()
            if int(alan[1]) != ana:
                continue
            ad = (d / "comm").read_text().strip()
            rss = next((int(l.split()[1]) for l in (d / "status").read_text().splitlines() if l.startswith("VmRSS:")), 0)
            gfx = vram = 0
            gorulen = set()
            for fd in (d / "fd").iterdir():
                try:
                    if not os.readlink(fd).startswith("/dev/dri/renderD"):
                        continue
                    bilgi = dict(l.split(":", 1) for l in (d / "fdinfo" / fd.name).read_text().splitlines() if ":" in l)
                except OSError:
                    continue
                if bilgi.get("drm-driver", "").strip() != "amdgpu" or bilgi.get("drm-client-id") in gorulen:
                    continue
                gorulen.add(bilgi.get("drm-client-id"))
                gfx += int(bilgi.get("drm-engine-gfx", "0 ns").split()[0])
                vram += int(bilgi.get("drm-memory-vram", "0 KiB").split()[0])
            out[ad + ":" + d.name] = {"cpu_sn": (int(alan[11]) + int(alan[12])) / tik, "rss_kib": rss,
                                      "gfx_ns": gfx, "vram_kib": vram}
        except (OSError, ValueError, IndexError):
            continue
    return out


DURUM_YOLU = "/_yuki/durum"   # sayfa → host: tıklama bölgesi + takılma sayacı (POST, JSON)
KOMUT_YOLU = "/_yuki/komut"   # host → sayfa: JS komutları (EventSource; evaluate_javascript'in yerine)
DURUM_AZAMI = 64 * 1024
KOMUT_NABIZ_SN = 15


class _Isleyici(http.server.SimpleHTTPRequestHandler):
    """Yalnız SUNULAN önekleri, yalnız GET. WebKit file:// fetch'inde durum 0 döner,
    motor bunu hata sayıyor (ölçüldü) → sayfa küçük yerel sunucudan gelir.

    Tek POST: DURUM_YOLU. NEDEN: host sayfanın durumunu saniyede bir `evaluate_javascript` ile
    okuyordu; her sonuç arayüz sürecinde bir JSC nesnesi yaratıyor ve ~39 sn sonra ilk JSC çöp toplamasında
    ana iş parçacığı `JSC::Heap::acquireAccessSlow`'da KALICI kilitleniyordu (gdb, iki kez aynı saniyede) —
    masaüstü Yuki son karede donuyordu. Artık sayfa durumu buraya yollar: arayüz sürecinde JSC'ye hiç girilmez.
    Süreç başına rastgele anahtar (`X-Yuki-Anahtar`) ister: aynı makinedeki başka süreç tıklama bölgesini yazamasın.

    Ters yön de JSC'siz: host komutları KOMUT_YOLU'ndan olay akışıyla (SSE) gider. Sonuçsuz evaluate_javascript
    bile arayüz sürecinde JSC'yi dolduruyor — 50 ms'de bir çağrıyla 124. sn'de aynı donma (ölçüldü). Anahtar burada
    sorgu parametresinde (EventSource başlık yollayamaz). Tek abone: sayfa yeniden bağlanırsa eski akış kapanır."""
    def log_message(self, *a):
        pass

    def _komut_akisi(self) -> None:
        srv = self.server
        sorgu = self.path.split("?", 1)[1] if "?" in self.path else ""
        anahtar = next((v for k, _, v in (x.partition("=") for x in sorgu.split("&")) if k == "anahtar"), "")
        if srv.kuyruk is None or not secrets.compare_digest(anahtar, srv.anahtar):
            self.send_error(403)
            return
        srv.abone += 1
        ben = srv.abone
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            while srv.abone == ben:
                try:
                    kod = srv.kuyruk.get(timeout=KOMUT_NABIZ_SN)
                except queue.Empty:
                    self.wfile.write(b": nabiz\n\n")
                else:
                    if srv.abone != ben:            # yeni sayfa bağlandı: komutu ona bırak
                        srv.kuyruk.put(kod)
                        break
                    self.wfile.write(b"data: " + json.dumps(kod).encode() + b"\n\n")
                self.wfile.flush()
        except OSError:
            pass

    def do_POST(self):
        srv = self.server
        if self.path.split("?", 1)[0] != DURUM_YOLU or not getattr(srv, "teslim", None):
            self.send_error(404)
            return
        if not secrets.compare_digest(self.headers.get("X-Yuki-Anahtar", ""), srv.anahtar):
            self.send_error(403)
            return
        try:
            n = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            n = -1
        if not 0 < n <= DURUM_AZAMI:
            self.send_error(413 if n > DURUM_AZAMI else 400)
            return
        try:
            veri = json.loads(self.rfile.read(n))
        except ValueError:
            self.send_error(400)
            return
        if not isinstance(veri, dict):
            self.send_error(400)
            return
        srv.teslim(veri)
        self.send_response(204)
        self.end_headers()

    def _dosya_gonder(self, yol: Path | None) -> None:
        """Tek bir yerel dosyayı (kullanıcının VRM'i / klibi) parça parça gönder; yoksa 404."""
        if yol is None or not yol.is_file():
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(yol.stat().st_size))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        with open(yol, "rb") as f:
            while parca := f.read(1 << 20):
                self.wfile.write(parca)

    def do_GET(self):
        if self.path.split("?", 1)[0] == KOMUT_YOLU:
            self._komut_akisi()
            return
        temiz = self.path.split("?", 1)[0]
        if temiz == MODEL_YOLU:
            self._dosya_gonder(Path(self.server.model) if self.server.model else None)
            return
        if temiz.startswith(KLIP_ONEK):
            ad, dizin = temiz[len(KLIP_ONEK):], self.server.klip_dizini
            ok = bool(dizin) and ad.endswith(".vrma") and ad.isascii() and ad[:-5].isalnum()
            self._dosya_gonder(Path(dizin) / ad if ok else None)
            return
        yol = self.path.split("?", 1)[0].lstrip("/")
        if ".." in yol or not yol.startswith(SUNULAN):
            self.send_error(404)
            return
        super().do_GET()


class _Sunucu(socketserver.ThreadingTCPServer):
    """İş parçacıklı: olay akışı açıkken dosyalar da sunulur. Sayfa kapanırken kopan bağlantı yığın basmasın."""
    daemon_threads = True

    def handle_error(self, request, client_address) -> None:
        if not isinstance(sys.exc_info()[1], (BrokenPipeError, ConnectionResetError)):
            super().handle_error(request, client_address)


def sunucu_baslat() -> tuple[socketserver.TCPServer, int]:
    isleyici = functools.partial(_Isleyici, directory=str(DEPO))
    srv = _Sunucu(("127.0.0.1", 0), isleyici)
    srv.anahtar, srv.teslim = secrets.token_urlsafe(18), None   # teslim: host bağlar (GLib.idle_add ile ana iş parçacığına)
    srv.model = srv.klip_dizini = None                          # host bağlar (kullanıcının VRM'i / isteğe bağlı klipler)
    srv.kuyruk, srv.abone = None, 0                              # kuyruk: host bağlar (canlıda); None → akış 403
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, srv.server_address[1]


def yuzey_durumu() -> str:
    """Pencere yüzeyi: 'katman' (gtk-layer-shell destekli) · 'x11' (normal çerçevesiz üstte pencere) ·
    'wayland_katmansiz' (GNOME Wayland: XWayland denenebilir) · 'yok'. Ekran açılmaz."""
    disp = Gdk.Display.get_default()
    if disp is None:
        return "yok"
    if GtkLayerShell is not None and GtkLayerShell.is_supported():
        return "katman"
    ad = type(disp).__name__
    if "X11" in ad:
        return "x11"
    return "wayland_katmansiz" if "Wayland" in ad else "yok"


class YukiGovde:
    """Ortak host: pencere (katman yüzeyi ya da X11), WebView, dokunma/sürükleme, yerel sunucu. Kip: YukiTamGovde."""
    SAYFA = "masaustu/web/yuki-tam.html"
    KIP = "tam"

    def __init__(self, arg) -> None:
        self.arg = arg
        self._t_baslangic = time.monotonic()
        self.gpu = gpu_ortami()
        self.srv, self.port = sunucu_baslat()
        self.srv.model, self.srv.klip_dizini = getattr(arg, "model", None), os.environ.get("YUKI_MASAUSTU_VRMA_DIZINI")
        # konum kaydı: --kuru'da yalnız XDG_STATE_HOME açıkça verildiyse (test geçici dizin verir) — gerçek dosya kirlenmez
        self.kayit_yolu = durum_yolu() if (not arg.kuru or os.environ.get("XDG_STATE_HOME")) else None
        kayit = konum_oku(self.kayit_yolu).get(self.KIP, {}) if self.kayit_yolu else {}
        self.monitorler = self._monitorler()
        self.mon_i = monitor_sec([self._mon_adi(m, i) for i, m in enumerate(self.monitorler)],
                                 kayit.get("monitor") if arg.monitor is None else None, arg.monitor or 0)
        self.mon = self.monitorler[self.mon_i] if self.monitorler else None
        self.w, self.h = self._olcu()
        g = self._geo()
        sol = arg.x if arg.x is not None else kayit.get("sol", g[2] - self.w - 40)
        alt = arg.zemin if arg.zemin is not None else kayit.get("alt", 0)
        self.sol, self.alt = kenetle(sol, alt, self.w, self.h, g[2], g[3])
        self.dokunma = Dokunma()
        self._bas = None                     # basılı tuş durumu (sürükle / uzun bas)
        self._son_surukle = 0.0
        self.gizli = self.uyku = False
        self.bas_daire = None                # sayfadan: başın pencere içi dairesi (cx, cy, r)
        self._son_bakis = "?"
        self._imlec = imlec_oku
        self._imlec_max_ms = 0.0
        self.bolge = self._ilk_bolge()
        self.win = Gtk.Window()
        self.win.set_title("Yuki — Masaüstü")
        self.win.set_decorated(False)
        self.win.set_app_paintable(True)
        self.win.set_size_request(self.w, self.h)
        ekran = self.win.get_screen()
        gorsel = ekran.get_rgba_visual() if ekran else None
        if gorsel is not None:
            self.win.set_visual(gorsel)
        self.rgba = gorsel is not None

        self.katman = GtkLayerShell is not None and GtkLayerShell.is_supported()
        if not self.katman:      # X11: normal pencere, çerçevesiz, üstte, görev çubuğunda yok, odak almaz
            self.win.set_keep_above(True)
            self.win.set_skip_taskbar_hint(True)
            self.win.set_skip_pager_hint(True)
            self.win.set_accept_focus(False)
            self.win.set_type_hint(Gdk.WindowTypeHint.UTILITY)
            self.win.stick()
        if self.katman:
            GtkLayerShell.init_for_window(self.win)
            GtkLayerShell.set_namespace(self.win, NAMESPACE)
            GtkLayerShell.set_layer(self.win, GtkLayerShell.Layer.OVERLAY if arg.katman == "overlay"
                                    else GtkLayerShell.Layer.TOP)
            if self.mon is not None:
                GtkLayerShell.set_monitor(self.win, self.mon)
            GtkLayerShell.set_anchor(self.win, GtkLayerShell.Edge.LEFT, True)
            GtkLayerShell.set_anchor(self.win, GtkLayerShell.Edge.BOTTOM, True)
            self._marj_uygula()
            GtkLayerShell.set_exclusive_zone(self.win, 0)
            GtkLayerShell.set_keyboard_mode(self.win, GtkLayerShell.KeyboardMode.NONE)
        else:
            self._marj_uygula()

        # Ses: komutlar olay akışından koşuyor (evaluate_javascript değil) ve kullanıcı hareketi sayılmıyor;
        # WebKit'in otomatik oynatma kuralı AudioContext'i 'suspended' bırakıyor, resume() hiç dönmüyordu (ölçüldü) →
        # Yuki ağzını oynatıp SESSİZ kalıyordu. Bu sayfa yalnız kendi yerel sunucumuzdan geliyor: otomatik oynatmaya izin.
        self.web = WebKit2.WebView(website_policies=WebKit2.WebsitePolicies(autoplay=WebKit2.AutoplayPolicy.ALLOW))
        self.web.set_size_request(self.w, self.h)
        self.web.set_background_color(Gdk.RGBA(0, 0, 0, 0))
        s = self.web.get_settings()
        s.set_property("enable-webgl", True)
        s.set_property("media-playback-requires-user-gesture", False)
        s.set_property("enable-write-console-messages-to-stdout", True)
        self.web.connect("context-menu", lambda *_: True)                # sağ tık menüsü yok
        self.web.add_events(Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.BUTTON_RELEASE_MASK
                            | Gdk.EventMask.POINTER_MOTION_MASK)
        self.web.connect("button-press-event", self._tik)
        self.web.connect("button-release-event", self._birak)
        self.web.connect("motion-notify-event", self._hareket)
        self.win.add(self.web)
        self.win.connect("realize", lambda *_: self._girdi_bolgesi())
        self.win.connect("map", lambda *_: self._girdi_bolgesi())     # gizle → göster sonrası da
        self.win.connect("destroy", lambda *_: Gtk.main_quit())
        if not arg.kuru:
            self.srv.kuyruk = queue.Queue()
        self.web.load_uri(f"http://127.0.0.1:{self.port}/{self.SAYFA}?{self._sorgu()}"
                          + ("" if arg.kuru else f"&anahtar={self.srv.anahtar}"))
        self.kopru = kopru_kur(self)          # F2: /ws/realtime dinleyici + balon + giriş kutusu (balon.py)

    # ── kipe göre değişen üç parça (_olcu, _ilk_bolge, _sorgu) YukiTamGovde'de ──
    @staticmethod
    def _monitorler() -> list:
        disp = Gdk.Display.get_default()
        return [disp.get_monitor(i) for i in range(disp.get_n_monitors())] if disp else []

    @staticmethod
    def _mon_adi(m, i: int) -> str:
        """Kayıt anahtarı: model adı (GTK3 bağlantı adını vermiyor); yoksa sıra."""
        return (m.get_model() or "") or f"#{i}"

    def _geo(self) -> tuple[int, int, int, int]:
        if self.mon is None:
            return 0, 0, 1920, 1080
        g = self.mon.get_geometry()
        return g.x, g.y, g.width, g.height

    def _marj_uygula(self) -> None:
        if self.katman:
            GtkLayerShell.set_margin(self.win, GtkLayerShell.Edge.LEFT, self.sol)
            GtkLayerShell.set_margin(self.win, GtkLayerShell.Edge.BOTTOM, self.alt)
        else:                    # X11: sol-alt marjı mutlak pencere konumuna çevrilir
            mx, my, _mw, mh = self._geo()
            self.win.move(mx + self.sol, my + mh - self.alt - self.h)

    def _kaydet(self) -> None:
        if self.kayit_yolu:
            etk = getattr(self, "etk", None)                 # pozdayken ayaktaki yer kaydedilir
            sol, alt = etk.ayakta_marj() if etk else (self.sol, self.alt)
            konum_yaz(self.KIP, {"monitor": self._mon_adi(self.mon, self.mon_i) if self.mon else None,
                                 "sol": sol, "alt": alt}, self.kayit_yolu)

    def _girdi_bolgesi(self) -> None:
        gw = self.win.get_window()
        if gw is not None:
            r = cairo.Region()
            for k in self.bolge:
                r.union(cairo.RectangleInt(*k))
            gw.input_shape_combine_region(r, 0, 0)

    def _js(self, kod: str, geri=None) -> None:
        """Sayfada JS koş. `geri` yoksa sonuç HİÇ istenmez (finish çağrılmaz → arayüz sürecinde JSC nesnesi yok;
        bkz. _Isleyici). Sonuç gerekiyorsa yalnız kuru ölçümde kullan: canlıda biriken sonuçlar donma yaratıyordu."""
        if geri is None:
            if self.srv.kuyruk is not None:      # canlı: olay akışından (JSC'siz); sayfa bağlanana kadar kuyrukta bekler
                self.srv.kuyruk.put(kod)
            else:
                self.web.evaluate_javascript(kod, -1, None, None, None, None)
            return

        def bitti(web, sonuc):
            try:
                deger = web.evaluate_javascript_finish(sonuc)
                metin = deger.to_json(0) if deger is not None else "null"
            except GLib.Error as e:
                metin = json.dumps({"js_hata": e.message})
            if geri:
                geri(json.loads(metin) if metin and metin != "undefined" else None)
        self.web.evaluate_javascript(kod, -1, None, None, None, bitti)

    # ── F1: dokunma · sürükleme · monitör · göster/gizle ──
    def _tik(self, _w, olay) -> bool:
        if olay.button == 1 and olay.type == Gdk.EventType._2BUTTON_PRESS and self.kopru:   # F2: çift tık → yaz
            self.kopru.giris_ac()
            return True
        if olay.type != Gdk.EventType.BUTTON_PRESS:      # GTK çift/üçlü tık olayını ayrıca yollar: sayma
            return True
        if olay.button == 1:
            if getattr(self, "etk", None):
                self.etk.etkilesim()
            self._bas = {"x": olay.x, "y": olay.y, "imlec": self._imlec(), "marj": (self.sol, self.alt),
                         "surukle": False, "uzun": False, "bekleyen": None}
            self._bas["zaman"] = GLib.timeout_add(int(UZUN_BAS_SN * 1000), self._uzun_bas)
            return True
        if olay.button == 2:
            self.monitor_degistir(1)
            return True
        if olay.button == 3:
            Gtk.main_quit()
            return True
        return False

    def _uzun_bas(self) -> bool:
        b = self._bas
        if b and not b["surukle"]:
            b["uzun"], b["zaman"] = True, None
            self._tepki(self.dokunma.uzun_bas(time.monotonic()))
        return False

    def _hareket(self, _w, olay) -> bool:
        b = self._bas
        if not b:
            return False
        imlec = self._imlec() if b["imlec"] else None
        g = self._geo()
        if imlec:          # global imleç farkı: pencere kaydıkça değişmez
            dx, dy = imlec[0] - b["imlec"][0], imlec[1] - b["imlec"][1]
            hedef = surukle_marj(b["marj"], b["imlec"], imlec, self.w, self.h, g[2], g[3])
        else:              # IPC yoksa yerel fark: tutma noktası imlecin altında kalır
            dx, dy = olay.x - b["x"], olay.y - b["y"]
            hedef = kenetle(self.sol + dx, self.alt - dy, self.w, self.h, g[2], g[3])
        if not b["surukle"]:
            if not suruklendi_mi(dx, dy):
                return True
            b["surukle"] = True
            if b["zaman"]:
                GLib.source_remove(b["zaman"])
                b["zaman"] = None
            self._js("window.yukiUyandir && window.yukiUyandir()")
            etk = getattr(self, "etk", None)
            if etk and etk.poz:                              # pozdayken sürükleme: kalkar, ayaktaki yerden sürüklenir
                b["marj"] = etk.ayakta_marj()
                etk.surukle_basladi()
            elif etk:
                etk.surukle_basladi()
        if getattr(self, "etk", None) and self.etk.poz:      # kalkış bitene kadar (0,65 sn) pencere yerinde
            return True
        b["bekleyen"] = hedef
        simdi = time.monotonic()
        if simdi - self._son_surukle >= SURUKLE_MS / 1000:
            self._son_surukle = simdi
            self._marj_yaz(hedef)
        return True

    def _marj_yaz(self, hedef) -> None:
        if hedef and hedef != (self.sol, self.alt):
            self.sol, self.alt = hedef
            self._marj_uygula()

    def _birak(self, _w, olay) -> bool:
        b = self._bas
        if olay.button != 1 or not b:
            return olay.button == 1
        self._bas = None
        if b["zaman"]:
            GLib.source_remove(b["zaman"])
        if b["surukle"]:
            if not (getattr(self, "etk", None) and self.etk.poz):
                self._marj_yaz(b["bekleyen"])
            self._kaydet()
            if getattr(self, "etk", None):
                self.etk.birakildi()
        elif not b["uzun"]:
            self._tepki(self.dokunma.tik(time.monotonic(), basta_mi(b["x"], b["y"], self.bas_daire)))
        return True

    def _tepki(self, duygu: str | None) -> None:
        if duygu:
            self._js(f"window.yukiYuz && window.yukiYuz({json.dumps(duygu)}, {SURE_MS.get(duygu, 3000)})")
        else:              # zincirin ara tıkı: tepki sürer, yalnız uyanık say
            self._js("window.yukiUyandir && window.yukiUyandir()")

    def monitor_degistir(self, adim: int = 1) -> bool:
        """Sonraki monitör (orta tık / SIGUSR2): boy o monitöre göre, sağ altta, konum kaydedilir."""
        if len(self.monitorler) < 2:
            return True
        if getattr(self, "etk", None) and self.etk.poz:      # önce ayağa (poz penceresi yeni monitöre taşınmaz)
            self.etk.kalk(hemen=True)
        self.mon_i = (self.mon_i + adim) % len(self.monitorler)
        self.mon = self.monitorler[self.mon_i]
        self.w, self.h = self._olcu()
        g = self._geo()
        self.sol, self.alt = kenetle(g[2] - self.w - 40, self.alt, self.w, self.h, g[2], g[3])
        self.win.set_size_request(self.w, self.h)
        self.web.set_size_request(self.w, self.h)
        self.win.resize(self.w, self.h)
        if self.katman:
            GtkLayerShell.set_monitor(self.win, self.mon)
        self._marj_uygula()
        self._js(f"window.yukiBoyut && window.yukiBoyut({self.w}, {self.h})")
        self.bolge = self._ilk_bolge()
        self._girdi_bolgesi()
        self._kaydet()
        return True

    def goster_gizle(self) -> bool:
        """SIGUSR1: gizliyken sayfa hiç kare çizmez, imleç okunmaz."""
        self.gizli = not self.gizli
        if not self.arg.kuru:
            (self.win.hide if self.gizli else self.win.show_all)()
        self._js(f"window.yukiGizli && window.yukiGizli({'true' if self.gizli else 'false'})")
        return True

    def _bakis_tur(self) -> bool:
        """İmleç başa yakınsa sayfaya bakış noktası; uzaksa bir kez null (izleyene döner)."""
        if self.gizli or self.uyku or (self._bas and self._bas["surukle"]):
            return True
        t0 = time.monotonic()
        imlec = self._imlec()
        self._imlec_max_ms = max(self._imlec_max_ms, (time.monotonic() - t0) * 1000)   # ana iş parçacığını bekletir
        hedef = bakis_hedefi(imlec, pencere_kutusu(self._geo(), self.sol, self.alt, self.w, self.h),
                             self.bas_daire) if imlec else None
        if hedef == self._son_bakis or (hedef and self._son_bakis not in (None, "?")
                                        and abs(hedef[0] - self._son_bakis[0]) + abs(hedef[1] - self._son_bakis[1]) < 4):
            return True
        self._son_bakis = hedef
        self._js("window.yukiBak && window.yukiBak(%s)" % ("null" if hedef is None else f"{hedef[0]}, {hedef[1]}"))
        return True

    # ── kuru başlatma: pencere GÖSTERİLMEZ; sayfa yüklenir, motor kurulur, ölçülür ──
    def _kuru_ozet(self) -> dict:
        return {"kip": self.KIP, "gpu": self.gpu, "katman_kabugu": self.katman, "rgba": self.rgba,
                "boyut": [self.w, self.h], "marj": [self.sol, self.alt], "monitor": self.mon_i, "tiklama_bolgesi": {"serit": len(self.bolge),
                "alan_orani": round(sum(k[2] * k[3] for k in self.bolge) / (self.w * self.h), 2)},
                "otomatik_oynatma": self.web.get_website_policies().get_autoplay_policy().value_nick,
                "ses_hareket_ister": self.web.get_settings().get_property("media-playback-requires-user-gesture")}

    def _kuru_ek(self, sonuc: dict, bitir) -> None:
        """Kipe özel ek ölçümler; bitince `bitir()` çağrılır."""
        def son():
            if self.arg.senaryo != "f1":
                return bitir()
            self._senaryo_f1(sonuc, lambda: self._js("JSON.parse(JSON.stringify(window.yukiDurum))",
                                                     lambda d: (sonuc.__setitem__("durum", d), bitir())))
        self._js("window.yukiOrnek ? window.yukiOrnek() : null",
                 lambda o: (sonuc.__setitem__("ornek", o), self._tezgah(sonuc, son)))

    def _tezgah(self, sonuc: dict, sonra) -> None:
        """N kareyi art arda çizdir; WebKit sürecinin işlemci + AMD gfx süresi farkından kare başı maliyet.

        Map edilmemiş pencerede zamanlayıcılar kısılır, "boşta %" doğrudan ölçülemez → kare başı maliyet × fps.
        """
        n = int(getattr(self.arg, "tezgah", 0) or 0)
        if n <= 0:
            sonra()
            return
        once = surec_olc()

        def al(t):
            sonra_ = surec_olc()
            web = [k for k in sonra_ if k.startswith("WebKitWebProces") and k in once]
            if t and web:
                a, b = once[web[0]], sonra_[web[0]]
                cpu_ms = 1000 * (b["cpu_sn"] - a["cpu_sn"]) / n
                gfx_ms = (b["gfx_ns"] - a["gfx_ns"]) / 1e6 / n
                fps = self.arg.fps
                t.update({"web_cpu_ms_kare": round(cpu_ms, 3), "web_gfx_ms_kare": round(gfx_ms, 3),
                          f"tahmini_cpu_yuzde_{fps}fps": round(cpu_ms * fps / 10, 2),
                          f"tahmini_gpu_yuzde_{fps}fps": round(gfx_ms * fps / 10, 2),
                          "tahmini_cpu_yuzde_uyku_10fps": round(cpu_ms, 2),
                          "web_rss_mib": round(b["rss_kib"] / 1024), "web_vram_mib": round(b["vram_kib"] / 1024)})
            sonuc["tezgah"] = t
            sonuc["surecler"] = {k: {"rss_mib": round(v["rss_kib"] / 1024), "vram_mib": round(v["vram_kib"] / 1024)}
                                 for k, v in sonra_.items()}
            sonra()
        self._js(f"window.yukiTezgah ? window.yukiTezgah({n}) : null", al)

    def kuru(self, sure: float) -> int:
        """Pencere map edilmeden WebView'in sayfayı ve motoru kurup kuramadığını ölçer.

        Not: map edilmemiş WebView'de WebKit ekrana çizmez, zamanlayıcıları da kısar; piksel ve kare hızı
        burada "ekranda böyle" demek DEĞİL.
        """
        sonuc = self._kuru_ozet()
        c0, t0 = time.process_time(), time.monotonic()

        def hazir_bekle():   # açılış: host kurulumu bitti → motor ilk kareyi çizdi
            def bak(h):
                if h and "hazir_sn" not in sonuc:
                    sonuc["hazir_sn"] = round(time.monotonic() - self._t_baslangic, 2)
                elif not h:
                    GLib.timeout_add(100, lambda: (hazir_bekle(), False)[1])
            self._js("!!(window.yukiDurum && window.yukiDurum.hazir)", bak)
        hazir_bekle()

        def bitir():
            sonuc["sure_sn"] = round(time.monotonic() - t0, 2)
            sonuc["host_cpu_sn"] = round(time.process_time() - c0, 3)
            Gtk.main_quit()

        def basla():
            def durum_al(d):
                sonuc["durum"] = d
                self._kuru_ek(sonuc, bitir)
            self._js("window.yukiTikla && window.yukiTikla(); JSON.parse(JSON.stringify(window.yukiDurum || null))",
                     durum_al)
            return False

        GLib.timeout_add(int(sure * 1000), basla)
        GLib.timeout_add(int((sure + 30) * 1000), lambda: (sonuc.setdefault("zaman_asimi", True), Gtk.main_quit(), False)[2])
        Gtk.main()
        if self.kopru:                        # F2: bağlantı + komut + balon kaydı (token'sız)
            sonuc["baglanti"] = self.kopru.ozet()
        print(json.dumps(sonuc, ensure_ascii=False))
        d = sonuc.get("durum") or {}
        return 0 if d.get("hazir") and not d.get("hata") else 4

    def calistir(self) -> int:
        try:
            from gi.repository import GLibUnix
            ekle = GLibUnix.signal_add
        except (ImportError, AttributeError):
            ekle = GLib.unix_signal_add
        ekle(GLib.PRIORITY_DEFAULT, signal.SIGUSR1, self.goster_gizle)
        ekle(GLib.PRIORITY_DEFAULT, signal.SIGUSR2, lambda: self.monitor_degistir(1))
        self.win.show_all()
        Gtk.main()
        return 0

    # ── kuru F1 senaryosu: olaylar sahte, pencere ekrana çıkmaz ──
    def _adimlar(self, adimlar, sonra) -> None:
        """[(bekle_ms, f)] sırayla; f(devam) devam'ı çağırınca sonraki adım."""
        def kos(i):
            if i >= len(adimlar):
                sonra()
                return
            ms, f = adimlar[i]
            GLib.timeout_add(ms, lambda: (f(lambda: kos(i + 1)), False)[1])
        kos(0)

    def _senaryo_f1(self, sonuc: dict, sonra) -> None:
        f1 = sonuc.setdefault("f1", {})
        g = self._geo()
        bas = self.bas_daire
        hx, hy = (bas[0], bas[1]) if bas else (self.w / 2, self.h * 0.2)
        gx, gy = self.w / 2, self.h * 0.72                    # gövde (bacak üstü): baş dairesinin dışında
        f1["bas_daire"], f1["govde_basta"] = bas, basta_mi(gx, gy, bas)
        olay = lambda tip, x, y, d=1: SimpleNamespace(type=tip, button=d, x=x, y=y)
        P, R = Gdk.EventType.BUTTON_PRESS, Gdk.EventType.BUTTON_RELEASE

        def tikla(x, y):
            def f(devam):
                self._tik(None, olay(P, x, y))
                self._birak(None, olay(R, x, y))
                devam()
            return f

        def bas_tut(x, y):
            return lambda devam: (self._tik(None, olay(P, x, y)), devam())

        def birak(x, y):
            return lambda devam: (self._birak(None, olay(R, x, y)), devam())

        sahte = {"p": (1000.0, 500.0)}

        def imlec_ayarla(p):
            return lambda devam: (sahte.__setitem__("p", p), devam())

        def suru(p):
            def f(devam):
                sahte["p"] = p
                self._son_surukle = 0.0
                self._hareket(None, olay(Gdk.EventType.MOTION_NOTIFY, gx, gy))
                f1.setdefault("surukle_marj", []).append([self.sol, self.alt])
                devam()
            return f

        def oku(ad, kod):
            return lambda devam: self._js(kod, lambda v: (f1.__setitem__(ad, v), devam()))

        def kayit_oku(ad):
            return lambda devam: (f1.__setitem__(ad, konum_oku(self.kayit_yolu) if self.kayit_yolu else None), devam())

        adim = [(0, tikla(hx, hy))] + [(150, tikla(hx, hy)) for _ in range(4)]      # başa 5 tık
        adim += [(1500, tikla(gx, gy)),                                              # zincir bitti → gövdeye 1 tık
                 (1500, bas_tut(gx, gy)), (int(UZUN_BAS_SN * 1000) + 300, birak(gx, gy))]   # uzun bas
        # sürükle: sahte global imleç; sınır dışına it → kenetlenir; sonra ortaya
        self._imlec = lambda: sahte["p"]
        x0, y0 = 1000.0, 500.0
        adim += [(1500, imlec_ayarla((x0, y0))), (0, bas_tut(gx, gy)), (30, suru((x0 + 3, y0))),
                 (30, suru((x0 - 9000, y0 + 9000))), (30, suru((x0 + 9000, y0 - 9000))),
                 (30, suru((x0 - 300, y0 - 120))), (30, birak(gx, gy)), (50, kayit_oku("kayit"))]
        f1["beklenen_orta"] = list(kenetle(self.sol - 300, self.alt + 120, self.w, self.h, g[2], g[3]))
        f1["beklenen_sinir"] = [[0, 0], [g[2] - self.w, g[3] - self.h]]
        if self.KIP == "tam":                                 # bakış: imleç başın solunda / sağında / çok uzakta
            def bakis_dene(dx, ad):
                def f(devam):
                    pk = pencere_kutusu(self._geo(), self.sol, self.alt, self.w, self.h)
                    sahte["p"] = (pk[0] + hx + dx, pk[1] + hy)
                    self._bakis_tur()
                    self._js("window.yukiBakOlc(48)", lambda v: (f1.__setitem__(ad, v), devam()))
                return f
            def kare(ad):     # --kare verildiyse bakış anının ekran dışı karesi
                def f(devam):
                    if not self.arg.kare:
                        return devam()
                    def yaz(url):
                        if url and url.startswith("data:image/png;base64,"):
                            import base64
                            yol = Path(self.arg.kare) / f"tam-{ad}.png"
                            yol.parent.mkdir(parents=True, exist_ok=True)
                            yol.write_bytes(base64.b64decode(url.split(",", 1)[1]))
                            sonuc.setdefault("kareler", []).append(str(yol))
                        devam()
                    self._js("window.yukiKare(null, 0)", yaz)
                return f
            adim += [(100, oku("bakis_yok", "window.yukiBakOlc(48)")), (0, bakis_dene(-400, "bakis_sol")),
                     (0, kare("bakis-sol")), (0, bakis_dene(400, "bakis_sag")), (0, kare("bakis-sag")),
                     (0, bakis_dene(5000, "bakis_uzak"))]
        # SIGUSR1: gizliyken kare sayacı durur, gösterince sürer
        sayac = "window.yukiDurum.kare"
        adim += [(200, lambda d: (self.goster_gizle(), d())), (300, oku("kare_gizli_0", sayac)),
                 (1500, oku("kare_gizli_1", sayac)), (0, lambda d: (self.goster_gizle(), d())),
                 (1500, oku("kare_acik", sayac))]
        # monitör değiştir (orta tık): boy yeni monitöre göre, konum kaydı yeni monitörü yazar
        adim += [(0, lambda d: (f1.__setitem__("mon_once", [self.mon_i, self.w, self.h]),
                                self._tik(None, olay(P, gx, gy, 2)),
                                f1.__setitem__("mon_sonra", [self.mon_i, self.w, self.h, self._geo()[3], self._geo()[2]]), d())),
                 (300, oku("sayfa_boyut", "window.yukiDurum.boyut || null")), (0, kayit_oku("kayit_mon"))]

        def bitti():
            self._imlec = imlec_oku
            f1["dokunma"] = list(self.dokunma.gecmis)
            sonra()
        self._adimlar(adim, bitti)


class YukiTamGovde(YukiGovde):
    """Kip tam: OYUN kipinin Yuki'si (yuki3d.vrm) baştan ayağa, ekranın alt kenarında AYAKTA.

    Pencere boyu ekran yüksekliğinin ≈%45'i (`--boyut`: ≤1 oran, >1 piksel), eni boyun yarısı.
    Tıklama bölgesi çizilen siluetten gelir: sayfa saniyede bir `window.yukiBolge`'yi (24 şerit) günceller,
    host saniyede bir okur, sürüm değiştiyse input bölgesini yeniler (el sallarken kol da tıklanır).
    """
    SAYFA = "masaustu/web/yuki-tam.html"
    KIP = "tam"

    def __init__(self, arg) -> None:
        self._bolge_surum = 0
        # takılma sayacı: host'un ekrana basışları + son log satırındaki haller
        self.boya = KareSayaci()
        self._son_boya: float | None = None
        self._boyalar: collections.deque = collections.deque(maxlen=96)   # son basışların duvar saati (ms)
        self._log_once: tuple[dict | None, dict | None] = (None, None)
        self._log_ozet_t = time.monotonic()
        super().__init__(arg)
        self.win.connect("realize", self._boya_bagla)
        self.etk = EtkilesimHost(self)                        #: PANEL'e otur · çubuğa uzan · el salla
        if not arg.kuru:
            # sayfa durumu kendisi yollar (DURUM_YOLU); saniyelik _bolge_yokla canlıda donma yaratıyordu
            self.srv.teslim = lambda d: GLib.idle_add(self._durum_geldi, d)
            GLib.timeout_add(BAKIS_MS, self._bakis_tur)
            GLib.timeout_add(1000, self.etk.tur)

    def capa_geldi(self, c: dict) -> None:                   # balon.Kopru →
        self.etk.capa_geldi(c)

    def boyut_uygula(self) -> None:
        """Pencere + WebView boyu self.w × self.h (poz kesiti ↔ ayakta). Sayfanın kadrajını çağıran ayrıca kurar."""
        self.win.set_size_request(self.w, self.h)
        self.web.set_size_request(self.w, self.h)
        self.win.resize(self.w, self.h)

    def _boya_bagla(self, *_) -> None:
        saat = self.win.get_frame_clock()
        if saat is not None:
            saat.connect("after-paint", self._boyandi)

    def _boyandi(self, _saat) -> None:
        simdi, saat = time.monotonic(), time.time() * 1000
        if self._son_boya is not None and not self.gizli:
            self.boya.ekle((simdi - self._son_boya) * 1000, 10 if self.uyku else self.arg.fps, saat)
        self._son_boya = simdi
        self._boyalar.append(saat)

    def _takilma_logla(self, b) -> str | None:
        """Saniyede bir: yeni takılma varsa (ya da OZET_SN dolduysa) log'a TEK satır. Satırı döner (test)."""
        sayfa = b.get("takilma") if isinstance(b, dict) else None
        host = self.boya.ozet()
        ozet = time.monotonic() - self._log_ozet_t >= OZET_SN
        komut = b.get("komut") if isinstance(b, dict) else None
        ek = (f"imleç_max {self._imlec_max_ms:.1f}ms · uyku {int(self.uyku)} · gpu {self.gpu} · gl {'kapali' if os.environ.get('GDK_GL') == 'disable' else 'acik'}"
              + (f" · komut {komut[0]}/{komut[1]} hata" if isinstance(komut, list) and len(komut) == 2 else "")
              + ses_ozeti(b.get("bag") if isinstance(b, dict) else None))
        satir = takilma_satiri(time.strftime("%H:%M:%S"), sayfa, self._log_once[0], host, self._log_once[1], ozet, ek,
                               self._boyalar)
        if satir:
            print(satir, flush=True)
            self._log_once = (sayfa, host)
            self._log_ozet_t = time.monotonic()
            self._imlec_max_ms = 0.0
        return satir

    def _olcu(self) -> tuple[int, int]:
        ekran_h = self.mon.get_geometry().height if self.mon is not None else 1080
        return tam_boy_olcu(self.arg.boyut, ekran_h)

    def _ilk_bolge(self) -> list[tuple[int, int, int, int]]:
        # siluet gelene kadar (≈1 sn) gövdenin orta sütunu: kenarlar ilk andan geçirgen
        return [(self.w // 4, self.h // 30, self.w // 2, self.h - self.h // 30)]

    def _sorgu(self) -> str:
        return f"fps={self.arg.fps}&uyku={int(self.arg.uyku)}&w={self.w}&h={self.h}&hareket={getattr(self.arg, 'hareket', 'a')}"

    def _bolge_uygula(self, b) -> bool:
        if b:
            self.bas_daire = tuple(b["bas"]) if b.get("bas") else None
            self.uyku = bool(b.get("uyku"))
        if not b or not b.get("kutular") or b.get("surum") == self._bolge_surum:
            return False
        self._bolge_surum = b["surum"]
        self.bolge = [tuple(int(v) for v in k) for k in b["kutular"]]
        self._girdi_bolgesi()
        return True

    def _durum_geldi(self, d: dict) -> bool:
        """Sayfanın saniyelik POST'u (sunucu iş parçacığından idle_add ile, ana iş parçacığında)."""
        self._bolge_uygula(d)
        self._takilma_logla(d)
        self.etk.kadraj_geldi(d.get("poz_kadraj"))           # etkileşim pozları
        return False

    def _bolge_yokla(self) -> bool:
        """Yalnız kuru ölçüm/test: sonucu evaluate_javascript ile okur (canlıda KULLANMA, bkz. _Isleyici)."""
        self._js("window.yukiBolge ? {surum: window.yukiBolge.surum, kutular: window.yukiBolge.kutular, bas: window.yukiBolge.bas, uyku: window.yukiDurum.uyku, takilma: window.yukiDurum.takilma} : null",
                 lambda b: (self._bolge_uygula(b), self._takilma_logla(b)))
        return True

    def _kuru_ek(self, sonuc: dict, bitir) -> None:
        def bolge_al(b):
            sonuc["siluet_bolgesi"] = None
            if self._bolge_uygula(b):
                sonuc["siluet_bolgesi"] = {"serit": len(self.bolge), "alan_orani": round(
                    sum(k[2] * k[3] for k in self.bolge) / (self.w * self.h), 2)}
            self._tezgah(sonuc, kare_basla)

        def kare_basla():
            kareler = [("bos", None, 0), ("selam", "selam", 2.5)] if self.arg.kare else []   # selam 2,5. sn: el başın üstünde
            kare_al(kareler)

        def kare_al(kalan):
            if not kalan:
                son = lambda: self._js("JSON.parse(JSON.stringify(window.yukiDurum))",
                                       lambda d: (sonuc.__setitem__("durum", d), bitir()))
                self._senaryo_f1(sonuc, son) if self.arg.senaryo == "f1" else son()
                return
            ad, klip, sn = kalan[0]

            def yaz(url):
                if url and url.startswith("data:image/png;base64,"):
                    import base64
                    yol = Path(self.arg.kare) / f"tam-{ad}.png"
                    yol.parent.mkdir(parents=True, exist_ok=True)
                    yol.write_bytes(base64.b64decode(url.split(",", 1)[1]))
                    sonuc.setdefault("kareler", []).append(str(yol))
                kare_al(kalan[1:])
            self._js(f"window.yukiKare({json.dumps(klip)}, {sn})", yaz)

        # klipler arkadan iner; ölçümden önce hepsinin gelmesini bekle (en çok 10 sn)
        def klipler_bekle(n=0):
            def bak(d):
                if (d and d.get("klipler_ms") is not None) or n >= 20:
                    self._js("window.yukiBolge ? {surum: window.yukiBolge.surum, kutular: window.yukiBolge.kutular, bas: window.yukiBolge.bas, uyku: window.yukiDurum.uyku} : null",
                             bolge_al)
                else:
                    GLib.timeout_add(500, lambda: (klipler_bekle(n + 1), False)[1])
            self._js("JSON.parse(JSON.stringify(window.yukiDurum))", bak)
        klipler_bekle()
