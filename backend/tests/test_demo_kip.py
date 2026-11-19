"""Demo veri kipi (YUKI_DEMO=1) — kişisel yol okunmaz, örnek veri görünür.

Her senaryo AYRI bir Python sürecinde koşar: `demo_kip.kur()` `app` paketinin ilk
import'unda ortamı (HOME, YUKI_DATA_DIR…) değiştirir; pytest sürecini kirletmesin.

"Gerçek ev" burada sahte bir klasördür (tmp_path/gercek-ev): içine adı bilinen
dosyalar (belge, fotoğraf, Claude oturumu) konur, sonra demo kipindeki HER yanıtta
bu adların ve gerçek ev yolunun geçmediği ölçülür.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
GIZLI_BELGE = "GIZLI-BELGE-q7x2.txt"
GIZLI_FOTO = "gizli-foto-q7x2.png"
GIZLI_PROJE = "gizli-proje-q7x2"
GIZLI_IZ = "q7x2"          # üç adın ortak parçası — yanıtta hiç geçmemeli

KOSUM = textwrap.dedent(r'''
    import asyncio, json, os, sys
    sonuc = {}
    async def ana():
        from httpx import ASGITransport, AsyncClient
        from app.main import app
        from app import demo_kip
        sonuc["home"] = os.environ.get("HOME")
        sonuc["kuruldu"] = demo_kip._KURULDU
        sonuc["env"] = {k: os.environ.get(k) for k in ("YUKI_DOSYA_KOKLER", "YUKI_GALERI_KOKLER", "YUKI_SKILLS_DIR", "YUKI_DATA_DIR")}
        yanitlar = {}
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://127.0.0.1") as c:
            async def al(ad, yontem, yol, **kw):
                r = await c.request(yontem, yol, **kw)
                yanitlar[ad] = {"kod": r.status_code, "govde": r.text[:200000],
                                "pp": r.headers.get("permissions-policy", "")}
                return r
            r = await al("dosya_kokler", "GET", "/api/dosya/kokler")
            for k in (r.json().get("kokler") or [])[:2]:
                l = await al("dosya_liste_" + k["ad"], "GET", f"/api/dosya/liste/{k['id']}")
                for o in (l.json().get("girdiler") or [])[:6]:
                    if isinstance(o, dict) and o.get("id") and o.get("klasor"):
                        await al("dosya_alt_" + str(o.get("ad")), "GET", f"/api/dosya/liste/{o['id']}")
            await al("dosya_git_ev", "POST", "/api/dosya/git", json={"yol": sys.argv[1]})
            r = await al("galeri_kokler", "GET", "/api/galeri/kokler")
            await al("galeri_hepsi", "GET", "/api/galeri/hepsi")
            await al("ajan", "GET", "/api/ajan/oturumlar")
            await al("surecler", "GET", "/api/monitor/processes?limit=200")
            await al("anlik", "GET", "/api/monitor/snapshot")
            await al("surec_1", "GET", "/api/monitor/process/1")
            await al("kok_html", "GET", "/")
            await al("demo_js", "GET", "/demo/demo-kip.js")
            await al("plan_listeler", "GET", "/api/todo/lists")
            await al("plan_bugun", "GET", "/api/todo/filter?f=today")
            await al("yedek_durum", "GET", "/api/yedekleme/durum")
        from app.services.tools import network
        sonuc["ip"] = await network.get_public_ip()
        sonuc["yanit"] = yanitlar
    asyncio.run(ana())
    print("@@SONUC@@" + json.dumps(sonuc))
''')


def _gercek_ev(tmp_path: Path) -> Path:
    ev = tmp_path / "gercek-ev"
    (ev / "Belgeler").mkdir(parents=True)
    (ev / "Belgeler" / GIZLI_BELGE).write_text("özel")
    (ev / "Resimler").mkdir()
    # Geçerli küçük PNG (galeri boyut/başlık okuyabilsin)
    (ev / "Resimler" / GIZLI_FOTO).write_bytes(bytes.fromhex(
        "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
        "1f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082"))
    ses = ev / ".claude" / "sessions"
    ses.mkdir(parents=True)
    (ses / f"{os.getpid()}.json").write_text(json.dumps(
        {"pid": os.getpid(), "sessionId": "deadbeef-0000", "cwd": str(ev / GIZLI_PROJE)}))
    (ev / ".claude" / "projects" / GIZLI_PROJE).mkdir(parents=True)
    (ev / ".claude" / "projects" / GIZLI_PROJE / "deadbeef-0000.jsonl").write_text("{}\n")
    return ev


def _kos(tmp_path: Path, demo: bool, ag_yasak: bool = True) -> dict:
    ev = _gercek_ev(tmp_path)
    # *_PROXY da çıkar: vekil tanımlıyken dış istek 127.0.0.1'deki vekile bağlanır, ağ kapısı
    # onu "yerel" sayar → demo sızıntısı kaydedilmez, kapı sahte yeşil.
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("YUKI_", "CLAUDE_", "CODEX_", "XDG_")) and not k.lower().endswith("_proxy")}
    env.update({
        "HOME": str(ev), "PYTHONPATH": str(BACKEND), "SCHEDULER_ENABLED": "false",
        "YUKI_DATA_DIR": str(tmp_path / "gercek-veri"), "YUKI_ANAHTARLIK": "0",
        "AUTH_TOKEN": "", "FACE_AUTH_ENABLED": "false", "ATOLYE": "false",
        "YUKI_DOSYA_KOKLER": str(ev), "YUKI_GALERI_KOKLER": str(ev / "Resimler"),
        "CLAUDE_CONFIG_DIR": str(ev / ".claude"), "XDG_CONFIG_HOME": str(ev / ".config"),
        "YUKI_SKILLS_DIR": str(ev / ".yuki-beceriler"),   # gerçek evi gösteren başka bir kişisel ayar
    })
    (tmp_path / "gercek-veri").mkdir(exist_ok=True)
    (tmp_path / "gercek-veri" / ".env").touch()
    if demo:
        env.update({"YUKI_DEMO": "1", "YUKI_DEMO_KOK": str(tmp_path / "demo-kok")})
    kod = KOSUM
    if ag_yasak:
        # Ağ kapısı: dış bağlantı denemesi = test hatası (IP→konum sorgusu dahil)
        kod = textwrap.dedent('''
            import socket
            _asil = socket.socket.connect
            def _yasak(self, adres, *a, **k):
                h = adres[0] if isinstance(adres, tuple) else adres
                if h not in ("127.0.0.1", "::1", "localhost") and not str(h).startswith("/"):
                    open(os.environ["AG_GUNLUK"], "a").write(str(adres) + "\\n")
                    raise OSError("demo testinde ağ yasak")
                return _asil(self, adres, *a, **k)
            socket.socket.connect = _yasak
            # DNS de dış deneme: ad çözülemeyen makinede connect'e hiç sıra gelmiyordu → kayıt yok.
            _asil_gai = socket.getaddrinfo
            def _yasak_gai(h, *a, **k):
                if h not in (None, "127.0.0.1", "::1", "localhost") and not str(h).startswith("/"):
                    open(os.environ["AG_GUNLUK"], "a").write("dns:" + str(h) + "\\n")
                    raise OSError("demo testinde ağ yasak")
                return _asil_gai(h, *a, **k)
            socket.getaddrinfo = _yasak_gai
        ''') + kod
        env["AG_GUNLUK"] = str(tmp_path / "ag.log")
    kod = "import os\n" + kod
    p = subprocess.run([sys.executable, "-c", kod, str(ev)], cwd=BACKEND, env=env,
                       capture_output=True, text=True, timeout=180)
    satir = [s for s in p.stdout.splitlines() if s.startswith("@@SONUC@@")]
    assert satir, f"koşum çıktı vermedi\nSTDERR:\n{p.stderr[-3000:]}"
    s = json.loads(satir[0][len("@@SONUC@@"):])
    s["ev"] = str(ev)
    ag = tmp_path / "ag.log"
    s["ag"] = ag.read_text().splitlines() if ag.exists() else []
    return s


@pytest.fixture(scope="module")
def demo(tmp_path_factory):
    return _kos(tmp_path_factory.mktemp("demo"), demo=True)


@pytest.fixture(scope="module")
def normal(tmp_path_factory):
    return _kos(tmp_path_factory.mktemp("normal"), demo=False)


# ── Kapı 1: ev değişir ───────────────────────────────────────────────────────
def test_demo_ev_degisir(demo):
    assert demo["kuruldu"] is True
    assert demo["home"] != demo["ev"]
    assert "demo-kok" in demo["home"]


def test_demo_kisisel_ortam_temizlenir(demo):
    """Kapı 1-2: gerçek evi gösteren YUKI_* silinir; dosya/galeri kökü AÇIKÇA demo evi.
    (İkisi birbirinin yedeği — biri kırılınca öbürü sızıntıyı tutar; o yüzden ayrı ölçülür.)"""
    e, ev = demo["env"], demo["home"]
    assert e["YUKI_SKILLS_DIR"] is None
    assert e["YUKI_DOSYA_KOKLER"] == ev
    assert e["YUKI_GALERI_KOKLER"] == ev + "/Resimler"
    assert e["YUKI_DATA_DIR"].startswith(str(Path(ev).parent))


# ── Kapı 1-5 toplu: hiçbir yanıtta gerçek ev yolu ya da bilinen dosya adı yok ─
def test_demo_hicbir_yanitta_kisisel_iz_yok(demo):
    for ad, y in demo["yanit"].items():
        assert demo["ev"] not in y["govde"], f"{ad}: gerçek ev yolu sızdı"
        assert GIZLI_IZ not in y["govde"], f"{ad}: gerçek evdeki dosya/proje adı sızdı"


# ── Kapı 2: dosya + galeri demo içeriği gösterir ────────────────────────────
def test_demo_dosya_ve_galeri_ornek_veri(demo):
    y = demo["yanit"]
    assert y["dosya_kokler"]["kod"] == 200
    hepsi = " ".join(v["govde"] for k, v in y.items() if k.startswith("dosya_liste"))
    assert "Belgeler" in hepsi and "Resimler" in hepsi
    assert "BENI-OKU.md" in y["dosya_alt_Belgeler"]["govde"]
    assert y["galeri_hepsi"]["kod"] == 200
    assert y["galeri_hepsi"]["govde"].count(".webp") >= 20, "galeri demo görsellerini göstermiyor"


def test_demo_elle_yol_gercek_eve_gidemez(demo):
    assert demo["yanit"]["dosya_git_ev"]["kod"] >= 400


# ── Kapı 3: ajan oturumları + süreçler + makine adı ─────────────────────────
def test_demo_ajan_ve_surec_listesi(demo):
    y = demo["yanit"]
    ajan = json.loads(y["ajan"]["govde"])
    assert {o["proje"] for o in ajan["claude"]["oturumlar"]} == {"tarif-defteri", "hava-panosu", "blog-sitesi"}
    surec = json.loads(y["surecler"]["govde"])["processes"]
    assert {"firefox", "yuki-oss"} <= {s["name"] for s in surec}
    assert all(s["user"] == "demo" for s in surec)
    assert '"yuki-demo"' in y["anlik"]["govde"]
    assert json.loads(y["surec_1"]["govde"])["cmdline"] == "/sbin/init"


# ── Kapı 4: konum — sayfaya demo betiği, gerçek konum kapalı, ağ yok ────────
def test_demo_konum_sabit_ve_ag_yok(demo):
    y = demo["yanit"]
    assert '<script src="/demo/demo-kip.js"></script>' in y["kok_html"]["govde"]
    assert y["kok_html"]["pp"] == "geolocation=()"
    js = y["demo_js"]["govde"]
    assert y["demo_js"]["kod"] == 200 and "41.0082" in js and "28.9784" in js
    assert "ipapi" in js and "__LAT__" not in js
    assert demo["ip"].startswith("Genel IP: 203.0.113.10")
    assert demo["ag"] == [], f"demo kipinde dış ağ denemesi: {demo['ag']}"


# ── Kapı 6: Plan + Yedek boş açılmaz (goz 11-13) ─────────────────────────────
def test_demo_plan_ve_yedek_tohumlu(demo):
    y = demo["yanit"]
    assert y["plan_listeler"]["kod"] == 200, y["plan_listeler"]["govde"][:300]
    listeler = json.loads(y["plan_listeler"]["govde"])["lists"]
    assert len(listeler) >= 4
    assert sum(l.get("open_count", 0) for l in listeler) >= 8, listeler
    assert y["plan_bugun"]["kod"] == 200
    assert "Market" in y["plan_bugun"]["govde"], "bugüne tarihli görev yok — tarih bugüne göre kurulmalı"
    import re as _re
    for t in json.loads(y["plan_bugun"]["govde"]).get("tasks", []):
        assert t["due_date"] is None or _re.fullmatch(r"\d{4}-\d{2}-\d{2}", t["due_date"]), t["due_date"]   # saatli = ön yüzde "NaN"
    yd = json.loads(y["yedek_durum"]["govde"])
    assert yd["acik"] is True and yd["zamanlama"] == "03:30"
    adlar = {k["ad"] for k in yd["kaynaklar"]}
    assert {"Belgeler", "Resimler"} <= adlar, adlar
    assert all(k["yol_var"] for k in yd["kaynaklar"])
    # Google demo'da bağlı değil → sahte "son yedek" YOK (Anahtar ↔ BAĞLI türü çelişki olmasın)
    assert yd["son_yedek"] is None and yd["baglanti"]["durum"] != "bagli"


def test_demo_tohumu_kullanici_degisikligini_ezmez(tmp_path, monkeypatch):
    from app import demo_kip
    ev, veri = tmp_path / "ev", tmp_path / "veri"
    (ev / "Belgeler").mkdir(parents=True); veri.mkdir()
    (veri / "todo_store.json").write_text('{"benim": 1}')
    demo_kip.tohumla(ev, veri)
    assert (veri / "todo_store.json").read_text() == '{"benim": 1}'
    ayar = json.loads((veri / "data" / "yedekleme.json").read_text())
    assert [k["ad"] for k in ayar["kaynaklar"]] == ["Belgeler"]   # olmayan Resimler eklenmez


# ── Varsayılan davranış değişmez ────────────────────────────────────────────
def test_varsayilan_degismez(normal):
    assert normal["kuruldu"] is False
    assert normal["home"] == normal["ev"]
    y = normal["yanit"]
    assert y["demo_js"]["kod"] == 404
    assert "demo-kip.js" not in y["kok_html"]["govde"]
    assert y["kok_html"]["pp"] == ""
    # bayraksız kurulum kendi evini görür (ürünün normal hâli)
    # Bayraksız kurulum kendi evini görür (ürünün normal hâli). Bu aynı zamanda
    # demo testlerinin kanıt gücü: sızıntı olsaydı bu ölçüler onu yakalardı.
    assert GIZLI_FOTO in y["galeri_hepsi"]["govde"]
    assert normal["ev"] in y["dosya_kokler"]["govde"]
    assert y["dosya_git_ev"]["kod"] == 200
    assert normal["ag"], "ağ kapısı bayraksız koşuda dış denemeyi kaydetmeli (IP aracı)"
    # tohum yalnız demo kipinde: bayraksız kurulum boş Plan/Yedek ile açılır
    assert len(json.loads(y["plan_listeler"]["govde"])["lists"]) == 1
    assert json.loads(y["yedek_durum"]["govde"])["kaynaklar"][1:] == []


# ── Birim: son süzgeç ───────────────────────────────────────────────────────
def test_metin_temizle_birim(monkeypatch):
    from app import demo_kip
    monkeypatch.setenv("YUKI_DEMO", "1")
    monkeypatch.setattr(demo_kip, "_GERCEK_EV", "/home/ornekkisi")
    monkeypatch.setattr(demo_kip, "_GERCEK_KULLANICI", "ornekkisi")
    assert demo_kip.metin_temizle("/home/ornekkisi/Belgeler") == "~/Belgeler"
    assert demo_kip.metin_temizle("/run/media/ornekkisi/usb") == "/run/media/demo/usb"
    assert demo_kip.metin_temizle("ornekkisiler") == "ornekkisiler"   # kelime içi dokunulmaz
    monkeypatch.setenv("YUKI_DEMO", "0")
    assert demo_kip.metin_temizle("/home/ornekkisi") == "/home/ornekkisi"


def test_demo_veri_boyut_ve_lisans():
    kok = BACKEND / "demo_veri"
    gorseller = list((kok / "ev" / "Resimler").rglob("*.webp"))
    assert 20 <= len(gorseller) <= 40
    assert sum(p.stat().st_size for p in kok.rglob("*") if p.is_file()) <= 15 * 1024 * 1024
    kaynak = (kok / "KAYNAK.md").read_text("utf-8")
    for g in gorseller:
        assert f"`{g.relative_to(kok / 'ev' / 'Resimler')}`" in kaynak, f"KAYNAK.md'de yok: {g.name}"
