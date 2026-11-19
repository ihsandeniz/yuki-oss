"""HQ › MODLAR backend sözleşmesi (2026-09-27, Faz 0.5 — kişisel 097779b'nin ürün karşılığı).

Kapanan kusurlar (üründe ölçüldü):
  · /run/{id} gevşek eşleşmeyle çalışıyordu. Kapalı modlar yükleyicide süzüldüğü için kapalı bir
    modun id'si adı ona benzeyen BAŞKA bir açık modu başlatıyordu → panel ucu yalnız birebir id.
  · Kapalı mod: 409 (sessizce başka mod değil).
  · Kısmi başarı ("✓ … ⚠ …") 200 + düz "ok" dönüyordu → `uyari` alanı.
  · Arayüz PUT'ta id göndermiyor → yeniden adlandırma id'yi değiştiriyordu → id korunur.
  · Aynı uygulama iki kez yazılınca iki pencere açılıyordu → kayıtta tekillenir.
Üründe mod başlatıcı bayrağı (kişiseldeki MODE_LAUNCHER_ENABLED) YOK — o madde taşınmadı.
Testler canlı modes.json'a dokunmaz; hiçbir mod gerçekten başlatılmaz (start_mode sahte).
"""
import pytest

from app.api import modes_api
from app.services.tools import modes as modes_svc

MODLAR = [
    {"id": "dosya", "name": "Dosya", "trigger_keywords": [], "apps": ["nautilus"], "enabled": False},
    {"id": "dosya_yonetimi", "name": "Dosya Yönetimi", "trigger_keywords": ["dosya modu"],
     "apps": ["nautilus"], "enabled": True},
]


@pytest.fixture
def sahte(monkeypatch, tmp_path):
    import json
    durum = {"modlar": [dict(m) for m in MODLAR], "baslatilan": [], "kayit": None}
    monkeypatch.setattr(modes_api, "list_modes_struct", lambda: [dict(m) for m in durum["modlar"]])

    def kaydet(modlar):
        durum["kayit"] = modlar
        return True, "ok"
    monkeypatch.setattr(modes_api, "save_modes_file", kaydet)

    # start_mode GERÇEK (_find_mode eşleşmesi ölçülsün) — yalnız eylemler ve kart sahte
    yol = tmp_path / "modes.json"
    yol.write_text(json.dumps({"modes": durum["modlar"]}), encoding="utf-8")
    monkeypatch.setattr(modes_svc, "MODES_PATH", str(yol))
    monkeypatch.setattr(modes_svc, "_modes_cache", None)

    def eylem(mod):
        durum["baslatilan"].append(mod["id"])
        return durum.get("sonuc", (["nautilus açıldı"], []))
    monkeypatch.setattr(modes_svc, "_run_mode_actions", eylem)

    async def kart(_m):
        return None
    monkeypatch.setattr(modes_svc, "_emit_card", kart)
    return durum


async def test_kapali_mod_baska_modu_baslatmaz(client, sahte):
    r = await client.post("/api/modes/run/dosya")
    assert r.status_code == 409, r.text
    assert sahte["baslatilan"] == []


async def test_yalniz_birebir_id(client, sahte):
    r = await client.post("/api/modes/run/dosya_yon")   # gevşek eşleşme Dosya Yönetimi'ni bulurdu
    assert r.status_code == 404 and sahte["baslatilan"] == []
    r = await client.post("/api/modes/run/dosya_yonetimi")
    assert r.status_code == 200 and r.json()["uyari"] is False
    assert sahte["baslatilan"] == ["dosya_yonetimi"]


async def test_kismi_basari_uyari_tasir(client, sahte):
    sahte["sonuc"] = (["terminal açıldı"], ["nautilus bulunamadı"])
    r = await client.post("/api/modes/run/dosya_yonetimi")
    assert r.status_code == 200 and r.json()["uyari"] is True


async def test_yeniden_adlandirma_id_korur_ve_uygulama_tekillenir(client, sahte):
    # Arayüzün gönderdiği gövde: id YOK (intro-sequences.js hqModeSave)
    r = await client.put("/api/modes/dosya_yonetimi",
                         json={"name": "Dosyalar", "apps": ["nautilus", "nautilus", "gnome-terminal"]})
    assert r.status_code == 200, r.text
    assert r.json()["mode"]["id"] == "dosya_yonetimi"
    assert r.json()["mode"]["apps"] == ["nautilus", "gnome-terminal"]
    assert sahte["kayit"][1]["id"] == "dosya_yonetimi"


def test_kapali_mesaj_iki_dilde():
    from app.mesajlar import en, tr
    for sozluk in (tr, en):
        metin = sozluk.METINLER["mod.kapali"]
        assert "{ad}" in metin


# ── Mod dosyası paketin içinde değil kullanıcının veri dizininde (2026-09-27) ──────────
# Yayındaki 0.7.0 AppImage'inde resources/backend/modes.json salt-okunur (fuse ro) ölçüldü:
# Linux müşterisi mod ekleyemiyor/düzenleyemiyordu; modlar Drive yedeğine de girmiyordu
# (yedekleme.py modes.json'u YUKI_DATA_DIR'de arıyor).

def _config_modes_path(ortam: dict) -> tuple[str, str]:
    import os
    import subprocess
    import sys
    kod = "from app import config as c; print(c.MODES_PATH); print(c.MODES_SEED_PATH)"
    temiz = {k: v for k, v in os.environ.items() if k not in ("YUKI_DATA_DIR", "MODES_PATH")}
    cikti = subprocess.run([sys.executable, "-c", kod], env={**temiz, **ortam}, capture_output=True,
                           text=True, check=True, cwd=os.path.dirname(os.path.dirname(__file__))).stdout.split("\n")
    return cikti[0], cikti[1]


def test_paketli_uygulamada_mod_dosyasi_veri_dizininde(tmp_path):
    yol, tohum = _config_modes_path({"YUKI_DATA_DIR": str(tmp_path)})
    assert yol == str(tmp_path / "modes.json")
    assert tohum.endswith("backend/modes.json") and tohum != yol


def test_gelistirmede_eski_yol_korunur():
    yol, tohum = _config_modes_path({})
    assert yol == tohum and yol.endswith("backend/modes.json")


def test_kullanici_dosyasi_yokken_tohum_okunur_ilk_kayit_kullaniciya(tmp_path, monkeypatch):
    import json
    tohum = tmp_path / "paket" / "modes.json"
    tohum.parent.mkdir()
    tohum.write_text(json.dumps({"version": "1.0", "_note": "not", "modes": [
        {"id": "eski", "name": "Eski", "apps": ["nautilus"], "enabled": True}]}), encoding="utf-8")
    tohum.chmod(0o444)   # paket salt-okunur
    kullanici = tmp_path / "veri" / "modes.json"
    monkeypatch.setattr(modes_svc, "MODES_SEED_PATH", str(tohum))
    monkeypatch.setattr(modes_svc, "MODES_PATH", str(kullanici))
    monkeypatch.setattr(modes_svc, "_modes_cache", None)

    assert [m["id"] for m in modes_svc.list_modes_struct()] == ["eski"]   # eski kurulumun modu kaybolmaz
    assert "eski" in modes_svc._load_modes(force=True)
    ok, _ = modes_svc.save_modes_file(modes_svc.list_modes_struct() + [{"id": "yeni", "name": "Yeni"}])
    assert ok
    kayit = json.loads(kullanici.read_text(encoding="utf-8"))
    assert [m["id"] for m in kayit["modes"]] == ["eski", "yeni"] and kayit["_note"] == "not"
    assert not (tohum.parent / "modes.json.backup").exists()   # pakete yedek yazmaya kalkmaz
    assert [m["id"] for m in modes_svc.list_modes_struct()] == ["eski", "yeni"]


# ── "Mod Başlatıcı" anahtarı gerçekten bir şey yapıyor (2026-09-27) ────────────────────
# Bayrak AYARLAR › Sistem'de duruyordu ama hiçbir kod okumuyordu: kapatınca modlar yine başlıyordu.

async def test_baslatici_kapaliyken_hicbir_yol_mod_baslatmaz(client, sahte, monkeypatch):
    from app import config as cfg
    monkeypatch.setattr(cfg, "MODE_LAUNCHER_ENABLED", False)
    r = await client.post("/api/modes/run/dosya_yonetimi")
    assert r.status_code == 409
    sonuc = await modes_svc.start_mode("dosya modu")          # LLM aracı / ön-tetik / autostart yolu
    assert "Mod Başlatıcı kapalı" in sonuc or "Mode launcher is off" in sonuc
    assert sahte["baslatilan"] == []


async def test_baslatici_acikken_calisir(client, sahte, monkeypatch):
    from app import config as cfg
    monkeypatch.setattr(cfg, "MODE_LAUNCHER_ENABLED", True)
    r = await client.post("/api/modes/run/dosya_yonetimi")
    assert r.status_code == 200 and sahte["baslatilan"] == ["dosya_yonetimi"]


def test_baslatici_ayari_canli_isaretli():
    from app.api.settings_api import CANLI_UYGULANAN
    assert "MODE_LAUNCHER_ENABLED" in CANLI_UYGULANAN, "arayüz 'yeniden başlat' derdi — oysa anında geçiyor"
