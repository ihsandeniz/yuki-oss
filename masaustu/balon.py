"""Masaüstü Yuki F2 — köprü: bağlantı komutları → sayfa (yukiBag) + konuşma balonu + çift tık giriş kutusu.

NEDEN AYRI PENCERE: Yuki'nin penceresi karakter kadar; balon onun içine çizilirse yüzün üstüne biner ve
tıklama bölgesini (siluet şeritleri) bozar. Balon ve giriş kutusu ayrı, küçük gtk-layer-shell yüzeyleri:
- balon tıklamayı geçirir (boş input bölgesi), klavye almaz;
- giriş kutusu yalnız açıkken klavye alır (KeyboardMode.ON_DEMAND, PLAN § Sohbet etme), Esc kapatır.
Konum Yuki'nin o anki kenar boşluklarından okunur (F1 sürüklemesiyle de doğru kalır).

Kuru kipte (`--kuru`) hiçbir pencere GÖSTERİLMEZ; balonlar yalnız kayda geçer (ekranda açılmaz).
"""
from __future__ import annotations

import json
import os
import time

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GtkLayerShell", "0.1")
from gi.repository import Gdk, GLib, Gtk, GtkLayerShell  # noqa: E402
import cairo  # noqa: E402

from baglanti import Baglanti, token_bul, ws_adresi  # noqa: E402

BALON_W = 300
GIRIS_W = 340
GIRIS_SN = 45            # açık ama dokunulmayan kutu bu kadar sonra kapanır
_CSS = b"""
.yuki-balon { background-color: rgba(14,16,26,0.93); border: 1px solid rgba(201,163,82,0.45);
  border-radius: 14px; padding: 10px 14px; color: #ece9f6; font-size: 14px; }
.yuki-balon .devami { color: #a19eb8; font-size: 12px; }
.yuki-giris { background-color: rgba(14,16,26,0.96); border: 1px solid rgba(165,140,255,0.6);
  border-radius: 14px; padding: 8px; }
.yuki-giris entry { background: rgba(255,255,255,0.06); color: #ece9f6; border: none; border-radius: 10px;
  padding: 8px 10px; min-height: 28px; font-size: 14px; caret-color: #a58cff; }
.yuki-giris label { color: #a19eb8; font-size: 12px; }
"""


def _stil() -> None:
    p = Gtk.CssProvider()
    p.load_from_data(_CSS)
    ekran = Gdk.Screen.get_default()
    if ekran is not None:
        Gtk.StyleContext.add_provider_for_screen(ekran, p, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)


def _katman(win: Gtk.Window, govde, klavye: bool) -> None:
    gorsel = win.get_screen().get_rgba_visual() if win.get_screen() else None
    if gorsel is not None:
        win.set_visual(gorsel)
    win.set_app_paintable(True)
    win.set_decorated(False)
    if not GtkLayerShell.is_supported():
        return
    GtkLayerShell.init_for_window(win)
    GtkLayerShell.set_namespace(win, "yuki-masaustu-balon")
    GtkLayerShell.set_layer(win, GtkLayerShell.Layer.OVERLAY if govde.arg.katman == "overlay" else GtkLayerShell.Layer.TOP)
    if govde.mon is not None:
        GtkLayerShell.set_monitor(win, govde.mon)
    GtkLayerShell.set_anchor(win, GtkLayerShell.Edge.LEFT, True)
    GtkLayerShell.set_anchor(win, GtkLayerShell.Edge.BOTTOM, True)
    GtkLayerShell.set_exclusive_zone(win, 0)
    GtkLayerShell.set_keyboard_mode(win, GtkLayerShell.KeyboardMode.ON_DEMAND if klavye else GtkLayerShell.KeyboardMode.NONE)
    win.connect("draw", _saydam_zemin)


def _saydam_zemin(_w, cr) -> bool:
    cr.set_source_rgba(0, 0, 0, 0)
    cr.set_operator(cairo.OPERATOR_SOURCE)
    cr.paint()
    cr.set_operator(cairo.OPERATOR_OVER)
    return False


def yuki_konumu(govde) -> tuple[int, int]:
    """Yuki penceresinin sol/alt kenar boşluğu (F1 sürüklemesi değiştirse de o anki değer)."""
    x = y = None
    if getattr(govde, "katman", False):
        try:
            x = GtkLayerShell.get_margin(govde.win, GtkLayerShell.Edge.LEFT)
            y = GtkLayerShell.get_margin(govde.win, GtkLayerShell.Edge.BOTTOM)
        except (AttributeError, TypeError):
            pass
    if x is None:
        x = govde.arg.x if govde.arg.x is not None else (
            max(0, govde.mon.get_geometry().width - govde.w - 40) if govde.mon else 40)
    if y is None:
        y = govde.arg.zemin
    return int(x), int(y)


def balon_yeri(yx: int, yy: int, w: int, h: int, bw: int, kip: str) -> tuple[int, int]:
    """Balon Yuki'nin başının solunda: tam boyda baş üstte (%80), portrede ortada (%55). Ekrandan taşmaz."""
    oran = 0.80 if kip == "tam" else 0.55
    x = yx + w // 4 - bw
    if x < 8:                       # solda yer yok (Yuki sol kenarda) → sağına
        x = yx + w - w // 4
    return int(x), int(yy + h * oran)


class Balon:
    def __init__(self, govde, gorunmez: bool) -> None:
        self.govde = govde
        self.gorunmez = gorunmez
        self.kayit: list[dict] = []
        self._zaman = 0
        self.win = None
        if gorunmez:
            return
        self.win = Gtk.Window()
        self.win.set_title("Yuki — balon")
        _katman(self.win, govde, klavye=False)
        kutu = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        kutu.get_style_context().add_class("yuki-balon")
        self.yazi = Gtk.Label(xalign=0)
        self.yazi.set_line_wrap(True)
        self.yazi.set_max_width_chars(34)
        self.devami = Gtk.Label(label="devamı ana pencerede", xalign=0)
        self.devami.get_style_context().add_class("devami")
        kutu.pack_start(self.yazi, False, False, 0)
        kutu.pack_start(self.devami, False, False, 0)
        self.win.add(kutu)
        self.win.set_size_request(BALON_W, -1)
        self.win.connect("realize", lambda *_: self.win.get_window().input_shape_combine_region(cairo.Region(), 0, 0))

    def goster(self, metin: str, sn: float, devami: bool = False) -> None:
        self.kayit.append({"metin": metin, "sn": sn, "devami": devami, "t": round(time.monotonic(), 2)})
        del self.kayit[:-20]
        if self.win is None:
            return
        self.yazi.set_text(metin)
        self.devami.set_visible(devami)
        if GtkLayerShell.is_supported():
            yx, yy = yuki_konumu(self.govde)
            x, y = balon_yeri(yx, yy, self.govde.w, self.govde.h, BALON_W, self.govde.KIP)
            GtkLayerShell.set_margin(self.win, GtkLayerShell.Edge.LEFT, x)
            GtkLayerShell.set_margin(self.win, GtkLayerShell.Edge.BOTTOM, y)
        self.win.show_all()
        self.devami.set_visible(devami)
        if self._zaman:
            GLib.source_remove(self._zaman)
        self._zaman = GLib.timeout_add(int(sn * 1000), self.gizle)

    def gizle(self) -> bool:
        self._zaman = 0
        if self.win is not None:
            self.win.hide()
        return False


class Giris:
    """Çift tık → küçük giriş kutusu. Enter gönderir, Esc kapatır. Klavye yalnız açıkken."""

    def __init__(self, govde, gonder) -> None:
        self.govde = govde
        self.gonder = gonder
        self._zaman = 0
        self.win = Gtk.Window()
        self.win.set_title("Yuki — yaz")
        _katman(self.win, govde, klavye=True)
        kutu = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        kutu.get_style_context().add_class("yuki-giris")
        self.alan = Gtk.Entry()
        self.alan.set_placeholder_text("Yuki'ye yaz…")
        self.alan.set_max_length(2000)
        self.alan.connect("activate", lambda *_: self.yolla())
        self.alan.connect("changed", lambda *_: self._sure_tazele())
        ipucu = Gtk.Label(label="Enter gönder · Esc kapat", xalign=0)
        kutu.pack_start(self.alan, False, False, 0)
        kutu.pack_start(ipucu, False, False, 0)
        self.win.add(kutu)
        self.win.set_size_request(GIRIS_W, -1)
        self.win.connect("key-press-event", self._tus)

    def ac(self) -> None:
        if GtkLayerShell.is_supported():
            yx, yy = yuki_konumu(self.govde)
            x, y = balon_yeri(yx, yy, self.govde.w, self.govde.h, GIRIS_W, self.govde.KIP)
            GtkLayerShell.set_margin(self.win, GtkLayerShell.Edge.LEFT, x)
            GtkLayerShell.set_margin(self.win, GtkLayerShell.Edge.BOTTOM, max(0, y - 70))
        self.win.show_all()
        self.alan.grab_focus()
        self._sure_tazele()

    def kapat(self) -> bool:
        self._zaman = 0
        self.alan.set_text("")
        self.win.hide()
        return False

    def yolla(self) -> str | None:
        metin = self.alan.get_text().strip()
        if not metin:
            return None
        tur = self.gonder(metin)
        self.kapat()
        return tur

    def _tus(self, _w, olay) -> bool:
        if olay.keyval == Gdk.KEY_Escape:
            self.kapat()
            return True
        return False

    def _sure_tazele(self) -> None:
        if self._zaman:
            GLib.source_remove(self._zaman)
        self._zaman = GLib.timeout_add(GIRIS_SN * 1000, self.kapat)


class Kopru:
    """Baglanti (arka iş parçacığı) → GTK ana döngüsü → sayfa `window.yukiBag` + balon."""

    def __init__(self, govde, adres: str) -> None:
        self.govde = govde
        _stil()
        self.balon = Balon(govde, gorunmez=bool(govde.arg.kuru))
        self.giris = None if govde.arg.kuru else Giris(govde, self.gonder)
        self.komut_say: dict[str, int] = {}
        self.ses_sonuc: list = []
        self.baglanti = Baglanti(adres, lambda k: GLib.idle_add(self._uygula, k)).baslat()

    def _uygula(self, k: tuple) -> bool:
        ad = k[0]
        self.komut_say[ad] = self.komut_say.get(ad, 0) + 1
        js = lambda kod, geri=None: self.govde._js(f"window.yukiBag && ({kod})", geri)  # noqa: E731
        if ad == "yuz":
            js(f"yukiBag.yuz({json.dumps(k[1])}, {int(k[2])})")
        elif ad == "selam":
            js("yukiBag.selam()")
        elif ad == "dusun":
            js(f"yukiBag.dusun({json.dumps(bool(k[1]))})")
        elif ad == "konus":
            js(f"yukiBag.konus({json.dumps(bool(k[1]))})")
        elif ad == "konus_sure":
            js(f"yukiBag.konusSure({float(k[1])})")
        elif ad == "ses":
            # sesCal bir Promise döner; evaluate_javascript Promise'i beklemez → süreyi ayrıca sorma
            js(f"(yukiBag.sesCal({json.dumps(k[1])}, {json.dumps(bool(k[2]))}), true)")
        elif ad == "balon":
            self.balon.goster(k[1], float(k[2]), bool(k[3]))
        elif ad == "capa":                 #: yalnız saklanır; karar host'un 1 sn'lik turunda
            geri = getattr(self.govde, "capa_geldi", None)
            if geri:
                geri(k[1])
        return False

    def gonder(self, metin: str) -> str | None:
        tur = self.baglanti.gonder(metin)
        if tur is None:
            self.balon.goster("Bağlantı yok — mesaj gitmedi. Yuki açık mı?", 5.0)
        else:
            self.govde._js("window.yukiBag && yukiBag.dusun(true)")
        return tur

    def giris_ac(self) -> None:
        if self.giris is not None:
            self.giris.ac()

    def ozet(self) -> dict:
        return {**self.baglanti.ozet(), "komut": dict(self.komut_say), "balon": self.balon.kayit[-10:]}


def kopru_kur(govde) -> Kopru | None:
    """Yuki gövdesine bağlantıyı tak. `--baglantisiz` ya da kuru kipte açık `--backend` yoksa bağlanmaz
    (testler canlı backend'e kendiliğinden bağlanmasın)."""
    arg = govde.arg
    if getattr(arg, "baglantisiz", False):
        return None
    taban = getattr(arg, "backend", None)
    if arg.kuru and not taban:
        return None
    taban = taban or os.environ.get("YUKI_BACKEND", "http://127.0.0.1:8001")
    from yuki_govde import DEPO
    return Kopru(govde, ws_adresi(taban, token_bul(DEPO)))
