"""Yedek › BULUTTA / AYARLAR / Kontrol et / Kuru çalıştır — rclone arka ucu.

Gerçek rclone ÇAĞRILMAZ, buluta istek gitmez: `YUKI_RCLONE` sahte bir betiğe bakar.
Sahte rclone davranışı `SAHTE_RCLONE_DIZIN` altındaki dosyalardan okunur ve her
çağrıyı `cagrilar.jsonl`'e yazar (argv denetimi için).

    cd backend && python -m pytest -q tests/test_yedek_rclone.py
"""
from __future__ import annotations

import asyncio
import importlib
import json
import os
import stat
import sys
from pathlib import Path

import pytest

SAHTE = r'''#!{py}
import json, os, sys
d = os.environ["SAHTE_RCLONE_DIZIN"]
a = sys.argv[1:]
open(os.path.join(d, "cagrilar.jsonl"), "a").write(json.dumps(a) + "\n")
def oku(ad, v=""):
    p = os.path.join(d, ad)
    return open(p).read() if os.path.exists(p) else v
if a[0] == "version":
    print("rclone v1.68.0-sahte"); sys.exit(0)
if a[0] == "listremotes":
    sys.stdout.write(oku("uzaklar")); sys.exit(0)
if a[0] == "lsjson":
    if oku("lsjson-hata"): sys.stderr.write("ERROR: dizin yok\n"); sys.exit(3)
    sys.stdout.write(oku("lsjson", "[]")); sys.exit(0)
if a[0] == "check":
    for x in a:
        if x.startswith("--missing-on-dst="): open(x.split("=", 1)[1], "w").write(oku("eksik"))
        if x.startswith("--differ="): open(x.split("=", 1)[1], "w").write(oku("fark"))
    sys.exit(1 if (oku("eksik") or oku("fark")) else 0)
if a[0] == "copy":
    for s in oku("kuru").splitlines():
        sys.stderr.write("2026/11/15 12:00:00 NOTICE: %s: Skipped copy as --dry-run is set (size 1k)\n" % s)
    sys.exit(0)
sys.exit(2)
'''


@pytest.fixture
def r(tmp_path, monkeypatch):
    monkeypatch.setenv("YUKI_DATA_DIR", str(tmp_path / "veri"))
    from app.services import yedekleme as y
    y = importlib.reload(y)
    from app.services import rclone_yedek as rmod
    rmod = importlib.reload(rmod)
    sahte_dizin = tmp_path / "sahte"
    sahte_dizin.mkdir()
    betik = tmp_path / "bin" / "rclone"
    betik.parent.mkdir()
    betik.write_text(SAHTE.replace("{py}", sys.executable))
    betik.chmod(betik.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("YUKI_RCLONE", str(betik))
    monkeypatch.setenv("SAHTE_RCLONE_DIZIN", str(sahte_dizin))
    kaynak = tmp_path / "Belgeler"
    kaynak.mkdir()
    (kaynak / "a.txt").write_text("x")
    temel = y.ayarlar()
    temel.update({"yuki_verisi": True})
    y.ayar_yaz(temel)
    y.kaynak_ekle(str(kaynak))
    return {"r": rmod, "y": y, "sahte": sahte_dizin, "kaynak": kaynak, "betik": betik}


def _calistir(coro):
    return asyncio.run(coro)


def _cagrilar(o):
    p = o["sahte"] / "cagrilar.jsonl"
    return [json.loads(s) for s in p.read_text().splitlines()] if p.exists() else []


def _hazirla(o, uzak="bulut"):
    (o["sahte"] / "uzaklar").write_text(f"{uzak}:\n")
    o["r"].ayar_kaydet({"uzak": uzak, "yol": "Yuki Yedek"}, [uzak])


# ── Varsayılanlar: kişisel bilgi yok ─────────────────────────────────────────

def test_varsayilanlar_bos(r):
    a = r["r"].ayar_oku()
    assert a["uzak"] == "" and a["yol"] == "" and a["bant"] == "" and a["haric"] == []


def test_kaynakta_kisisel_ad_yok():
    kaynak = (Path(__file__).resolve().parents[1] / "app" / "services" / "rclone_yedek.py").read_text("utf-8")
    kaynak += (Path(__file__).resolve().parents[1] / "app" / "api" / "yedek_rclone_api.py").read_text("utf-8")
    for yasak in ("gdrive", "Pc " + "ih" + "san", "ih" + "san", "/home/", "rclone-backup", "systemctl"):
        assert yasak not in kaynak, yasak


# ── Durum: kurulu değil / ayarlanmadı (çökme yok) ────────────────────────────

def test_rclone_kurulu_degil(r, monkeypatch):
    monkeypatch.setenv("YUKI_RCLONE", str(r["sahte"] / "olmayan-rclone"))
    d = _calistir(r["r"].durum())
    assert d["kurulu"] is False and d["hazir"] is False and d["neden"] == "kurulu-degil"
    assert _calistir(r["r"].is_baslat("kontrol")) == {"ok": False, "neden": "kurulu-degil"}
    assert _calistir(r["r"].gozat(None))["neden"] == "kurulu-degil"


def test_path_te_de_yoksa_kurulu_degil(r, monkeypatch):
    monkeypatch.delenv("YUKI_RCLONE")
    monkeypatch.setenv("PATH", str(r["sahte"]))
    assert _calistir(r["r"].durum())["neden"] == "kurulu-degil"


def test_uzak_tanimli_degil(r):
    d = _calistir(r["r"].durum())
    assert d["kurulu"] is True and d["neden"] == "uzak-yok" and d["surum"].startswith("rclone v")


def test_uzak_secilmedi_ve_bulunamadi(r):
    (r["sahte"] / "uzaklar").write_text("bulut:\nikinci:\n")
    assert _calistir(r["r"].durum())["neden"] == "uzak-secilmedi"
    r["r"]._ayar_yaz({**r["r"].ayar_oku(), "uzak": "silinmis"})
    assert _calistir(r["r"].durum())["neden"] == "uzak-bulunamadi"
    _hazirla(r)
    d = _calistir(r["r"].durum())
    assert d["hazir"] is True and d["neden"] is None and d["uzaklar"] == ["bulut"]


# ── Ayar doğrulaması (yol gezinmesi, bayrak enjeksiyonu) ─────────────────────

@pytest.mark.parametrize("alan,deger,kod", [
    ("uzak", "-config=/etc/x", "uzak"), ("uzak", "a:b", "uzak"), ("uzak", "yok", "uzak-bulunamadi"),
    ("yol", "../disari", "yol"), ("yol", "a/../../b", "yol"), ("yol", "a:b", "yol"), ("yol", "-x", "yol"),
    ("yol", "a\nb", "yol"), ("bant", "10M; rm", "bant"), ("haric", ["a\nb"], "desen"),
])
def test_ayar_dogrulama(r, alan, deger, kod):
    with pytest.raises(r["r"].AyarHatasi) as e:
        r["r"].ayar_kaydet({alan: deger}, ["bulut"])
    assert e.value.kod == kod
    assert r["r"].ayar_oku()[alan] == r["r"].VARSAYILAN[alan]      # yazılmadı


def test_haric_desen_bitisik_bayrak(r):
    _hazirla(r)
    r["r"].ayar_kaydet({"haric": ["--delete-before", "*.tmp"], "bant": "10M"}, ["bulut"])
    _bekle(r, "kuru")
    argv = [a for a in _cagrilar(r) if a[0] == "copy"][0]
    assert "--delete-before" not in argv and "--exclude=--delete-before" in argv
    assert "--dry-run" in argv and "--bwlimit=10M" in argv
    assert argv[1] == str(r["kaynak"]) and argv[2] == "bulut:Yuki Yedek/Belgeler"


# ── Kontrol et · Kuru çalıştır ───────────────────────────────────────────────

def _bekle(o, ad):
    async def dongu():
        await o["r"].is_baslat(ad) if not o["r"]._ISLER[ad]["calisiyor"] and o["r"]._ISLER[ad]["sonuc"] is None else None
        for _ in range(200):
            if not o["r"]._ISLER[ad]["calisiyor"] and o["r"]._ISLER[ad]["sonuc"] is not None:
                return o["r"].is_durumu(ad)
            await asyncio.sleep(0.02)
        raise AssertionError("iş bitmedi")
    return asyncio.run(dongu())


def test_kontrol_esit(r):
    _hazirla(r)
    s = _bekle(r, "kontrol")["sonuc"]
    assert s["hepsi_esit"] is True and s["eksik"] == 0 and s["denetlenen"] == 1
    yuki = [k for k in s["klasorler"] if k["klasor"] == "Yuki verisi"][0]
    assert yuki["ok"] is False and yuki["neden"] == "yuki-atlandi"
    argv = [a for a in _cagrilar(r) if a[0] == "check"][0]
    assert argv[1:3] == [str(r["kaynak"]), "bulut:Yuki Yedek/Belgeler"]
    assert "--one-way" in argv and "--size-only" in argv


def test_kontrol_eksik_ve_fark_sayilir(r):
    _hazirla(r)
    (r["sahte"] / "eksik").write_text("a.txt\nb/c.txt\n")
    (r["sahte"] / "fark").write_text("d.txt\n")
    s = _bekle(r, "kontrol")["sonuc"]
    b = [k for k in s["klasorler"] if k["klasor"] == "Belgeler"][0]
    assert (s["eksik"], s["fark"], s["hepsi_esit"]) == (2, 1, False)
    assert b["eksik_satir"] == ["a.txt", "b/c.txt"] and b["fark_satir"] == ["d.txt"]


def test_kuru_calistir_sayar_ve_yazmaz(r):
    _hazirla(r)
    (r["sahte"] / "kuru").write_text("yeni1.txt\nalt/yeni2.txt\n")
    s = _bekle(r, "kuru")["sonuc"]
    assert s["gidecek"] == 2
    for argv in _cagrilar(r):
        assert argv[0] in ("version", "listremotes", "copy")
        if argv[0] == "copy":
            assert "--dry-run" in argv


def test_klasor_yoksa_baslamaz(r):
    _hazirla(r)
    for k in list(r["y"].ayarlar()["kaynaklar"]):
        r["y"].kaynak_sil(k["id"])
    assert _calistir(r["r"].is_baslat("kontrol")) == {"ok": False, "neden": "klasor-yok"}


# ── BULUTTA gezgini ──────────────────────────────────────────────────────────

def test_gozat_listeler_ve_yol_gezinmesini_reddeder(r):
    _hazirla(r)
    (r["sahte"] / "lsjson").write_text(json.dumps([
        {"Name": "b.txt", "IsDir": False, "Size": 12, "ModTime": "2026-11-15T10:00:00Z"},
        {"Name": "Alt", "IsDir": True, "Size": -1, "ModTime": "2026-11-14T10:00:00Z"}]))
    d = _calistir(r["r"].gozat("Belgeler"))
    assert d["ok"] and [o["ad"] for o in d["ogeler"]] == ["Alt", "b.txt"]
    assert [a for a in _cagrilar(r) if a[0] == "lsjson"][-1][-1] == "bulut:Yuki Yedek/Belgeler"
    with pytest.raises(r["r"].AyarHatasi):
        _calistir(r["r"].gozat("../../baska"))


def test_gozat_hata_cokmeden_doner(r):
    _hazirla(r)
    (r["sahte"] / "lsjson-hata").write_text("1")
    d = _calistir(r["r"].gozat(None))
    assert d["ok"] is False and d["neden"] == "okunamadi"


# ── API yüzeyi ───────────────────────────────────────────────────────────────

def test_api_kapisi_router_duzeyinde_ve_uclar():
    from app.api import yedek_rclone_api as api
    from app.api.yedekleme import require_yedekleme
    assert require_yedekleme in [d.dependency for d in api.router.dependencies]
    yollar = {(m, r.path) for r in api.router.routes for m in r.methods}
    assert ("GET", "/api/yedekleme/rclone/durum") in yollar
    assert ("POST", "/api/yedekleme/rclone/kontrol") in yollar
    assert ("POST", "/api/yedekleme/rclone/kuru") in yollar
    assert not any(m in ("DELETE", "PUT", "PATCH") for m, _ in yollar)


def test_api_hata_kodu_doner(r):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api import yedek_rclone_api as api
    from app.api.yedekleme import require_yedekleme
    from app.limiter import limiter
    importlib.reload(api)
    app = FastAPI()
    app.state.limiter = limiter
    app.include_router(api.router)
    app.dependency_overrides[require_yedekleme] = lambda: None
    c = TestClient(app)
    assert c.get("/api/yedekleme/rclone/durum").json()["neden"] == "uzak-yok"
    rr = c.post("/api/yedekleme/rclone/ayar", json={"yol": "../x"})
    assert rr.status_code == 400 and rr.json()["detail"] == {"kod": "yol"}
