"""MAP panosu — kademe kapısı + taşıma disiplini + SSRF (Dalga 3 kalanı, 2026-09-18).

Kişisel `api/intel.py`'nin harita bölümünden taşındı (22 uç). Kademe **Pro**.

Bu dosya üç şeyi ölçer:
① Kapı — 22 uç birden router düzeyinde kapalı mı, fail-closed mu
② Taşıma disiplini — ürüne AİT OLMAYAN uçlar gelmedi mi
③ SSRF — iki vekil uç (`cctv/img`, `stream/proxy`) yerel ağa gidebiliyor mu

🔴 ③ neden var: kişiselde tek kontrol `url.startswith("http")` idi. Kişisel
makinede düşük riskli, SATILAN ÜRÜNDE değil — tarayıcıdan gelen adresi SUNUCU
çeker, yani müşterinin modemi/NAS'ı/yazıcısı ve ürünün kendi backend'i
dışarıdan tetiklenebilir hâle gelirdi.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api import map as map_api
from app.main import app

c = TestClient(app)


@pytest.fixture()
def pro():
    yield  # kademe yok — yetki her zaman açık


# ── ① Kapı ───────────────────────────────────────────────────────────────────

def test_router_kapiyi_tasiyor():
    adlar = [d.dependency.__name__ for d in map_api.router.dependencies
             if getattr(d, "dependency", None)]
    assert "require_map" in adlar, "router düzeyi kapı yok — 22 uç kapısız"


def test_her_harita_ucu_kapinin_ALTINDA():
    """Uç sayısını sabit yazmıyoruz: yarın 23. katman eklenirse o da denetime girsin."""
    yollar = {r.path for r in map_api.router.routes}
    assert len(yollar) >= 20, f"beklenenden az uç taşınmış: {len(yollar)}"
    kapili = any(getattr(d, "dependency", None) is map_api.require_map
                 for d in map_api.router.dependencies)
    assert kapili


def test_pro_kapiya_takilmiyor(pro):
    """Pro'da kapı geçilmeli. Dış API'ye giden uçlar başka kod döndürebilir —
    ölçülen şey 403 OLMAMASI."""
    r = c.get("/api/map/config")
    assert r.status_code != 403


def test_urune_ait_olmayan_uclar_TASINMADI():
    """`intel/agents/run` kendi LLM çağrısını yapıyordu (ürünün tek-motor kuralına
    aykırı, BYOK sihirbazını atlar); `intel/brief` arayüzden hiç çağrılmıyordu."""
    yollar = {r.path for r in map_api.router.routes}
    for yasak in ("/api/intel/agents/run", "/api/intel/brief"):
        assert yasak not in yollar, f"{yasak} ürüne sızmış"


def test_olu_kod_kalmadi():
    """Dekoratör silinip gövde bırakılırsa uç gider ama kod kalır — ilk taşıma
    denemesinde tam bu oldu (`agents/run` '1 satır çıkarıldı' demişti)."""
    import inspect
    src = inspect.getsource(map_api)
    for iz in ("run_intel_agent", "_AGENT_PROMPTS"):
        assert iz not in src, f"ölü kod kaldı: {iz}"


def test_harita_disi_yalniz_IKI_VEKIL():
    """`cctv/img` + `stream/proxy` haritanın parçası (map-engine.js ikisini de
    çağırıyor). Bunlar dışında harita-dışı uç kalmamalı."""
    disari = {r.path for r in map_api.router.routes if not r.path.startswith("/api/map")}
    assert disari == {"/api/cctv/img", "/api/stream/proxy"}, f"beklenmeyen: {disari}"


def test_map_resilience_CANLANDI():
    """Bu dosya üründe vardı ama hiçbir yerden çağrılmıyordu (ölü kod)."""
    import inspect
    src = inspect.getsource(map_api)
    assert "map_resilience" in src


# ── ③ SSRF kapısı ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("url", [
    "http://127.0.0.1:8001/api/license",      # ürünün kendi backend'i
    "http://localhost:8001/health",           # ad üzerinden aynısı
    "http://192.168.1.1/",                    # müşterinin modemi
    "http://10.0.0.5/admin",                  # iç ağ
    "http://172.16.0.9/",                     # iç ağ
    "http://169.254.169.254/latest/meta-data/",  # bulut metadata
    "http://[::1]:8001/",                     # IPv6 loopback
    "file:///etc/passwd",                     # şema dışı
    "gopher://x/",                            # şema dışı
    "http://bulunamayan-ad-xyz.invalid/",     # çözümlenemez → fail-closed
    "",                                       # boş
])
def test_ssrf_ozel_adresler_REDDEDILIR(url):
    assert map_api._ozel_adres_mi(url) is True, f"SSRF kapısı geçirdi: {url}"


@pytest.mark.parametrize("url", [
    "http://8.8.8.8/",          # public IP literal — DNS gerekmez
    "https://1.1.1.1/x.jpg",
])
def test_ssrf_dis_adresler_GECER(url):
    """Kapı fazla sıkı olmamalı: gerçek kamera/yayın adresleri geçebilmeli."""
    assert map_api._ozel_adres_mi(url) is False, f"meşru adres engellendi: {url}"


def test_vekil_uclar_kapiyi_KULLANIYOR():
    """Kapının tanımlı olması yetmez — iki uçta da ÇAĞRILMALI.

    🪤 Arama YORUMSUZ kod üzerinde yapılır. İlk yazımda düz metinde arandı ve
    eski kontrolü *anlatan* yorum (`Kişiselde tek kontrol url.startswith…`)
    ihlal sanıldı — bu vault'ta 2026-09-14'te üç kez düşülen tuzağın aynısı.
    `ast.unparse` yorumları düşürür, kodu bırakır.
    """
    import ast
    import inspect
    kod = ast.unparse(ast.parse(inspect.getsource(map_api)))
    # v0.8.1: kapı ortak `_vekil_ac`'ta, yönlendirmenin HER adımında (H4). İki uç onu çağırmalı.
    vekil = ast.unparse(ast.parse(inspect.getsource(map_api._vekil_ac)))
    assert "_ozel_adres_mi(" in vekil and "follow_redirects=False" in vekil, \
        "SSRF kapısı yönlendirme döngüsünün içinde değil"
    assert kod.count("_vekil_ac(") >= 3, \
        "iki vekil uç ortak kapıdan (`_vekil_ac`) geçmiyor (tanım + 2 kullanım beklenir)"
    assert "url.startswith('http')" not in kod and 'url.startswith("http")' not in kod, \
        "zayıf kontrol geride kalmış"
