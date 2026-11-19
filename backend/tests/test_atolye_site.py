"""Yuki Atölye v2 — Faz 1: ilk tür "site" .

Kabul ölçüleri (Atölye v2 planı § 2 Faz 1):
  ⑱ önizleme yalnız 127.0.0.1, yanıtta `CSP: sandbox`, önizleme `aliceToken`'a ulaşamaz
  ⑲ 1440 + 390: `pageerror` 0, yatay taşma 0 → doğrulayıcı bunu ÖLÇER (ve bozuğu yakalar)
  ⑳ bozuk fikstür → doğrulayıcı yakalar, model düzeltir, 2. ölçüm temiz
  (⑰ ㉑ ㉒ ㉓ gerçek modelle ölçülür: reports/…/faz1/luna_kosusu.py — burada sahte LLM)
Ayrıca: yama/bitir araçlarının çalışma alanı kilidi, görsel kontrolün (varsayılan kapalı, açıkken)
ücretli düşüşsüz geçmesi, rehberin dosyadan yüklenmesi, önizleme ucunun dış bağlamda 403.

LLM sahte, atölye kökü pytest'in geçici dizini — gerçek veri dizinine, :8011'e dokunulmaz.
"""
import asyncio
import json
import socket
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.services import gorev as gorev_mod
from app.services.atolye import alan, dogrulayici, onizleme
from app.services.atolye.turler import TURLER, GorevTuru, tur_dogrula
from app.services import gorev as gorev_mod
from app.services.gorev import GorevServisi
from app.services.atolye import baglam as tool_scope
from app.services.atolye.baglam import yerel_baglam
from tests.atolye_yardimci import _arac_akisi, _icerik_akisi
from tests.test_gorev_servisi import SahteLLM

pytestmark = pytest.mark.usefixtures("atolye_acik")   # `ATOLYE` varsayılan kapalı → uçlar 404

SAHTE_TOKEN = "atolye-faz1-test-anahtari"  # ÖRNEK — sahte test anahtarı, gerçek değil

# ══════════════════════════════════════════════════════════════════════════
#  Fikstürler
# ══════════════════════════════════════════════════════════════════════════

TEMIZ_HTML = """<!doctype html><html lang="tr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Luna</title>
<link rel="stylesheet" href="css/stil.css"></head><body><header><img src="logo.svg" alt="Luna"
width="48" height="48"><h1>Luna Kafe</h1></header><main><p>Mahallenin sessiz köşesinde taze
kahve ve ev yapımı kurabiye. Hafta içi her gün açığız.</p></main></body></html>"""
TEMIZ_CSS = "body{font:17px/1.6 system-ui,sans-serif;margin:0;padding:16px;max-width:68ch}"
TEMIZ_SVG = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48" width="48" '
             'height="48"><circle cx="24" cy="24" r="20" fill="#3a5"/></svg>')

# Bilerek bozuk: viewport yok, CDN script + Google Fonts, kırık css bağlantısı, 1200 px kutu
# (390'da taşar), çalışma anı JS hatası, betikli/viewBox'sız SVG.
BOZUK_HTML = """<!doctype html><html><head><meta charset="utf-8"><title>Luna</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter">
<link rel="stylesheet" href="css/yok.css">
<script src="https://cdn.example.com/lib.js"></script></head><body>
<div class="genis" style="width:1200px">Luna Kafe — mahallenin sessiz köşesi, taze kahve.</div>
<img src="logo.svg"><script>tanimsizFonksiyon();</script></body></html>"""
BOZUK_SVG = '<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'


def _alan_kur(kok: Path, dosyalar: dict[str, str], tur="site", ad="luna") -> Path:
    a = kok / tur / ad
    (a / alan.AYRILMIS).mkdir(parents=True, exist_ok=True)
    for rel, icerik in dosyalar.items():
        (a / rel).parent.mkdir(parents=True, exist_ok=True)
        (a / rel).write_text(icerik, encoding="utf-8")
    return a


def _temiz(kok, ad="luna"):
    return _alan_kur(kok, {"index.html": TEMIZ_HTML, "css/stil.css": TEMIZ_CSS,
                           "logo.svg": TEMIZ_SVG}, ad=ad)


@pytest.fixture
def kok(tmp_path):
    return tmp_path / "atolye"


# ══════════════════════════════════════════════════════════════════════════
#  Araçlar: yama + bitir (çalışma alanı kilidi aynen)
# ══════════════════════════════════════════════════════════════════════════

def test_alan_yama_tek_gecen_metni_degistirir(kok):
    a = _alan_kur(kok, {"index.html": "<h1>Eski</h1><p>x</p>"})
    assert alan.alan_yama(a, "index.html", "Eski", "Yeni").startswith("yamalandı: index.html")
    assert (a / "index.html").read_text() == "<h1>Yeni</h1><p>x</p>"


@pytest.mark.parametrize("eski,beklenen", [("yok-boyle", "bulunamadı"), ("x", "2 kez"),
                                           ("", "boş olamaz")])
def test_alan_yama_belirsiz_ya_da_bos_eskiyi_reddeder(kok, eski, beklenen):
    a = _alan_kur(kok, {"a.txt": "x y x"})
    sonuc = alan.alan_yama(a, "a.txt", eski, "z")
    assert sonuc.startswith("Hata:") and beklenen in sonuc
    assert (a / "a.txt").read_text() == "x y x"


@pytest.mark.parametrize("yol", ["../disari.txt", "/etc/passwd", "~/.ssh/config",
                                 ".gorev/durum.json", "bag/a.txt"])
def test_alan_yama_alan_disina_cikamaz(kok, tmp_path, yol):
    a = _alan_kur(kok, {"a.txt": "x"})
    (kok / "site" / "disari.txt").write_text("x")
    (a / alan.AYRILMIS / "durum.json").write_text("x")
    disari = tmp_path / "disari"
    disari.mkdir()
    (disari / "a.txt").write_text("x")
    (a / "bag").symlink_to(disari)
    assert alan.alan_yama(a, yol, "x", "SIZDI").startswith("Hata:")
    assert (kok / "site" / "disari.txt").read_text() == "x"
    assert (a / alan.AYRILMIS / "durum.json").read_text() == "x"
    assert (disari / "a.txt").read_text() == "x"


def test_tur_araclari_kapi_kumesiyle_esit_ve_sohbet_semasinda_yok():
    """⑫'nin Faz 1 hâli: tür araçları genel dispatcher'a girmez."""
    from app.services.tools import TOOLS
    assert {"alan_yama", "alan_bitir"} <= set(alan.ARACLAR)
    assert not {t["function"]["name"] for t in TOOLS} & set(alan.ARACLAR)
    assert set(TURLER["site"].araclar) == {"alan_agac", "alan_oku", "alan_yaz", "alan_yama", "alan_bitir"}
    assert set(alan.SEMALAR) == set(alan.ARACLAR)


def test_dogrulayicili_tur_bitir_aracsiz_kaydedilemez():
    with pytest.raises(ValueError, match="alan_bitir"):
        tur_dogrula(GorevTuru(ad="x", aciklama="x", araclar=("alan_yaz",), dogrulayici=True))


def test_site_rehberi_dosyadan_gelir(kok):
    yol = Path(gorev_mod.__file__).parent / "atolye_rehber.md"
    metin = yol.read_text(encoding="utf-8").strip()
    assert TURLER["site"].rehber == metin
    for kural in ("alan_bitir", "viewport", "Ağ yok", "390", "localStorage"):
        assert kural in metin


# ══════════════════════════════════════════════════════════════════════════
#  Doğrulayıcı — statik
# ══════════════════════════════════════════════════════════════════════════

def test_statik_temiz_site_hatasiz(kok):
    hatalar, _ = dogrulayici.statik(_temiz(kok))
    assert hatalar == []


def test_statik_bozuk_siteyi_madde_madde_yakalar(kok):
    a = _alan_kur(kok, {"index.html": BOZUK_HTML, "logo.svg": BOZUK_SVG,
                        "css/s.css": "@import url(https://x.example/a.css); "
                                     "body{background:url(yok.png)}"})
    metin = "\n".join(dogrulayici.statik(a)[0])
    for beklenen in ("viewport", "fonts.googleapis.com", "cdn.example.com", "css/yok.css",
                     "SVG içinde <script>", "viewBox", "x.example/a.css", "yok.png"):
        assert beklenen in metin, f"yakalanmadı: {beklenen}\n{metin}"


def test_statik_index_yoksa_tek_hata(kok):
    a = _alan_kur(kok, {"a.html": TEMIZ_HTML})
    assert dogrulayici.statik(a)[0] == [
        "index.html yok — site ana dosyası çalışma alanının kökünde olmalı"]


def test_statik_bozuk_svg_xml(kok):
    a = _temiz(kok)
    (a / "logo.svg").write_text("<svg viewBox='0 0 1 1'><g></svg>")
    assert any("bozuk XML" in h for h in dogrulayici.statik(a)[0])


def test_statik_dis_sayfa_baglantisi_serbest(kok):
    a = _temiz(kok)
    (a / "index.html").write_text(TEMIZ_HTML.replace(
        "</main>", '<a href="https://example.com">dış bağlantı</a></main>'))
    assert dogrulayici.statik(a)[0] == []


# ══════════════════════════════════════════════════════════════════════════
#  Doğrulayıcı — ekran (Playwright, gerçek Chromium) — ⑲
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.usefixtures("tarayici_gerekli")
def test_ekran_temiz_site_1440_ve_390_pageerror_0_tasma_0(kok):
    a = _temiz(kok)
    s = dogrulayici.dogrula(a)
    assert s["temiz"], s["hatalar"]
    for gen in ("1440px", "390px"):
        o = s["olcum"][gen]
        assert o["pageerror"] == 0 and o["dis_istek"] == 0 and o["kirik_istek"] == 0
        assert o["scrollWidth"] == o["genislik"] == int(gen[:-2])
    assert (a / ".gorev/ekran/1440.png").stat().st_size > 1000
    assert (a / ".gorev/ekran/390.png").stat().st_size > 1000
    kayit = json.loads((a / ".gorev/dogrulama.json").read_text())
    assert kayit["temiz"] and kayit["parmak_izi"] == dogrulayici.parmak_izi(a)


@pytest.mark.usefixtures("tarayici_gerekli")
def test_ekran_bozuk_siteyi_yakalar_js_hatasi_tasma_kirik_istek(kok):
    a = _alan_kur(kok, {"index.html": BOZUK_HTML, "logo.svg": TEMIZ_SVG})
    s = dogrulayici.dogrula(a)
    assert not s["temiz"]
    m = "\n".join(s["hatalar"])
    assert "390px: JS hatası" in m and "tanimsizFonksiyon" in m
    assert "390px: yatay taşma" in m and "div.genis" in m
    assert "1440px: yatay taşma" not in m                      # 1200 px 1440'a sığar
    assert s["olcum"]["390px"]["kirik_istek"] >= 1              # css/yok.css 404


class _DisSunucu(BaseHTTPRequestHandler):
    vurus = 0

    def log_message(self, *a):
        pass

    def do_GET(self):
        type(self).vurus += 1
        self.send_response(204)
        self.end_headers()


@pytest.mark.usefixtures("tarayici_gerekli")
def test_ekran_dis_istek_engellenir_ve_sayilir(kok):
    """CSP'nin yakalamadığı yol için de ağ kapalı: route iptal eder, istek hedefe HİÇ varmaz."""
    _DisSunucu.vurus = 0
    dis = ThreadingHTTPServer(("127.0.0.1", 0), _DisSunucu)       # başka port = başka köken
    threading.Thread(target=dis.serve_forever, daemon=True).start()
    a = _temiz(kok)
    (a / "index.html").write_text(TEMIZ_HTML.replace(
        "</main>", f'<img src="http://127.0.0.1:{dis.server_address[1]}/x.png" alt=""></main>'))
    try:
        with patch.object(onizleme, "CSP", "sandbox allow-scripts"):
            s = dogrulayici.dogrula(a)
    finally:
        dis.shutdown()
    assert _DisSunucu.vurus == 0, "dış istek hedefe ulaştı"
    assert s["olcum"]["1440px"]["dis_istek"] == 1 and s["olcum"]["390px"]["dis_istek"] == 1
    assert any("dış istek" in h for h in s["hatalar"])


def test_son_sonuc_parmak_izi_degisince_bayatlar(kok):
    a = _temiz(kok)
    dogrulayici.dogrula(a)
    assert dogrulayici.son_sonuc(a)["temiz"] is True
    (a / "index.html").write_text(TEMIZ_HTML + " ")
    assert dogrulayici.son_sonuc(a) is None


def test_alan_bitir_raporu_modele_doner(kok):
    a = _alan_kur(kok, {"index.html": BOZUK_HTML, "logo.svg": TEMIZ_SVG})
    r = alan.alan_bitir(a)
    assert r.startswith("DOĞRULAMA KİRLİ") and "yeniden alan_bitir" in r
    _temiz(kok)
    assert alan.alan_bitir(a).startswith("DOĞRULAMA TEMİZ")


def test_alan_bitir_dogrulayici_coker_ise_temiz_demez(kok):
    a = _temiz(kok)
    with patch.object(dogrulayici, "dogrula", side_effect=RuntimeError("tarayıcı yok")):
        r = alan.alan_bitir(a)
    assert r.startswith("Hata: doğrulama koşamadı") and "TEMİZ" not in r


# ══════════════════════════════════════════════════════════════════════════
#  Önizleme — ⑱
# ══════════════════════════════════════════════════════════════════════════

def _get(url, host=None, method="GET"):
    req = urllib.request.Request(url, method=method, headers={"Host": host} if host else {})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()


def test_onizleme_yalniz_loopback_ve_csp_sandbox(kok):
    _temiz(kok)
    with onizleme.OnizlemeSunucusu(kok, 0) as srv:
        assert srv._srv.server_address[0] == "127.0.0.1"
        kod, bas, govde = _get(srv.url("site", "luna"))
        assert kod == 200 and "Luna Kafe".encode() in govde
        csp = bas["Content-Security-Policy"]
        assert csp.startswith("sandbox allow-scripts;") and "allow-same-origin" not in csp
        assert "connect-src 'none'" in csp and "default-src 'none'" in csp
        assert bas["X-Content-Type-Options"] == "nosniff"
        # 404'te de CSP var (hata sayfası da sandbox'ta)
        assert "sandbox" in _get(srv.url("site", "luna") + "yok.html")[1]["Content-Security-Policy"]


def test_onizleme_loopback_disindan_erisilemez(kok):
    """Makinenin loopback dışı bir adresi varsa ona bağlanma reddedilir."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
        s.close()
    except OSError:
        pytest.skip("loopback dışı adres yok")
    if ip.startswith("127."):
        pytest.skip("loopback dışı adres yok")
    _temiz(kok)
    with onizleme.OnizlemeSunucusu(kok, 0) as srv:
        with pytest.raises(OSError):
            socket.create_connection((ip, srv.port), timeout=2).close()


@pytest.mark.parametrize("yol,beklenen", [
    ("site/luna/.gorev/durum.json", 404), ("site/luna/../../etc/passwd", 404),
    ("site/luna/%2e%2e/%2e%2e/x", 404), ("site/luna/bag/sir.txt", 404),
    ("site/luna/gizli.py", 404), ("site/LUNA/index.html", 404), ("site", 404),
    ("site/luna/css/stil.css", 200), ("site/luna/logo.svg", 200),
])
def test_onizleme_yol_kilidi(kok, tmp_path, yol, beklenen):
    a = _temiz(kok)
    (a / alan.AYRILMIS / "durum.json").write_text("{}")
    (a / "gizli.py").write_text("x")
    disari = tmp_path / "disari"
    disari.mkdir()
    (disari / "sir.txt").write_text("SIR")
    (a / "bag").symlink_to(disari)
    with onizleme.OnizlemeSunucusu(kok, 0) as srv:
        kod, _, govde = _get(f"http://127.0.0.1:{srv.port}/{yol}")
    assert kod == beklenen, (yol, kod)
    assert b"SIR" not in govde


def test_onizleme_yabanci_host_403_ve_yalniz_get(kok):
    _temiz(kok)
    with onizleme.OnizlemeSunucusu(kok, 0) as srv:
        url = srv.url("site", "luna")
        assert _get(url, host=f"kotu.example:{srv.port}")[0] == 403          # DNS rebinding
        assert _get(url, host=f"localhost:{srv.port}")[0] == 200
        assert _get(url, method="POST")[0] == 405
        assert _get(url, method="HEAD")[0] == 200


class _UygulamaSahte(BaseHTTPRequestHandler):
    """Yuki'nin kökenini taklit eder: sayfası localStorage'a aliceToken yazar; /api sır döner."""
    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path.startswith("/api"):
            govde = b'{"sir":"TOKEN-ULASTI"}'
            self.send_response(200)
            self.send_header("Access-Control-Allow-Origin", "*")
        else:
            govde = b"<script>localStorage.setItem('aliceToken','GIZLI-TOKEN-123')</script>ok"
            self.send_response(200)
            self.send_header("Set-Cookie", "alice=GIZLI-CEREZ; Path=/")
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(govde)))
        self.end_headers()
        self.wfile.write(govde)


@pytest.mark.usefixtures("tarayici_gerekli")
def test_onizleme_aliceTokena_ulasamaz(kok):
    """⑱ Saldırgan site: aynı tarayıcıda Yuki kökeni token'ı yazmışken önizleme sayfası
    localStorage/çerez/fetch ile token'ı okumayı dener → hepsi engelli."""
    from playwright.sync_api import sync_playwright
    uyg = ThreadingHTTPServer(("127.0.0.1", 0), _UygulamaSahte)
    threading.Thread(target=uyg.serve_forever, daemon=True).start()
    up = uyg.server_address[1]
    saldiri = f"""<!doctype html><html lang="tr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width"><title>x</title></head><body>
<p>saldiri sayfasi metni yeterince uzun olsun diye</p><script>
const r = {{}};
try {{ r.ls = localStorage.getItem('aliceToken'); }} catch (e) {{ r.ls = 'HATA:' + e.name; }}
try {{ r.cerez = document.cookie; }} catch (e) {{ r.cerez = 'HATA:' + e.name; }}
r.origin = self.origin;
fetch('http://127.0.0.1:{up}/api/x', {{credentials: 'include'}}).then(x => x.text())
  .then(t => {{ r.fetch = t; }}).catch(e => {{ r.fetch = 'HATA'; }})
  .finally(() => {{ document.title = 'BITTI:' + JSON.stringify(r); }});
</script></body></html>"""
    _alan_kur(kok, {"index.html": saldiri})
    try:
        with onizleme.OnizlemeSunucusu(kok, 0) as srv, sync_playwright() as p:
            b = p.chromium.launch()
            sayfa = b.new_context().new_page()
            sayfa.goto(f"http://127.0.0.1:{up}/")                   # Yuki kökeni token'ı yazar
            assert sayfa.evaluate("localStorage.getItem('aliceToken')") == "GIZLI-TOKEN-123"
            sayfa.goto(srv.url("site", "luna"))
            sayfa.wait_for_function("document.title.startsWith('BITTI:')", timeout=5000)
            r = json.loads(sayfa.title()[len("BITTI:"):])
            b.close()
    finally:
        uyg.shutdown()
    assert r["ls"] == "HATA:SecurityError"
    assert r["cerez"] == "HATA:SecurityError"
    assert r["origin"] == "null"                                     # opak köken
    assert r["fetch"] == "HATA"                                      # connect-src 'none'
    assert "GIZLI" not in json.dumps(r) and "TOKEN-ULASTI" not in json.dumps(r)


def test_paylasilan_onizleme_portu_envden(kok, monkeypatch):
    monkeypatch.setenv("YUKI_ATOLYE_ONIZLEME_PORT", "0")
    monkeypatch.setattr(onizleme, "_paylasilan", None)
    _temiz(kok)
    srv = onizleme.paylasilan(kok)
    try:
        assert onizleme.paylasilan(kok) is srv                       # süreç başına tek
        assert _get(srv.url("site", "luna"))[0] == 200
    finally:
        srv.kapat()
        monkeypatch.setattr(onizleme, "_paylasilan", None)
    assert onizleme.VARSAYILAN_PORT == 8011


# ══════════════════════════════════════════════════════════════════════════
#  Görev servisi — bitiş doğrulaması döngüsü (⑳, sahte LLM)
# ══════════════════════════════════════════════════════════════════════════

def _cagri(i, ad, args):
    return _arac_akisi([(f"c{i}", ad, args)])


def _gorsel_cevap(ciddi=(), token=600):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(
            content=json.dumps({"ciddi": list(ciddi), "kucuk": []})))],
        usage=SimpleNamespace(total_tokens=token))


async def _kos(servis, llm, istek="Luna için site", ad="luna", zaman=60, router=None):
    with patch("app.services.llm_router.get_router", return_value=router or llm.router()), \
            yerel_baglam():
        await servis.baslat("site", ad, istek)
        return await servis.bekle(f"site/{ad}", zaman)


def _gorsel_cagrilari(llm):
    return [c for c in llm.client.chat.completions.create.await_args_list
            if c.kwargs.get("stream") is False]


def _arac_sonuclari(mesajlar):
    return [m["content"] for m in mesajlar if m.get("role") == "tool"]


@pytest.mark.asyncio
@pytest.mark.usefixtures("tarayici_gerekli")
async def test_bozuk_fikstur_bitir_yakalar_model_duzeltir_ikinci_olcum_temiz(kok):
    """⑳: model bozuk site yazar → alan_bitir KİRLİ → model düzeltir → alan_bitir TEMİZ →
    servis aynı içeriği yeniden ölçmez (parmak izi) → görsel kontrol temiz → bitti."""
    llm = SahteLLM([
        _cagri(0, "alan_yaz", {"yol": "index.html", "icerik": BOZUK_HTML}),
        _cagri(1, "alan_yaz", {"yol": "logo.svg", "icerik": BOZUK_SVG}),
        _cagri(2, "alan_bitir", {"ozet": "ilk sürüm"}),
        _cagri(3, "alan_yaz", {"yol": "index.html", "icerik": TEMIZ_HTML}),
        _cagri(4, "alan_yaz", {"yol": "css/stil.css", "icerik": TEMIZ_CSS}),
        _cagri(5, "alan_yama", {"yol": "logo.svg", "eski": BOZUK_SVG, "yeni": TEMIZ_SVG}),
        _cagri(6, "alan_bitir", {}),
        _icerik_akisi("Luna sitesi hazır."),
        _gorsel_cevap(),
    ])
    servis = GorevServisi(kok)
    with patch.object(dogrulayici, "dogrula", wraps=dogrulayici.dogrula) as casus:
        d = await _kos(servis, llm)
    assert (d["durum"], d["neden"]) == ("bitti", None), d
    ilk = _arac_sonuclari(llm.cagrilar[3])[-1]                # 1. alan_bitir → modele KİRLİ
    assert ilk.startswith("DOĞRULAMA KİRLİ")
    assert "viewport" in ilk and "390px: yatay taşma" in ilk and "SVG içinde <script>" in ilk
    assert _arac_sonuclari(llm.cagrilar[7])[-1].startswith("DOĞRULAMA TEMİZ")   # 2. ölçüm
    assert casus.call_count == 2                     # servis yeniden ölçmedi (parmak izi aynı)
    assert len(d["dogrulama"]) == 1 and d["dogrulama"][0]["temiz"] is True
    assert d["dogrulama"][0]["gorsel"]["durum"] == "temiz"
    assert gorev_mod.ozet(d)["dogrulama"] == {"temiz": True, "hata": 0, "gorsel": "temiz", "tur": 1}
    assert d["adim"] == 8 and d["token"] >= 600       # görsel token'ı göreve sayıldı


@pytest.mark.asyncio
async def test_model_bitirmeden_biterse_servis_olcer_geri_bildirim_verir(kok):
    """Model alan_bitir çağırmadan "bitti" der → servis ölçer → KİRLİ → geri bildirim
    mesajı → model düzeltir → 2. ölçüm temiz → bitti."""
    llm = SahteLLM([
        _cagri(0, "alan_yaz", {"yol": "index.html", "icerik": BOZUK_HTML}),
        _icerik_akisi("bitti sanırım"),
        _cagri(1, "alan_yaz", {"yol": "index.html", "icerik": TEMIZ_HTML}),
        _cagri(2, "alan_yaz", {"yol": "css/stil.css", "icerik": TEMIZ_CSS}),
        _cagri(3, "alan_yaz", {"yol": "logo.svg", "icerik": TEMIZ_SVG}),
        _icerik_akisi("şimdi tamam"),
        _gorsel_cevap(),
    ])
    d = await _kos(GorevServisi(kok), llm)
    assert d["durum"] == "bitti", d
    assert [r["temiz"] for r in d["dogrulama"]] == [False, True]
    geri = llm.cagrilar[2][-1]
    assert geri["role"] == "user"
    assert geri["content"].startswith("Bitiş doğrulaması KİRLİ (düzeltme turu 1/2)")
    assert "viewport" in geri["content"]
    assert llm.cagrilar[2][-2] == {"role": "assistant", "content": "bitti sanırım "}
    assert d["ozet"].strip() == "şimdi tamam"
    olaylar = [json.loads(s) for s in
               (kok / "site/luna/.gorev/olaylar.jsonl").read_text().splitlines()]
    assert [o["temiz"] for o in olaylar if o["olay"] == "dogrulama"] == [False, True]


@pytest.mark.asyncio
async def test_duzeltmeyen_model_tavanda_yarim_dogrulama(kok):
    llm = SahteLLM([_cagri(0, "alan_yaz", {"yol": "index.html", "icerik": BOZUK_HTML})]
                   + [_icerik_akisi("bitti") for _ in range(gorev_mod.DUZELTME_TAVANI + 1)])
    d = await _kos(GorevServisi(kok), llm)
    assert (d["durum"], d["neden"]) == ("yarim", "dogrulama")
    assert len(d["dogrulama"]) == gorev_mod.DUZELTME_TAVANI + 1
    assert not _gorsel_cagrilari(llm)                 # sayısal kirliyken görüntü gönderilmez
    assert "yarim" in gorev_mod.DEVAM_EDILEBILIR      # kullanıcı DEVAM ile sürdürebilir


@pytest.mark.asyncio
@pytest.mark.usefixtures("tarayici_gerekli")
async def test_gorsel_ciddi_kusur_geri_bildirime_doner(kok):
    llm = SahteLLM([
        _cagri(0, "alan_yaz", {"yol": "index.html", "icerik": TEMIZ_HTML}),
        _cagri(1, "alan_yaz", {"yol": "css/stil.css", "icerik": TEMIZ_CSS}),
        _cagri(2, "alan_yaz", {"yol": "logo.svg", "icerik": TEMIZ_SVG}),
        _icerik_akisi("hazır"),
        _gorsel_cevap(["390 px'te başlık logonun üstüne biniyor"], token=100_000),
        _cagri(3, "alan_yama", {"yol": "css/stil.css", "eski": "padding:16px",
                                "yeni": "padding:24px"}),
        _icerik_akisi("düzelttim"),
        _gorsel_cevap([], token=200_000),
    ])
    d = await _kos(GorevServisi(kok), llm)
    assert d["durum"] == "bitti", d
    assert [r["gorsel"]["durum"] for r in d["dogrulama"]] == ["kusurlu", "temiz"]
    geri = llm.cagrilar[5][-1]["content"]
    assert "görsel: 390 px'te başlık logonun üstüne biniyor" in geri
    g = _gorsel_cagrilari(llm)
    assert len(g) == 2
    icerik = g[0].kwargs["messages"][1]["content"]
    assert [p["type"] for p in icerik] == ["text", "image_url", "image_url"]
    assert icerik[1]["image_url"]["url"].startswith("data:image/png;base64,")
    assert d["token"] >= 300_000                      # iki görsel çağrının token'ı göreve sayıldı
    assert [r["gorsel"]["token"] for r in d["dogrulama"]] == [100_000, 200_000]


@pytest.mark.asyncio
@pytest.mark.usefixtures("tarayici_gerekli")
async def test_gorsel_kontrol_hata_hukmu_bozmaz(kok):
    """Görsel çağrı hata verirse görsel `yapilamadi`, görev yine biter."""
    llm = SahteLLM([
        _cagri(0, "alan_yaz", {"yol": "index.html", "icerik": TEMIZ_HTML}),
        _cagri(1, "alan_yaz", {"yol": "css/stil.css", "icerik": TEMIZ_CSS}),
        _cagri(2, "alan_yaz", {"yol": "logo.svg", "icerik": TEMIZ_SVG}),
        _icerik_akisi("hazır"),
    ])
    asil = llm._create

    async def _create(**kw):
        if kw.get("stream") is False:
            raise RuntimeError("sağlayıcı yanıt vermedi")
        return await asil(**kw)
    llm.client.chat.completions.create.side_effect = _create
    d = await _kos(GorevServisi(kok), llm)
    assert d["durum"] == "bitti"
    assert d["dogrulama"][-1]["gorsel"] == {"durum": "yapilamadi", "neden": "RuntimeError",
                                            "ciddi": [], "kucuk": [], "token": 0}


def test_gorsel_kontrol_varsayilan_kapali(monkeypatch):
    """Görüntü kabulü her sağlayıcıda ölçülmediği için ayarsız kurulumda kapalı."""
    monkeypatch.delenv("YUKI_ATOLYE_GORSEL", raising=False)
    assert gorev_mod._gorsel_acik() is False
    monkeypatch.setenv("YUKI_ATOLYE_GORSEL", "1")
    assert gorev_mod._gorsel_acik() is True


@pytest.fixture(autouse=True)
def _gorsel_acik(monkeypatch):
    """Bu dosyadaki ölçümler görsel kontrol AÇIKKEN yapılır (varsayılan kapalı)."""
    monkeypatch.setattr(gorev_mod, "GORSEL_KONTROL", True)


@pytest.mark.asyncio
async def test_deneme_turu_dogrulamasiz_kalir(kok):
    llm = SahteLLM([_cagri(0, "alan_yaz", {"yol": "a.txt", "icerik": "x"}), _icerik_akisi("ok")])
    with patch("app.services.llm_router.get_router", return_value=llm.router()), yerel_baglam():
        servis = GorevServisi(kok)
        await servis.baslat("deneme", "bir", "yap")
        d = await servis.bekle("deneme/bir", 10)
    assert d["durum"] == "bitti" and "dogrulama" not in d
    assert len(llm.cagrilar) == 2


@pytest.mark.asyncio
async def test_durdur_dogrulama_turunda_da_iki_saniye(kok):
    """Doğrulama (Playwright) koşarken DURDUR → görev ≤2 sn'de durdu, geri bildirim turu yok."""
    llm = SahteLLM([_cagri(0, "alan_yaz", {"yol": "index.html", "icerik": BOZUK_HTML}),
                    _icerik_akisi("bitti")])
    servis = GorevServisi(kok)
    yavas = threading.Event()

    def _yavas_dogrula(k, ekran_kaydet=True):
        yavas.set()
        time.sleep(4)
        return {"temiz": False, "hatalar": ["x"], "uyarilar": [], "olcum": {}, "sure_sn": 4}
    with patch("app.services.llm_router.get_router", return_value=llm.router()), \
            patch.object(dogrulayici, "dogrula", _yavas_dogrula), yerel_baglam():
        await servis.baslat("site", "luna", "yap")
        while not yavas.is_set():
            await asyncio.sleep(0.02)
        t0 = time.monotonic()
        d = await servis.durdur("site/luna")
        sure = time.monotonic() - t0
    assert sure <= 2.0, sure
    assert d["durum"] == "durdu"
    assert len(llm.cagrilar) == 2


@pytest.mark.asyncio
async def test_dis_site_gorevi_yeni_araclari_kullanir_genel_arac_yine_kapali(kok):
    """Telefondan açılmış site görevi: yama/bitir (tür araçları) çalışır; genel araç reddi
    sürer (0d kapısı gevşemedi)."""
    servis = GorevServisi(kok)
    t = servis.turler["site"]
    a = _temiz(kok)
    sonuc = await servis._arac(t, a, "alan_yama", {"yol": "index.html", "eski": "Luna Kafe",
                                                   "yeni": "Luna Kahve"}, dis=True)
    assert sonuc.startswith("yamalandı")
    for ad in ("komut_calistir", "write_file", "read_file", "open_panel", "mcp__fs__write_file"):
        r = await servis._arac(t, a, ad, {}, dis=True)
        assert r.startswith("Hata:"), ad


# ══════════════════════════════════════════════════════════════════════════
#  API — önizleme ucu
# ══════════════════════════════════════════════════════════════════════════

def test_onizleme_ucu_dista_403_yerelde_adres(kok, monkeypatch):
    from starlette.testclient import TestClient
    from app import main as main_mod
    yetki = {"Authorization": f"Bearer {SAHTE_TOKEN}"}
    servis = GorevServisi(kok)
    _temiz(kok)
    (kok / "site/luna/.gorev/durum.json").write_text(json.dumps(
        {"id": "site/luna", "tur": "site", "ad": "luna", "durum": "bitti", "kaynak": "yerel",
         "tavanlar": {}, "dogrulama": [{"temiz": True, "hatalar": []}]}))
    monkeypatch.setenv("YUKI_ATOLYE_ONIZLEME_PORT", "0")
    monkeypatch.setattr(onizleme, "_paylasilan", None)
    with patch.object(gorev_mod, "_servis", servis), \
            patch.object(main_mod, "AUTH_TOKEN", SAHTE_TOKEN):
        c = TestClient(main_mod.app, base_url="http://localhost:8001", client=("127.0.0.1", 50000))
        dis = c.get("/api/gorev/site/luna/onizleme",
                    headers={**yetki, "X-Forwarded-For": "100.64.0.7"})
        assert dis.status_code == 403
        assert onizleme._paylasilan is None              # dış istek sunucuyu açmadı bile
        assert c.get("/api/gorev/site/luna/onizleme").status_code == 401
        assert c.get("/api/gorev/site/yok/onizleme", headers=yetki).status_code == 404
        r = c.get("/api/gorev/site/luna/onizleme", headers=yetki)
        assert r.status_code == 200, r.text
        g = r.json()
        try:
            assert g["url"].startswith("http://127.0.0.1:") and g["url"].endswith("/site/luna/")
            assert g["dogrulama"]["temiz"] is True
            assert _get(g["url"])[0] == 200
        finally:
            onizleme._paylasilan.kapat()
            monkeypatch.setattr(onizleme, "_paylasilan", None)
