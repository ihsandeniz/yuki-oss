#!/usr/bin/env python3
"""Masaüstü Yuki — ekranın köşesinde baştan ayağa duran, nefes alan, tıklayınca el sallayan Yuki.

NEDEN VAR: Yuki'nin masaüstünde de durması istendi. Katman yüzeyi (gtk-layer-shell) destekleniyorsa
(wlroots/KDE Wayland) blur/gölge/kenarlık almayan, her çalışma alanında görünen bir yüzey olur;
desteklenmiyorsa X11'de normal, çerçevesiz, üstte kalan bir pencere açılır. İkisi de yoksa (GNOME Wayland
katmansız, macOS, Windows) çıkış 3 ile "bu masaüstünde desteklenmiyor" der — hata yığını atmaz.

Model: kullanıcının KENDİ VRM dosyası (depoda model yok). `--model` / `YUKI_MASAUSTU_VRM`; yoksa çıkış 6.

Tıklama: yalnız çizilen siluet tıklanır, gerisi alttaki pencereye geçer.
  sol tık → el sallar · çift tık → yaz · orta tık → sonraki monitör · sağ tık → kapanır

Kullanım:
  python3 masaustu.py --model ~/models/yuki.vrm
  python3 masaustu.py --model m.vrm --kuru --sure 3     # EKRANA ÇIKMADAN başlatma testi → JSON özet
Dokunma: başa tık → utangaç · 3. art arda tık → şaşkın · 5. → kızgın · uzun bas → sevinç ·
basılı tut + sürükle → yer (kaydedilir) · SIGUSR2 → sonraki monitör · SIGUSR1 → göster/gizle
Çıkış: 0 tamam · 2 bağımlılık yok (gi/WebKit2) · 3 bu masaüstünde desteklenmiyor · 4 yuki motoru kurulamadı ·
5 zaten açık (tek örnek kilidi, tek_ornek.py) · 6 model yok
"""
from __future__ import annotations

import argparse
import os
import signal
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from davranis import arayuz_gl_ortami  # noqa: E402  GTK'den ÖNCE: GDK_GL gtk_init'te okunur

CIKIS_BAGIMLILIK, CIKIS_DESTEKLENMIYOR, CIKIS_MOTOR, CIKIS_ACIK, CIKIS_MODEL_YOK = 2, 3, 4, 5, 6
X11_DENENDI = "YUKI_MASAUSTU_X11"        # katman kabuğu yok → bir kez XWayland'e yeniden başlat


def model_yolu(arg_model: str | None, ortam=None) -> Path | None:
    """`--model` → `YUKI_MASAUSTU_VRM`; dosya yoksa/`.vrm` değilse None ('model yok')."""
    ortam = os.environ if ortam is None else ortam
    ham = (arg_model or ortam.get("YUKI_MASAUSTU_VRM") or "").strip()
    if not ham:
        return None
    yol = Path(ham).expanduser()
    return yol if yol.is_file() and yol.suffix.lower() == ".vrm" else None


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Masaüstü Yuki")
    ap.add_argument("--model", default=None, help="kullanıcının kendi VRM dosyası (varsayılan YUKI_MASAUSTU_VRM)")
    ap.add_argument("--boyut", type=float, default=None,
                    help="boy: ≤1 ekran yüksekliği oranı (varsayılan 0.45) ya da piksel")
    ap.add_argument("--hareket", choices=("a", "b"), default="a",
                    help="hareket seti: a sakin (varsayılan) · b canlı (web/hareket.js)")
    ap.add_argument("--fps", type=int, default=24, help="uyanık kare hızı (uyku 10)")
    ap.add_argument("--monitor", type=int, default=None,
                    help="monitör sırası (varsayılan: kayıtlı konumun monitörü, yoksa 0)")
    ap.add_argument("--katman", choices=("top", "overlay"), default="top",
                    help="top: pencerelerin üstü, tam ekran video örter · overlay: her şeyin üstü (yalnız katman kabuğu)")
    ap.add_argument("--x", type=int, default=None, help="soldan piksel (varsayılan sağ alt)")
    ap.add_argument("--zemin", type=int, default=None, help="alt kenardan piksel (varsayılan: kayıtlı konum, yoksa 0)")
    ap.add_argument("--uyku", type=float, default=60.0, help="etkileşimsiz kaç sn sonra uyku kipi")
    ap.add_argument("--kuru", action="store_true", help="ekrana çıkmadan başlat, ölç, çık")
    ap.add_argument("--backend", default=None, help="Yuki backend adresi (varsayılan YUKI_BACKEND ya da "
                    "http://127.0.0.1:8001; --kuru'da verilmezse bağlanmaz)")
    ap.add_argument("--baglantisiz", action="store_true", help="backend'e bağlanma (yalnız beden)")
    ap.add_argument("--sure", type=float, default=3.0, help="--kuru koşu süresi (sn)")
    ap.add_argument("--kare", default=None, help="--kuru: ekran dışı kareleri (PNG) bu klasöre yaz")
    ap.add_argument("--senaryo", choices=("f1",), default=None,
                    help="--kuru: sahte olaylarla senaryo (dokunma, sürükleme, bakış, gizle, monitör)")
    ap.add_argument("--tezgah", type=int, default=120, help="--kuru: kare maliyeti için art arda çizilecek kare sayısı (0 = yok)")
    return ap


def _sinyaller(Gtk, GLib) -> None:
    try:
        from gi.repository import GLibUnix
        ekle = GLibUnix.signal_add
    except (ImportError, AttributeError):
        ekle = GLib.unix_signal_add
    for sig in (signal.SIGINT, signal.SIGTERM):
        ekle(GLib.PRIORITY_DEFAULT, sig, lambda *_: (Gtk.main_quit(), False)[1])


def main(argv=None) -> int:
    arg = _parser().parse_args(argv)
    model = model_yolu(arg.model)
    if model is None:
        print("✗ model yok — kullanıcının kendi .vrm dosyası gerekir (--model ya da YUKI_MASAUSTU_VRM)", file=sys.stderr)
        return CIKIS_MODEL_YOK
    arg.model = str(model)
    if not arg.kuru and not (os.environ.get("WAYLAND_DISPLAY") or os.environ.get("DISPLAY")):
        print("✗ bu masaüstünde desteklenmiyor — grafik oturumu yok", file=sys.stderr)
        return CIKIS_DESTEKLENMIYOR
    arayuz_gl_ortami(os.environ)
    try:
        import gi
        gi.require_version("Gtk", "3.0")
        gi.require_version("Gdk", "3.0")
        gi.require_version("WebKit2", "4.1")
        from gi.repository import GLib, Gtk  # noqa: F401
        import yuki_govde
    except (ImportError, ValueError) as e:       # gi / WebKit2 yok (ör. macOS, Windows)
        print(f"✗ bu masaüstünde desteklenmiyor — gerekli GTK/WebKit kitaplığı yok ({e})", file=sys.stderr)
        return CIKIS_BAGIMLILIK
    if not arg.kuru:
        from tek_ornek import al, birak       # elle (run.sh) ve Yuki'den (backend) açılabiliyor → tek örnek
        kilit, sahip = al()
        if kilit is None:
            print(f"✗ masaüstü Yuki zaten açık (pid {sahip})", file=sys.stderr)
            return CIKIS_ACIK
        import atexit
        atexit.register(birak, kilit)
        d = yuki_govde.yuzey_durumu()
        if d == "wayland_katmansiz" and os.environ.get("DISPLAY") and not os.environ.get(X11_DENENDI):
            env = dict(os.environ, GDK_BACKEND="x11", **{X11_DENENDI: "1"})   # XWayland: normal çerçevesiz üstte pencere
            birak(kilit)
            os.execvpe(sys.executable, [sys.executable, *sys.argv], env)
        if d not in ("katman", "x11"):
            print("✗ bu masaüstünde desteklenmiyor — ne katman kabuğu (wlr-layer-shell) ne X11 var", file=sys.stderr)
            return CIKIS_DESTEKLENMIYOR
    g = yuki_govde.YukiTamGovde(arg)
    if arg.kuru:
        return g.kuru(arg.sure)
    _sinyaller(Gtk, GLib)
    return g.calistir()


if __name__ == "__main__":
    sys.exit(main())
