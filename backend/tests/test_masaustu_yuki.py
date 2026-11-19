"""Masaüstü Yuki'yi Yuki'den aç/kapat — services/masaustu_yuki.py + anahtar + sohbet aracı + çapa süzgeci.

Ekrana HİÇBİR ŞEY açılmaz: gerçek masaustu.py yerine tmp'de `masaustu.py` adlı sahte betik koşar. Sahte betik
kilidi GERÇEK `masaustu/tek_ornek.py` ile alır — backend'in okuduğu dosya adlarıyla masaüstünün yazdıkları
aynı mı, bu da ölçülür. `XDG_RUNTIME_DIR` ve `config.user.json` tmp'ye çevrilir; canlı ayara dokunulmaz.
"""
import asyncio
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from app import config as cfg
from app import config_manager
from app.services import masaustu_yuki as my

MASAUSTU_DIZIN = Path(__file__).resolve().parents[2] / "masaustu"

SAHTE = f'''
import os, signal, sys, time
sys.path.insert(0, {str(MASAUSTU_DIZIN)!r})
from tek_ornek import al, birak
if os.environ.get("SAHTE_HEMEN"):
    sys.exit(int(os.environ["SAHTE_HEMEN"]))
kilit, sahip = al()
if kilit is None:
    sys.exit(5)
calis = [True]
signal.signal(signal.SIGTERM, lambda *_: calis.__setitem__(0, False))
bitis = time.monotonic() + float(os.environ.get("SAHTE_SURE", "30"))
while calis[0] and time.monotonic() < bitis:
    time.sleep(0.05)
birak(kilit)
sys.exit(int(os.environ.get("SAHTE_KOD", "0")))
'''


@pytest.fixture
def ortam(tmp_path, monkeypatch):
    calisma = tmp_path / "run"
    calisma.mkdir()
    betik = tmp_path / "masaustu.py"
    betik.write_text(SAHTE)
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(calisma))
    monkeypatch.setenv("WAYLAND_DISPLAY", "sahte-0")
    vrm = tmp_path / "kullanici.vrm"          # sahte dosya: depoda model yok, kullanıcının kendi VRM'i yerine geçer
    vrm.write_bytes(b"glTF")
    monkeypatch.setattr(cfg, "MASAUSTU_VRM", str(vrm), raising=False)
    for k in ("SAHTE_HEMEN", "SAHTE_SURE", "SAHTE_KOD"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(my, "BETIK", betik)
    monkeypatch.setattr(my, "PYTHON", sys.executable)
    monkeypatch.setattr(my, "_proc", None)
    monkeypatch.setattr(my, "_durdurulan", set())
    monkeypatch.setattr(my, "_sahibiz", False)
    monkeypatch.setattr(my, "son_hata", None)
    monkeypatch.setattr(config_manager, "CONFIG_USER_PATH", tmp_path / "config.user.json")
    monkeypatch.setattr(config_manager, "_cache", None)
    monkeypatch.setattr(cfg, "MASAUSTU_YUKI", False, raising=False)
    yield calisma
    my.durdur(bekle=2)
    # izleyici iş parçacıkları monkeypatch geri alınmadan bitsin — yoksa ayarı GERÇEK config.user.json'a yazar
    # (ölçüldü: tam takımdan sonra worktree'de `{"MASAUSTU_YUKI": false}` kalmıştı)
    for t in threading.enumerate():
        if t.name == "masaustu-izle":
            t.join(5)


def _bekle(kosul, sn=4.0):
    t0 = time.monotonic()
    while time.monotonic() - t0 < sn:
        if kosul():
            return True
        time.sleep(0.05)
    return kosul()


# ── servis ────────────────────────────────────────────────────────

def test_baslat_kilidi_gorur_ikinci_acilmaz(ortam):
    r = my.baslat()
    assert r["ok"] and not r["zaten"] and r["pid"]
    d = my.durum()
    assert d["calisiyor"] and d["pid"] == r["pid"]          # tek_ornek'in PID dosyası = backend'in okuduğu
    r2 = my.baslat()
    assert r2["ok"] and r2["zaten"] and r2["pid"] == r["pid"]


def test_durdur_kapatir_ayara_dokunmaz(ortam):
    my.ayarla(True)
    assert cfg.MASAUSTU_YUKI is True
    r = my.durdur()
    assert r["ok"] and not my.durum()["calisiyor"]
    assert config_manager.load().get("MASAUSTU_YUKI") is True   # backend kapanışı ayarı silmez
    time.sleep(0.3)                                            # izleyici "kullanıcı kapattı" sanmamalı
    assert config_manager.load().get("MASAUSTU_YUKI") is True


def test_ayarla_ac_kapat_ayari_yazar(ortam):
    assert my.ayarla(True)["ok"]
    assert config_manager.load()["MASAUSTU_YUKI"] is True and my.durum()["calisiyor"]
    assert my.ayarla(False)["ok"]
    assert config_manager.load()["MASAUSTU_YUKI"] is False and not my.durum()["calisiyor"]


def test_acilamazsa_ayar_acik_yazilmaz(ortam, monkeypatch):
    monkeypatch.setenv("SAHTE_HEMEN", "2")
    r = my.ayarla(True)
    assert not r["ok"] and r["durum"] == "desteklenmiyor"      # masaustu.py çıkış 2 = GTK/WebKit yok
    assert config_manager.load().get("MASAUSTU_YUKI") is None and cfg.MASAUSTU_YUKI is False
    monkeypatch.setenv("SAHTE_HEMEN", "4")
    r = my.ayarla(True)
    assert not r["ok"] and "çıkış 4" in r["hata"] and r["durum"] == "hata"


def test_kilidi_alip_hemen_olen_acildi_sayilmaz(ortam, monkeypatch):
    # kilidi aldıktan sonra 3 ile çıkan (yüzey yok) süreç "açıldı" sayılmaz: desteklenmiyor durumu
    monkeypatch.setenv("SAHTE_SURE", "0.3")
    monkeypatch.setenv("SAHTE_KOD", "3")
    r = my.ayarla(True)
    assert not r["ok"] and r["durum"] == "desteklenmiyor" and "desteklenmiyor" in r["hata"]
    assert config_manager.load().get("MASAUSTU_YUKI") is None


def test_grafik_oturumu_yoksa_desteklenmiyor_surec_acilmaz(ortam, monkeypatch):
    monkeypatch.delenv("WAYLAND_DISPLAY")
    monkeypatch.delenv("DISPLAY", raising=False)
    r = my.baslat()
    assert not r["ok"] and r["durum"] == "desteklenmiyor" and "desteklenmiyor" in r["hata"]
    assert my._proc is None and not my.durum()["calisiyor"]
    assert my.durum()["durum"] == "desteklenmiyor"
    assert config_manager.load().get("MASAUSTU_YUKI") is None      # ayar açılmaz, hata atılmaz


def test_linux_disi_masaustu_desteklenmiyor(ortam, monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    r = my.ayarla(True)
    assert not r["ok"] and r["durum"] == "desteklenmiyor" and my._proc is None
    assert cfg.MASAUSTU_YUKI is False


def test_model_yoksa_acilmaz(ortam, monkeypatch):
    monkeypatch.setattr(cfg, "MASAUSTU_VRM", "")
    r = my.ayarla(True)
    assert not r["ok"] and r["durum"] == "model_yok" and "model yok" in r["hata"]
    assert my._proc is None and not my.durum()["calisiyor"] and my.durum()["durum"] == "model_yok"
    assert config_manager.load().get("MASAUSTU_YUKI") is None
    monkeypatch.setattr(cfg, "MASAUSTU_VRM", "/yok/yok/yuki.vrm")       # dosya yok
    assert my.baslat()["durum"] == "model_yok"
    assert "model yok" in my.arac("ac")


def test_vrm_olmayan_dosya_model_sayilmaz(ortam, tmp_path, monkeypatch):
    baska = tmp_path / "x.png"
    baska.write_bytes(b"x")
    monkeypatch.setattr(cfg, "MASAUSTU_VRM", str(baska))
    assert my.model_yolu() is None


def test_host_model_yok_cikis_6_modeli_gercek_betik_okur(tmp_path):
    # gerçek masaustu.py: model verilmezse GTK'ya hiç girmeden 6 ile çıkar
    env = {k: v for k, v in os.environ.items() if k != "YUKI_MASAUSTU_VRM"}
    r = subprocess.run([sys.executable, str(MASAUSTU_DIZIN / "masaustu.py"), "--kuru"], env=env,
                       capture_output=True, text=True, timeout=30)
    assert r.returncode == 6 and "model yok" in r.stderr


def test_model_cocuga_ortamdan_gider_depoda_vrm_yok(ortam):
    env = my._ortam(my.model_yolu())
    assert env["YUKI_MASAUSTU_VRM"] == str(my.model_yolu())
    kok = Path(__file__).resolve().parents[2]
    assert not list((kok / "masaustu").rglob("*.vrm")) and not list((kok / "frontend").rglob("*.vrm"))


def test_kullanici_kapatinca_ayar_kapanir(ortam, monkeypatch):
    monkeypatch.setenv("SAHTE_SURE", "2.2")                   # sağ tık gibi: açıldıktan sonra kendisi 0 ile çıkar
    assert my.ayarla(True)["ok"]
    assert _bekle(lambda: config_manager.load().get("MASAUSTU_YUKI") is False, 5)
    assert cfg.MASAUSTU_YUKI is False


def test_cokme_ayari_degistirmez_hata_yazar(ortam, monkeypatch):
    monkeypatch.setenv("SAHTE_SURE", "2.2")
    monkeypatch.setenv("SAHTE_KOD", "3")
    assert my.ayarla(True)["ok"]
    assert _bekle(lambda: my.son_hata is not None, 5)
    assert "çıkış 3" in my.son_hata
    assert config_manager.load()["MASAUSTU_YUKI"] is True     # sonraki açılışta yine dener


def test_baskasinin_pidine_sinyal_gitmez(ortam, tmp_path):
    # kilidi masaustu.py OLMAYAN bir süreç tutuyor (PID yeniden kullanımı benzetimi)
    yabanci = tmp_path / "baska.py"
    yabanci.write_text(SAHTE)
    p = subprocess.Popen([sys.executable, str(yabanci)], env={**os.environ, "SAHTE_SURE": "10"})
    try:
        assert _bekle(lambda: my.durum()["calisiyor"])
        r = my.durdur()
        assert not r["ok"] and "doğrulanamadı" in r["hata"]
        assert p.poll() is None                                # öldürülmedi
    finally:
        p.terminate(); p.wait(5)


def test_elle_acilan_ornek_gorulur_ve_kapatilabilir(ortam):
    # run.sh ile elle açılmış gibi: backend açmadı ama "git" deyince kapatabilmeli
    p = subprocess.Popen([sys.executable, str(my.BETIK)])
    try:
        assert _bekle(lambda: my.durum()["calisiyor"])
        assert my.baslat()["zaten"]                            # ikinci örnek açmadı
        assert my.ayarla(False)["ok"]
        assert p.wait(5) == 0
    finally:
        if p.poll() is None:
            p.kill()


@pytest.mark.asyncio
async def test_kapanista_yalniz_sahipse_kapatir(ortam):
    p = subprocess.Popen([sys.executable, str(my.BETIK)])
    try:
        assert _bekle(lambda: my.durum()["calisiyor"])
        await my.kapanista()                                   # sahip değiliz (ör. test kipi ikinci örneği)
        assert my.durum()["calisiyor"]
        my.baslat()                                            # devraldı
        await my.kapanista()
        assert not my.durum()["calisiyor"]
        assert p.wait(5) == 0
    finally:
        if p.poll() is None:
            p.kill()


@pytest.mark.asyncio
async def test_acilista_ayara_bakar(ortam, monkeypatch):
    await my.acilista(gecikme=0)
    assert not my.durum()["calisiyor"]
    monkeypatch.setattr(cfg, "MASAUSTU_YUKI", True)
    await my.acilista(gecikme=0)
    assert my.durum()["calisiyor"]
    await my.kapanista()
    assert not my.durum()["calisiyor"]
    assert cfg.MASAUSTU_YUKI is True


def test_eski_izleyici_yeni_acilisi_bozmaz(ortam):
    # durdur → hemen yeniden aç: eski sürecin kapanışı "kullanıcı kapattı" sayılıp ayarı KAPATMAMALI
    for _ in range(3):
        assert my.ayarla(True)["ok"]
        assert my.durdur()["ok"]
    assert my.ayarla(True)["ok"]
    time.sleep(0.5)
    assert config_manager.load()["MASAUSTU_YUKI"] is True and my.durum()["calisiyor"]


def test_testler_gercek_ayar_dosyasina_yazmaz():
    gercek = Path(config_manager.__file__).resolve().parents[1] / "config.user.json"
    if gercek.exists():
        assert "MASAUSTU_YUKI" not in gercek.read_text()


def test_cocuga_venv_ortami_gecmez(ortam, monkeypatch):
    monkeypatch.setenv("PYTHONPATH", "/venv/kirli")
    monkeypatch.setenv("VIRTUAL_ENV", "/venv")
    env = my._ortam(my.model_yolu())
    assert "PYTHONPATH" not in env and "VIRTUAL_ENV" not in env and env["WAYLAND_DISPLAY"] == "sahte-0"
    assert "GDK_BACKEND" not in env or env["GDK_BACKEND"] == os.environ.get("GDK_BACKEND")   # yüzeyi host seçer


# ── sohbet aracı ──────────────────────────────────────────────────

def test_arac_metinleri(ortam):
    assert "geldim" in my.arac("ac")
    assert "Zaten masaüstündeyim" in my.arac("ac")
    assert "açık" in my.arac("durum")
    assert "çekildim" in my.arac("kapat")
    assert "değildim" in my.arac("kapat")


def test_arac_semada_tek_motordan_cagrilir(monkeypatch):
    from app.services.tools import dispatcher
    sema = next(t for t in dispatcher.TOOLS if t["function"]["name"] == "masaustu_yuki")
    assert sema["function"]["parameters"]["properties"]["islem"]["enum"] == ["ac", "kapat", "durum"]
    cagri = []
    monkeypatch.setattr(my, "arac", lambda islem: cagri.append(islem) or "tamam")
    from app.services.atolye.baglam import yerel_baglam
    with yerel_baglam():
        sonuc = asyncio.run(dispatcher.call_tool("masaustu_yuki", {"islem": "ac"}))
    assert cagri == ["ac"] and "tamam" in str(sonuc)


def test_arac_dis_baglamda_kapali():
    from app.services.atolye.turler import _DIS_YASAK
    assert "masaustu_yuki" in _DIS_YASAK                       # telefon/tünel: open_application ile aynı sınıf


def test_alan_secici_masaustu_cumlesini_tanir():
    from app.services.tools import alan_secici
    for cumle in ("masaüstüne gel", "Masaustunden git artık", "yanıma gel yuki"):
        assert "masaustu" in alan_secici.alanlari_esle(cumle), cumle


# ── anahtar (HQ › AYARLAR) ────────────────────────────────────────

def test_anahtar_semada_sistem_bolumunde_canli():
    from app.api import settings_api
    s = next(i for i in settings_api.SETTINGS_SCHEMA if i["key"] == "MASAUSTU_YUKI")
    assert s["type"] == "toggle" and s["cat"] == "gelistirici"
    assert "MASAUSTU_YUKI" in settings_api.CANLI_UYGULANAN
    assert config_manager.ALLOWED_KEYS["MASAUSTU_YUKI"] is bool and config_manager.ALLOWED_KEYS["MASAUSTU_VRM"] is str
    assert not os.environ.get("MASAUSTU_YUKI")   # varsayılan kapalı (config.py: "false")


@pytest.mark.asyncio
async def test_anahtar_ayarla_cagirir(monkeypatch, ortam):
    from app.api import settings_api
    cagri = []
    monkeypatch.setattr(my, "ayarla", lambda acik: cagri.append(acik) or {"ok": True, "zaten": False, "pid": 1})
    r = await settings_api.set_setting.__wrapped__(None, "MASAUSTU_YUKI", settings_api.SettingUpdate(value=True))
    assert cagri == [True] and r["ok"] and r["needs_restart"] is False


@pytest.mark.asyncio
async def test_anahtar_acilamazsa_409_ayar_yazilmaz(monkeypatch, ortam):
    from app.api import settings_api
    monkeypatch.setenv("SAHTE_HEMEN", "4")
    with pytest.raises(Exception) as e:
        await settings_api.set_setting.__wrapped__(None, "MASAUSTU_YUKI", settings_api.SettingUpdate(value=True))
    assert getattr(e.value, "status_code", None) == 409 and "açılamadı" in e.value.detail
    assert "MASAUSTU_YUKI" not in config_manager.load()


@pytest.mark.asyncio
async def test_anahtar_model_yoksa_200_kapali_kalir(monkeypatch, ortam):
    from app.api import settings_api
    monkeypatch.setattr(cfg, "MASAUSTU_VRM", "")
    r = await settings_api.set_setting.__wrapped__(None, "MASAUSTU_YUKI", settings_api.SettingUpdate(value=True))
    assert r["ok"] is False and r["value"] is False and r["masaustu"]["durum"] == "model_yok"
    assert "MASAUSTU_YUKI" not in config_manager.load()


# ── çapa süzgeci (ön yüz → masaüstü) ──────────────────────────────

def test_capa_suzgeci_yalniz_sayi_gecirir():
    from app.api.websocket import masaustu_capa_suz
    iyi = masaustu_capa_suz({"type": "masaustu_capa", "vw": 1900, "vh": 1000, "panel": [10, 20, 300, 400],
                             "cubuk": None, "paneller": [[1, 2, 3, 4], "x", [1, 2, 3], [0, 0, 5, 5]], "sizinti": "x"})
    assert iyi == {"type": "masaustu_capa", "vw": 1900.0, "vh": 1000.0, "panel": [10.0, 20.0, 300.0, 400.0],
                   "cubuk": None, "paneller": [[1.0, 2.0, 3.0, 4.0], [0.0, 0.0, 5.0, 5.0]]}
    assert masaustu_capa_suz({"vw": "9", "vh": 1000}) is None
    assert masaustu_capa_suz({"vw": True, "vh": 1000}) is None
    assert masaustu_capa_suz({"vw": 50, "vh": 1000}) is None


def test_ws_capa_iletisi_sohbet_turu_acmaz():
    src = (Path(__file__).resolve().parents[1] / "app" / "api" / "websocket.py").read_text()
    i = src.index('msg.get("type") == "masaustu_capa"')
    assert "continue" in src[i:i + 500]


@pytest.mark.asyncio
async def test_varsayilana_don_kapatir(ortam):
    from app.api import settings_api
    assert my.ayarla(True)["ok"]
    r = await settings_api.varsayilana_don.__wrapped__(None, "MASAUSTU_YUKI")
    assert r["ok"] and not my.durum()["calisiyor"]
