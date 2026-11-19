#!/usr/bin/env python3
"""Masaüstü Yuki — host çevresi (ekrana pencere AÇILMAZ): ölçü/alfa mantığı, yerel sunucu (model + beyaz liste),
GPU ortamı, imleç, çıkış kodları ('model yok' = 6), depoda .vrm yok. Gerçek WebView ölçümü (--kuru) kullanıcının
kendi VRM'ini ister: `YUKI_TEST_VRM=/yol/model.vrm` yoksa atlanır.

Kullanım: /usr/bin/python3 tests/test_masaustu.py   (gi gerektirenler gi yoksa atlanır)
"""
from __future__ import annotations

import http.client
import os
import subprocess
import sys
import tempfile
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
DEPO = KOK.parent
sys.path.insert(0, str(KOK))
gecti = kaldi = 0


def kontrol(ad: str, kosul: bool, ayrinti: str = "") -> None:
    global gecti, kaldi
    if kosul:
        gecti += 1
        print("  ✓", ad)
    else:
        kaldi += 1
        print("  ✗", ad, ayrinti)


def kos(*args, env=None, timeout=60):
    return subprocess.run([sys.executable, str(KOK / "masaustu.py"), *args], capture_output=True, text=True,
                          timeout=timeout, env=env or {k: v for k, v in os.environ.items() if k != "YUKI_MASAUSTU_VRM"})


def saf() -> None:
    print("— ölçü + tıklama bölgesi (GTK'siz)")
    from yuki_sprite import alfa_bantlari, alfa_kutusu, tam_boy_olcu
    kontrol("varsayılan boy ekranın %45'i, en boyun yarısı", tam_boy_olcu(None, 1080) == (243, 486))
    kontrol("≤1 oran, >1 piksel", tam_boy_olcu(0.6, 1000) == (300, 600) and tam_boy_olcu(600, 1000) == (300, 600))
    kontrol("boy 200 ile ekran yüksekliği arasında", tam_boy_olcu(50, 1000)[1] == 200 and tam_boy_olcu(5000, 1000)[1] == 1000)
    w = h = 8
    saydam = bytes(w * h * 4)
    kontrol("tam saydam → kutu yok", alfa_kutusu(saydam, w, h, w * 4) is None and alfa_bantlari(saydam, w, h, w * 4) == [])
    piks = bytearray(w * h * 4)
    for y in range(2, 6):
        for x in range(3, 5):
            piks[(y * w + x) * 4 + 3] = 255
    kontrol("alfa kutusu dolu pikselleri sarar", alfa_kutusu(bytes(piks), w, h, w * 4) == (3, 2, 2, 4))
    kontrol("şeritler karakterin şekline uyar", all(k[0] == 3 and k[2] == 2 for k in alfa_bantlari(bytes(piks), w, h, w * 4, bant=4)))


def model_ve_cikis() -> None:
    print("— model yolu + çıkış kodları")
    import masaustu
    with tempfile.TemporaryDirectory() as d:
        vrm, png = Path(d) / "k.vrm", Path(d) / "k.png"
        vrm.write_bytes(b"glTF")
        png.write_bytes(b"x")
        kontrol("verilen .vrm bulunur", masaustu.model_yolu(str(vrm), {}) == vrm)
        kontrol("ortamdan gelir", masaustu.model_yolu(None, {"YUKI_MASAUSTU_VRM": str(vrm)}) == vrm)
        kontrol("yok / boş / .vrm değil → None", masaustu.model_yolu(None, {}) is None
                and masaustu.model_yolu(str(Path(d) / "yok.vrm"), {}) is None and masaustu.model_yolu(str(png), {}) is None)
    r = kos("--kuru")
    kontrol("model yoksa çıkış 6 ve 'model yok'", r.returncode == 6 and "model yok" in r.stderr, r.stderr[-200:])
    env = {k: v for k, v in os.environ.items() if k not in ("WAYLAND_DISPLAY", "DISPLAY", "YUKI_MASAUSTU_VRM")}
    with tempfile.TemporaryDirectory() as d:
        vrm = Path(d) / "k.vrm"
        vrm.write_bytes(b"glTF")
        r = kos("--model", str(vrm), env=env)
        kontrol("grafik oturumu yoksa çıkış 3 'desteklenmiyor', yığın yok",
                r.returncode == 3 and "desteklenmiyor" in r.stderr and "Traceback" not in r.stderr, r.stderr[-200:])
    kontrol("depoda .vrm yok", not [p for p in DEPO.rglob("*.vrm") if ".git" not in p.parts and "node_modules" not in p.parts])
    kontrol("masaustu/ altında sprite/klip/model varlığı yok",
            not [p for p in KOK.rglob("*") if p.suffix.lower() in {".webp", ".vrma", ".vrm", ".png", ".mp3", ".wav"}
                 and "__pycache__" not in p.parts])


def sunucu() -> None:
    print("— yerel sunucu: model yolu + beyaz liste")
    import yuki_govde
    srv, port = yuki_govde.sunucu_baslat()

    def al(yol: str) -> tuple[int, bytes]:
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
        c.request("GET", yol)
        r = c.getresponse()
        veri = r.read()
        c.close()
        return r.status, veri
    try:
        kontrol("sunucu yalnız 127.0.0.1", srv.server_address[0] == "127.0.0.1")
        kontrol("model verilmediyse 404", al(yuki_govde.MODEL_YOLU)[0] == 404)
        with tempfile.TemporaryDirectory() as d:
            vrm = Path(d) / "k.vrm"
            vrm.write_bytes(b"glTF-deneme")
            srv.model = str(vrm)
            kontrol("kullanıcının VRM'i /_yuki/model.vrm'den gelir", al(yuki_govde.MODEL_YOLU) == (200, b"glTF-deneme"))
            kontrol("model yolu sorgu parametresiyle değişmez", al(yuki_govde.MODEL_YOLU + "?x=/etc/passwd") == (200, b"glTF-deneme"))
            srv.klip_dizini = d
            (Path(d) / "idle.vrma").write_bytes(b"k")
            kontrol("klip dizini verilmişse klip gelir", al(yuki_govde.KLIP_ONEK + "idle.vrma") == (200, b"k"))
            kontrol("klip adında yol kaçışı 404", al(yuki_govde.KLIP_ONEK + "..%2f..%2fk.vrm")[0] == 404
                    and al(yuki_govde.KLIP_ONEK + "k.vrm")[0] == 404)
        kontrol("sayfa sunulur", al("/masaustu/web/yuki-tam.html")[0] == 200)
        kontrol("vendor three + three-vrm sunulur", al("/frontend/vendor/three-0.160.0/three.module.min.js")[0] == 200
                and al("/frontend/vendor/three-vrm-3.1.6/three-vrm.module.min.js")[0] == 200)
        kontrol(".env / backend / kaynak sunulmaz", all(al(y)[0] == 404 for y in
                ("/.env", "/backend/app/config.py", "/masaustu/davranis.py", "/frontend/assets/characters/yuki_avatar.png",
                 "/masaustu/web/../../.git/config")))
    finally:
        srv.shutdown()
    sayfa = (KOK / "web" / "yuki-tam.html").read_text()
    kontrol("sayfa modeli yerel yoldan ister, depodaki .vrm'e bağlı değil", "/_yuki/model.vrm" in sayfa and "yuki3d" not in sayfa)
    kontrol("importmap three-vrm 3.1.6 + animasyon modülü yok (klip isteğe bağlı)",
            "three-vrm-3.1.6" in sayfa and "three-vrm-animation-3.5.5" not in sayfa)


def ortam() -> None:
    print("— GPU / imleç")
    import davranis
    import yuki_govde
    eski = {k: os.environ.get(k) for k in ("YUKI_GPU", "WEBKIT_DISABLE_DMABUF_RENDERER", "WEBKIT_FORCE_COMPOSITING_MODE")}
    try:
        for k in ("WEBKIT_DISABLE_DMABUF_RENDERER", "WEBKIT_FORCE_COMPOSITING_MODE"):
            os.environ.pop(k, None)
        os.environ["YUKI_GPU"] = "software"
        kontrol("software: DMABUF kapalı", yuki_govde.gpu_ortami() == "software" and os.environ["WEBKIT_DISABLE_DMABUF_RENDERER"] == "1")
        os.environ.pop("WEBKIT_DISABLE_DMABUF_RENDERER")
        os.environ["YUKI_GPU"] = "mesa"
        kontrol("mesa: sürücü/aygıt seçimine karışılmaz", yuki_govde.gpu_ortami() == "mesa"
                and "WEBKIT_WEB_RENDER_DEVICE_FILE" not in os.environ and "DRI_PRIME" not in os.environ)
    finally:
        for k, v in eski.items():
            os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
    kontrol("imleç: ekran yoksa None, hata atmaz", davranis.imlec_oku() in (None,) or isinstance(davranis.imlec_oku(), tuple))
    src = (KOK / "yuki_govde.py").read_text() + (KOK / "davranis.py").read_text() + (KOK / "etkilesim.py").read_text()
    kontrol("hyprctl / Hyprland soketi / kişisel yol yok", not any(k in src for k in ("hyprctl", "HYPRLAND", ".socket.sock", "/home/")))


def yuzey_yolu() -> None:
    print("— yüzey seçimi (pencere AÇILMAZ)")
    src = (KOK / "yuki_govde.py").read_text()
    ana = (KOK / "masaustu.py").read_text()
    kontrol("katman yoksa X11: çerçevesiz, üstte, odak almaz, move ile konum",
            all(k in src for k in ("set_keep_above(True)", "set_accept_focus(False)", "self.win.move(")))
    kontrol("yüzey yoksa 'desteklenmiyor' (çıkış 3), GNOME Wayland'de XWayland denenir",
            "wayland_katmansiz" in ana and "CIKIS_DESTEKLENMIYOR" in ana)
    kontrol("tık işareti / fare-klavye-pencere denetimi taşınmadı",
            not any((KOK / n).exists() for n in ("tik_isaret.py", "tik_isaret_ciz.py")) and "xdotool" not in src and "ydotool" not in src)


def main() -> int:
    saf()
    model_ve_cikis()
    try:
        import gi
        gi.require_version("Gtk", "3.0")
        gi.require_version("WebKit2", "4.1")
    except (ImportError, ValueError):
        print("— gi/WebKit2 yok: sunucu/ortam testleri atlandı (/usr/bin/python3 ile koş)")
    else:
        sunucu()
        ortam()
    yuzey_yolu()
    print(f"\n{gecti} geçti · {kaldi} kaldı")
    return 1 if kaldi else 0


if __name__ == "__main__":
    sys.exit(main())
