#!/usr/bin/env python3
"""Masaüstü Yuki takılma/donma düzeltmesi — ekrana çıkmadan.

- davranis.py: KareSayaci · takilma_satiri (yalnız yenisi, örtülü ayıklama, özet) · arayuz_gl_ortami (öncelik)
- yuki_govde.py yerel sunucu: POST /_yuki/durum (anahtar, boyut, JSON) · GET /_yuki/komut olay akışı (anahtar, teslim)
- _js yönlendirmesi: canlıda (kuyruk varken) sonuçsuz komut evaluate_javascript'e GİTMEZ (donmanın kaynağı)
- yapı: canlı yolda saniyelik _bolge_yokla zamanlayıcısı kurulmaz; GDK_GL gi'den önce ayarlanır

Kullanım: python3 tests/test_takilma.py
"""
from __future__ import annotations

import http.client
import inspect
import json
import os
import queue
import sys
import tempfile
import threading
import time
from pathlib import Path
from types import SimpleNamespace

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))
import davranis  # noqa: E402
from davranis import KareSayaci, arayuz_gl_ortami, gorunurde_mi, takilma_esik, takilma_satiri  # noqa: E402

gecti = kaldi = 0


def kontrol(ad: str, kosul: bool, ayrinti: str = "") -> None:
    global gecti, kaldi
    if kosul:
        gecti += 1
        print("  ✓", ad)
    else:
        kaldi += 1
        print("  ✗", ad, ayrinti)


def sayac() -> None:
    print("— host kare sayacı (web/takilma.js ile aynı kural)")
    kontrol("eşik 24 fps 120 · 10 fps 250", (takilma_esik(24), takilma_esik(10)) == (120, 250))
    s = KareSayaci()
    kontrol("42 ms normal", s.ekle(42, 24, 1) is None and s.sayi == 0)
    kontrol("121 ms takılma", s.ekle(121, 24, 2) == "takilma" and s.sayi == 1)
    kontrol("uykuda 200 ms normal", s.ekle(200, 10, 3) is None and s.sayi == 1)
    kontrol("2,5 sn uzun boşluk, takılma değil", s.ekle(2500, 24, 4) == "uzun" and (s.sayi, s.uzun) == (1, 1))
    for i in range(30):
        s.ekle(300, 24, 100 + i)
    kontrol("son 20 tutulur", len(s.son) == 20 and s.son[-1] == [129, 300], str(s.son[-1]))


def satir() -> None:
    print("— log satırı")
    bos = {"kare": 0, "sayi": 0, "uzun": 0, "son": []}
    kontrol("yeni bir şey yok + özet zamanı değil → satır yok",
            takilma_satiri("12:00:00", bos, bos, bos, bos, False) is None)
    kontrol("özet zamanı → [kare] satırı", (takilma_satiri("12:00:00", bos, bos, bos, bos, True) or "").startswith("[kare] 12:00:00"))
    sayfa = {"kare": 50, "sayi": 2, "uzun": 0, "son": [[1000, 150], [5000, 300]], "is_max_ms": 4, "bolge_son_ms": 2,
             "bolge_max_ms": 3}
    once = {"kare": 20, "sayi": 1, "uzun": 0, "son": [[1000, 150]]}
    s = takilma_satiri("12:00:01", sayfa, once, bos, bos, False) or ""
    kontrol("yalnız önceki satırdan sonraki takılma basılır", s.startswith("[takilma]") and "sayfa +1 [300]ms" in s, s)
    kontrol("kare farkı basılır", "kare 30" in s, s)
    # görünürlük süzgeci: takılma başlangıcı 4700; host 4600'de bastı → ekrandaydı
    kontrol("başlangıç öncesi basış → ekranda", gorunurde_mi(5000, 300, [4600]))
    kontrol("basış yok → örtülü", not gorunurde_mi(5000, 300, [1000, 9000]))
    kontrol("örtülü tek başına satır açmaz (örtülü pencere her saniye kısılmış kare üretir, log şişmesin)",
            takilma_satiri("12:00:01", sayfa, once, bos, bos, False, boyalar=[100]) is None)
    s2 = takilma_satiri("12:00:01", sayfa, once, bos, bos, True, boyalar=[100]) or ""
    kontrol("özet satırında örtülü sayılmaz ama yazılır", s2.startswith("[kare]") and "sayfa +0" in s2 and "örtülü 1" in s2, s2)
    host = {"kare": 40, "sayi": 1, "uzun": 0, "son": [[7000, 180]]}
    s3 = takilma_satiri("12:00:02", bos, bos, host, bos, False, ek="gpu mesa") or ""
    kontrol("host basış takılması satır açar", s3.startswith("[takilma]") and "host_boya +1 [180]ms" in s3 and s3.endswith("gpu mesa"), s3)
    s4 = takilma_satiri("12:00:03", {**bos, "uzun": 1}, bos, bos, bos, False) or ""
    kontrol("uzun boşluk satır açar ama takılma sayılmaz", s4.startswith("[kare]") and "uzun_bosluk +1" in s4, s4)


def gl_ayari() -> None:
    print("— arayüz GL ayarı (GTK'den önce)")
    with tempfile.TemporaryDirectory() as d:
        yol = Path(d) / "yuki-masaustu.json"
        env = {}
        kontrol("varsayılan kapalı → GDK_GL=disable", arayuz_gl_ortami(env, yol) == "kapali" and env.get("GDK_GL") == "disable", str(env))
        yol.write_text(json.dumps({"gl": "acik"}))
        env = {}
        kontrol("dosya {gl: acik} → GDK_GL verilmez", arayuz_gl_ortami(env, yol) == "acik" and "GDK_GL" not in env, str(env))
        env = {"YUKI_GL": "kapali"}
        kontrol("env YUKI_GL dosyayı ezer", arayuz_gl_ortami(env, yol) == "kapali" and env.get("GDK_GL") == "disable", str(env))
        yol.write_text("{bozuk")
        env = {}
        kontrol("bozuk dosya → varsayılan kapalı", arayuz_gl_ortami(env, yol) == "kapali" and env.get("GDK_GL") == "disable")
        yol.write_text(json.dumps({"gl": "belki"}))
        env = {"GDK_GL": "gles"}
        kontrol("geçersiz değer → kapalı, elle verilen GDK_GL ezilmez", arayuz_gl_ortami(env, yol) == "kapali" and env["GDK_GL"] == "gles")
    kaynak = (KOK / "masaustu.py").read_text()
    kontrol("masaustu.py GDK_GL'i 'import gi'den ÖNCE ayarlar",
            0 < kaynak.index("arayuz_gl_ortami(os.environ)") < kaynak.index("import gi"))


def sunucu() -> None:
    print("— yerel sunucu: durum POST + komut akışı")
    import yuki_govde
    srv, port = yuki_govde.sunucu_baslat()
    gelen = []
    try:
        def post(govde: bytes, anahtar: str | None, uzunluk: int | None = None) -> int:
            c = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
            h = {"Content-Type": "application/json", "Content-Length": str(len(govde) if uzunluk is None else uzunluk)}
            if anahtar is not None:
                h["X-Yuki-Anahtar"] = anahtar
            c.request("POST", yuki_govde.DURUM_YOLU, body=govde, headers=h)
            r = c.getresponse().status
            c.close()
            return r
        kontrol("teslim bağlı değilken 404", post(b"{}", srv.anahtar) == 404)
        srv.teslim = gelen.append
        kontrol("anahtarsız 403", post(b'{"a":1}', None) == 403 and not gelen)
        kontrol("yanlış anahtar 403", post(b'{"a":1}', "yanlis") == 403 and not gelen)
        kontrol("64 KB üstü 413", post(b"{}", srv.anahtar, uzunluk=yuki_govde.DURUM_AZAMI + 1) == 413 and not gelen)
        kontrol("bozuk JSON 400", post(b"{bozuk", srv.anahtar) == 400 and not gelen)
        kontrol("dizi (sözlük değil) 400", post(b"[1]", srv.anahtar) == 400 and not gelen)
        kontrol("doğru anahtar 204 + teslim", post(b'{"surum": 3}', srv.anahtar) == 204 and gelen == [{"surum": 3}], str(gelen))

        def akis(anahtar: str) -> tuple[int, http.client.HTTPConnection, http.client.HTTPResponse]:
            c = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
            c.request("GET", f"{yuki_govde.KOMUT_YOLU}?anahtar={anahtar}")
            r = c.getresponse()
            return r.status, c, r
        kod, c, _ = akis(srv.anahtar)
        kontrol("kuyruk yokken (kuru kip) akış 403", kod == 403)
        c.close()
        srv.kuyruk = queue.Queue()
        kod, c, _ = akis("yanlis")
        kontrol("akış yanlış anahtar 403", kod == 403)
        c.close()
        srv.kuyruk.put("window.yukiBak(1, 2)")
        kod, c, r = akis(srv.anahtar)
        satir_ = r.fp.readline().decode().strip() if kod == 200 else ""
        kontrol("akış 200 + text/event-stream", kod == 200 and r.getheader("Content-Type") == "text/event-stream")
        kontrol("kuyruktaki komut akışa düşer (JSON dizesi)", satir_ == 'data: "window.yukiBak(1, 2)"', satir_)
        # akış açıkken dosya sunumu sürmeli (ThreadingTCPServer)
        c2 = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
        c2.request("GET", "/masaustu/web/komut.js")
        kontrol("akış açıkken dosya sunulur", c2.getresponse().status == 200)
        c2.close()
        # ikinci abone bağlanınca komut ona gider
        kod2, c3, r3 = akis(srv.anahtar)
        time.sleep(0.2)
        srv.kuyruk.put("ikinci()")
        satir2 = r3.fp.readline().decode().strip() if kod2 == 200 else ""
        kontrol("yeni sayfa bağlanınca komut yeni akışa gider", satir2 == 'data: "ikinci()"', satir2)
        c.close()
        c3.close()
    finally:
        srv.shutdown()
        srv.server_close()


def js_yonu() -> None:
    print("— _js yönlendirmesi")
    import yuki_govde
    cagri = []
    web = SimpleNamespace(evaluate_javascript=lambda *a: cagri.append(a))
    canli = SimpleNamespace(srv=SimpleNamespace(kuyruk=queue.Queue()), web=web)
    yuki_govde.YukiGovde._js(canli, "window.yukiBak(3, 4)")
    kontrol("canlıda sonuçsuz komut kuyruğa, evaluate_javascript'e değil",
            not cagri and canli.srv.kuyruk.get_nowait() == "window.yukiBak(3, 4)", str(cagri))
    kuru = SimpleNamespace(srv=SimpleNamespace(kuyruk=None), web=web)
    yuki_govde.YukiGovde._js(kuru, "x()")
    kontrol("kuru kipte evaluate_javascript, geri çağrısız (sonuç nesnesi yok)",
            len(cagri) == 1 and cagri[0][0] == "x()" and cagri[0][5] is None, str(cagri))
    cagri.clear()
    yuki_govde.YukiGovde._js(canli, "y()", lambda v: None)
    kontrol("sonuç istenirse (yalnız ölçüm) evaluate_javascript + geri çağrı", len(cagri) == 1 and callable(cagri[0][5]))
    tam_init = inspect.getsource(yuki_govde.YukiTamGovde.__init__)
    kontrol("canlı yolda saniyelik _bolge_yokla zamanlayıcısı YOK", "self._bolge_yokla" not in tam_init, tam_init)
    kontrol("canlı yolda durum teslimi bağlı", "srv.teslim" in tam_init)
    sayfa = (KOK / "web" / "yuki-tam.html").read_text()
    kontrol("sayfa durumu yerel sunucuya POST eder", "fetch('/_yuki/durum'" in sayfa and "X-Yuki-Anahtar" in sayfa)
    kontrol("iki sayfa da komut akışını yükler",
            all('<script src="komut.js"></script>' in (KOK / "web" / f).read_text() for f in ("yuki-tam.html",)))


def main() -> int:
    sayac()
    satir()
    gl_ayari()
    sunucu()
    js_yonu()
    print(f"\n{gecti} geçti · {kaldi} kaldı")
    return 1 if kaldi else 0


if __name__ == "__main__":
    sys.exit(main())
