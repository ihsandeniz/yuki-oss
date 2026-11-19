"""Araç koruma kapıları — yol, hedef, boş girdi ve "hepsi düştü" kapıları.

Yan etki yok: dosyalar geçici dizinde; hyprctl, os.kill, httpx ve model çağrısı sahte.
· W1 wiki_write: korumalı dosya ham metinle karşılaştırılıyordu (`WIKI/./index.md` ezilirdi);
     kök kapısı `startswith` olduğu için kardeş dizin `WIKI-disari` geçerdi; onay listesinde yoktu
· G1 analyze_image: read_file'ın yol + hassas dosya kapısı yoktu → `~/.ssh` altındaki görsel
     bile buluttaki modele gidiyordu; onay listesinde yoktu
· A1 search_file: read_file'ın reddettiği yerde arama yapıyordu; dönen dosya adı içerik
     varlığını sızdırır
· O1 close_game: başlığında oyun adı geçen herhangi bir pencereyi (terminal, tarayıcı) SIGTERM'liyordu
· E1 smart_home: boş cihaz adı `'' in alias` ile ilk cihazı seçiyordu
· N1 trigger_n8n: workflow adındaki `../` webhook kökünden başka uca gidiyordu
· S1 monitor_process: boş ad ilk süreci seçiyordu
· T1 run_team / delegate_to_companion: boş hedef plan için model harcıyordu
· T2 run_team: uzmanların hepsi düşünce sentez modeli hata metinlerinden başarı cevabı yazıyordu
· U1 delegate_task / get_task_result / uai_status: arkasında servis olmayan kişisel entegrasyon
· L1 list_directory: 15 sn önbellek, az önce yazılan dosyayı göstermiyordu
· N2 delete_note: not geri dönüşsüz siliniyordu (görev silme çöpe atıyor)
"""
from __future__ import annotations

import asyncio
import json
import types

import pytest

from app.services.tools import approval_gate, files, media, notes_tools, smart_home, system, wiki
from app.services import mcp_client
from app.services import orchestrator as orch


# ── W1 wiki_write ────────────────────────────────────────────────────────────
@pytest.fixture
def wiki_kok(tmp_path, monkeypatch):
    kok = tmp_path / "WIKI"
    kok.mkdir()
    (kok / "index.md").write_text("ASIL", encoding="utf-8")
    monkeypatch.setattr(wiki, "WIKI_ROOT", kok)
    monkeypatch.setattr(wiki, "_BASE", tmp_path)
    return kok


@pytest.mark.parametrize("yol", ["WIKI/./index.md", "WIKI/alt/../index.md", "WIKI//index.md"])
def test_w1_korumali_dosya_dolambacla_ezilmez(wiki_kok, yol):
    r = wiki.wiki_write(yol, "EZ")
    assert r.startswith("Hata"), r
    assert (wiki_kok / "index.md").read_text(encoding="utf-8") == "ASIL"


def test_w1_korumali_dosyaya_ekleme_serbest(wiki_kok):
    assert wiki.wiki_write("WIKI/./index.md", "ek", append=True).startswith("OK")
    assert (wiki_kok / "index.md").read_text(encoding="utf-8") == "ASIL\nek"


def test_w1_kardes_dizine_yazilmaz(wiki_kok, tmp_path):
    r = wiki.wiki_write("WIKI/../WIKI-disari/kacis.md", "x")
    assert r.startswith("Hata"), r
    assert not (tmp_path / "WIKI-disari" / "kacis.md").exists()


def test_w1_normal_sayfa_yazilir(wiki_kok):
    assert wiki.wiki_write("WIKI/notlar/yeni.md", "merhaba").startswith("OK")
    assert (wiki_kok / "notlar" / "yeni.md").read_text(encoding="utf-8") == "merhaba"


@pytest.mark.parametrize("ad", ["wiki_write", "analyze_image"])
def test_w1_g1_onay_listesinde(ad):
    assert ad in approval_gate.CRITICAL_TOOLS


# ── G1 analyze_image ─────────────────────────────────────────────────────────
@pytest.fixture
def model_yok(monkeypatch):
    """Kapı geçilirse model çağrısı yapılır: sahte istemci çağrıyı kaydeder."""
    cagri: list = []

    async def _create(**kw):
        cagri.append(kw)
        return types.SimpleNamespace(choices=[types.SimpleNamespace(
            message=types.SimpleNamespace(content="MODEL GÖRDÜ"))])

    istemci = types.SimpleNamespace(chat=types.SimpleNamespace(
        completions=types.SimpleNamespace(create=_create)))
    import app.services.llm as llm
    monkeypatch.setattr(llm, "_get_client", lambda *a, **k: istemci)
    return cagri


def test_g1_hassas_dizindeki_gorsel_buluta_gitmez(tmp_path, model_yok):
    p = tmp_path / ".ssh" / "anahtar.png"
    p.parent.mkdir()
    p.write_bytes(b"\x89PNG\r\n\x1a\n")
    r = asyncio.run(files.analyze_image(str(p)))
    assert r.startswith("Hata"), r
    assert model_yok == []


def test_g1_guvenli_kok_disindaki_gorsel_buluta_gitmez(tmp_path, monkeypatch, model_yok):
    p = tmp_path / "a.png"
    p.write_bytes(b"\x89PNG\r\n\x1a\n")
    # tmp_path /tmp altında; kökü "yalnız başka bir yer" yaparak kök dışını taklit ederiz.
    import app.services.tools._base as base
    monkeypatch.setattr(base, "_SAFE_ROOTS", [tmp_path / "baska"])
    r = asyncio.run(files.analyze_image(str(p)))
    assert r.startswith("Hata"), r
    assert model_yok == []


def test_g1_izinli_gorsel_analiz_edilir(tmp_path, model_yok):
    p = tmp_path / "kedi.png"
    p.write_bytes(b"\x89PNG\r\n\x1a\n")
    assert asyncio.run(files.analyze_image(str(p))) == "MODEL GÖRDÜ"
    assert len(model_yok) == 1


# ── A1 search_file ───────────────────────────────────────────────────────────
def test_a1_hassas_dizinde_arama_yapilmaz(tmp_path):
    d = tmp_path / ".ssh"
    d.mkdir()
    (d / "notlar.txt").write_text("KANARYA", encoding="utf-8")
    r = files.search_file("KANARYA", str(d))
    assert r.startswith("Hata"), r
    assert "notlar.txt" not in r


def test_a1_hassas_dosya_sonuc_listesinden_cikar(tmp_path):
    # Gizli olmayan ad: rg gizli dosyaları (`.env`) zaten atlar, süzgeci sınamaz.
    (tmp_path / "id_rsa_yedek").write_text("KANARYA", encoding="utf-8")
    (tmp_path / "acik.txt").write_text("KANARYA", encoding="utf-8")
    r = files.search_file("KANARYA", str(tmp_path))
    assert "acik.txt" in r
    assert "id_rsa" not in r


def test_a1_hassas_dosya_ad_aramasinda_da_cikar(tmp_path):
    (tmp_path / "id_rsa_KANARYA").write_text("x", encoding="utf-8")
    r = files.search_file("KANARYA", str(tmp_path))
    assert "id_rsa" not in r


def test_a1_kok_disinda_arama_yapilmaz(tmp_path, monkeypatch):
    (tmp_path / "a.txt").write_text("KANARYA", encoding="utf-8")
    import app.services.tools._base as base
    monkeypatch.setattr(base, "_SAFE_ROOTS", [tmp_path / "baska"])
    r = files.search_file("KANARYA", str(tmp_path))
    assert r.startswith("Hata"), r


# ── O1 close_game ────────────────────────────────────────────────────────────
def _pencereler(monkeypatch, clients):
    olduren: list = []
    monkeypatch.setattr(media.subprocess, "run", lambda *a, **k: types.SimpleNamespace(
        returncode=0, stdout=json.dumps(clients), stderr=""))
    monkeypatch.setattr(media.os, "kill", lambda pid, sig: olduren.append(pid))
    return olduren


def test_o1_uygulama_penceresi_oyun_diye_kapanmaz(monkeypatch):
    uygulama = media.APP_WHITELIST[0]
    olduren = _pencereler(monkeypatch, [
        {"class": uygulama, "title": "minecraft wiki — tarif", "pid": 4242},
    ])
    r = media.close_game("minecraft")
    assert olduren == [], r
    assert "kapatmadım" in r


def test_o1_gercek_oyun_penceresi_kapanir(monkeypatch):
    uygulama = media.APP_WHITELIST[0]
    olduren = _pencereler(monkeypatch, [
        {"class": uygulama, "title": "minecraft wiki", "pid": 4242},
        {"class": "Minecraft 1.21", "title": "Minecraft", "pid": 5151},
    ])
    r = media.close_game("minecraft")
    assert olduren == [5151], r


# ── E1 smart_home ────────────────────────────────────────────────────────────
_CIHAZ = {"192.168.1.20": {"alias": "Salon Lambası"}, "192.168.1.21": {"alias": ""}}


@pytest.mark.parametrize("ad", ["", "   "])
def test_e1_bos_ad_cihaz_secmez(ad):
    assert smart_home._find_device_ip(ad, _CIHAZ) is None


def test_e1_adsiz_cihaz_her_ada_eslesmez():
    assert smart_home._find_device_ip("mutfak", {"192.168.1.21": {"alias": ""}}) is None


def test_e1_dogru_ad_eslesir():
    assert smart_home._find_device_ip("salon", _CIHAZ) == "192.168.1.20"


# ── N1 trigger_n8n ───────────────────────────────────────────────────────────
@pytest.fixture
def sahte_n8n(monkeypatch):
    giden: list = []

    class _Istemci:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None):
            giden.append(url)
            return types.SimpleNamespace(status_code=200, text="ok",
                                         json=lambda: {"ok": True})

    monkeypatch.setenv("N8N_WEBHOOK_BASE", "http://n8n.local/webhook")
    monkeypatch.setattr(mcp_client.httpx, "AsyncClient", _Istemci)
    return giden


@pytest.mark.parametrize("ad", ["../../api/ozet", "a/../b", "x?y=1", "x#y", "", "a b"])
def test_n1_gecersiz_workflow_adi_gitmez(sahte_n8n, ad):
    r = asyncio.run(mcp_client.trigger_n8n(ad))
    assert r.startswith("Hata"), r
    assert sahte_n8n == []


def test_n1_gecerli_ad_gider(sahte_n8n):
    asyncio.run(mcp_client.trigger_n8n("/rapor-gonder"))
    assert sahte_n8n == ["http://n8n.local/webhook/rapor-gonder"]


# ── S1 monitor_process ───────────────────────────────────────────────────────
@pytest.mark.parametrize("ad", ["", "  "])
def test_s1_bos_ad_ilk_sureci_secmez(ad):
    r = system.monitor_process(ad)
    assert r.startswith("Hata"), r


# ── T1 / T2 ekip ─────────────────────────────────────────────────────────────
@pytest.fixture
def model_harcamaz(monkeypatch, test_ekibi):
    harcanan: list = []

    async def _decompose(goal):
        harcanan.append(("plan", goal))
        return [{"persona": orch.varsayilan_uzman(), "subtask": goal}]

    async def _delege(persona, subtask):
        harcanan.append(("delege", subtask))
        return "sonuç"

    monkeypatch.setattr(orch, "_decompose", _decompose)
    monkeypatch.setattr(orch, "delegate_to_persona", _delege)
    return harcanan


@pytest.mark.parametrize("hedef", ["", "   ", None])
def test_t1_bos_hedef_model_harcamaz(model_harcamaz, hedef):
    r = asyncio.run(orch.run_team(hedef))
    assert r.startswith("Hata"), r
    assert model_harcamaz == []


@pytest.mark.parametrize("alt", ["", "  "])
def test_t1_bos_alt_gorev_model_harcamaz(model_harcamaz, alt):
    r = asyncio.run(orch.companion_delegate(orch.varsayilan_uzman(), alt))
    assert r.startswith("Hata"), r
    assert model_harcamaz == []


def _meclis(monkeypatch, sonuclar):
    plan = [{"persona": p, "subtask": f"{p} işi"} for p in sonuclar]
    sentez: list = []

    async def _delege(persona, subtask):
        s = sonuclar[persona]
        if isinstance(s, Exception):
            raise s
        return s

    async def _sentez(goal, parts):
        sentez.append(parts)
        return "Her şey yolunda, ekip harika çalıştı."

    async def _onay(goal, plan):
        return True

    async def _plan(goal):
        return plan

    monkeypatch.setattr(orch, "_decompose", _plan)
    monkeypatch.setattr(orch, "_maliyet_onayi", _onay)
    monkeypatch.setattr(orch, "delegate_to_persona", _delege)
    monkeypatch.setattr(orch, "_synthesize", _sentez)
    return asyncio.run(orch._run_council_impl("hedef")), sentez


def _iki_uzman():
    from app.services.personas import PERSONAS
    adlar = [k for k in PERSONAS if k != "yuki"][:2]
    assert len(adlar) == 2
    return adlar


def test_t2_hepsi_duserse_sentez_yazilmaz(monkeypatch, test_ekibi):
    a, b = _iki_uzman()
    r, sentez = _meclis(monkeypatch, {a: RuntimeError("bağlantı yok"), b: ""})
    assert r.startswith("Hata"), r
    assert sentez == []


def test_t2_biri_calisirsa_sentez_yazilir(monkeypatch, test_ekibi):
    a, b = _iki_uzman()
    r, sentez = _meclis(monkeypatch, {a: RuntimeError("bağlantı yok"), b: "gerçek sonuç"})
    assert not r.startswith("Hata"), r
    assert len(sentez) == 1


def test_t2_hata_metni_kirpilir(monkeypatch, test_ekibi):
    a, b = _iki_uzman()
    r, _ = _meclis(monkeypatch, {a: RuntimeError("x" * 5000), b: RuntimeError("y")})
    assert len(r) < 1000


# ── U1 UAI ───────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("ad", ["delegate_task", "get_task_result", "uai_status"])
def test_u1_arkasi_olmayan_entegrasyon_semada_yok(ad):
    from app.services.tools import dispatcher
    adlar = {t["function"]["name"] for t in dispatcher.TOOLS}
    assert ad not in adlar


# ── L1 list_directory ────────────────────────────────────────────────────────
def test_l1_yeni_yazilan_dosya_hemen_listelenir(tmp_path):
    assert "boş" in files.list_directory(str(tmp_path))
    files.write_file(str(tmp_path / "yeni.txt"), "x")
    assert "yeni.txt" in files.list_directory(str(tmp_path))


# ── N2 delete_note ───────────────────────────────────────────────────────────
@pytest.fixture
def not_deposu(tmp_path, monkeypatch):
    monkeypatch.setattr(notes_tools, "_NOTES_FILE", tmp_path / "notes.json")
    return tmp_path


def test_n2_silinen_not_geri_getirilir(not_deposu):
    r = notes_tools.create_note("süt al", "alışveriş")
    not_id = [n for n in notes_tools._load()][0]["id"]
    assert "silindi" in notes_tools.delete_note(not_id).lower(), r
    assert notes_tools._load() == []
    assert "geri" in notes_tools.restore_note(not_id).lower()
    assert [n["content"] for n in notes_tools._load()] == ["süt al"]


def test_n2_olmayan_not_geri_gelmez(not_deposu):
    assert notes_tools.restore_note("yok123").startswith("Hata")
