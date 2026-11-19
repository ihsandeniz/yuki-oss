"""AJAN sekmesi — YALNIZ İZLEYİCİ: algılama gizliliği, ekip olayları.

Açık kaynak sürümde ajan oturumlarına metin/komut gönderme ucu YOK
(karar: 2026-10-17 yuki-urun-acik-kaynak § Ek karar). Gerçek ~/.claude'a ve ağa
dokunulmaz: algılama geçici dizinlerle ölçülür.
"""
from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path

import pytest


# ══════════════════════════════════════════════════════════════════════════════
#  Yardımcılar
# ══════════════════════════════════════════════════════════════════════════════

def _istemci():
    """Lifespan'SİZ istemci: açılış beceri araçlarını global TOOLS'a kaydeder ve
    sonraki dosyaların araç sınıflandırma testini kirletir (ölçüldü:
    test_companion_ekibi::test_her_arac_siniflandirilmis). Bu uçlar açılışa muhtaç değil."""
    from starlette.testclient import TestClient
    from app.main import app
    return TestClient(app)


# ══════════════════════════════════════════════════════════════════════════════
#  ① Yalnız okuma uçları
# ══════════════════════════════════════════════════════════════════════════════

def test_ajan_uclari_YALNIZ_okur():
    """Komut gönderme ucu geri gelmesin: /api/ajan altında yalnız GET var."""
    from app.main import app

    yollar = [r for r in app.routes if getattr(r, "path", "").startswith("/api/ajan")]
    assert len(yollar) >= 3
    for r in yollar:
        assert set(r.methods) <= {"GET", "HEAD"}, f"{r.path} {r.methods}"
        assert "yaz" not in r.path


def test_okuma_uclari_acik(monkeypatch, tmp_path, test_ekibi):
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "yok-claude"))
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "yok-codex"))
    c = _istemci()
    r = c.get("/api/ajan/oturumlar")
    assert r.status_code == 200
    d = r.json()
    # Kurulu değilse deste görünmez — arayüz `kurulu` alanına bakar.
    assert d["claude"] == {"kurulu": False, "oturumlar": []}
    assert d["codex"] == {"kurulu": False, "oturumlar": []}
    assert set(d) == {"claude", "codex"}       # komut alanı yok
    e = c.get("/api/ajan/ekip").json()
    assert {u["name"] for u in e["uzmanlar"]} == set(test_ekibi)   # Yuki koordinatör, uzman değil
    assert e["meclis_acik"] is True
    assert c.get("/api/ajan/rutinler").json()["acik"] is True


# ══════════════════════════════════════════════════════════════════════════════
#  ② Süreç tanıma (izleyicinin Claude kaydı)
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("ad, cmd, durum, beklenen", [
    ("claude", ["/home/x/.local/bin/claude"], "sleeping", (True, "")),
    ("claude.exe", ["C:/x/claude.exe"], "running", (True, "")),
    ("node", ["node", "/usr/lib/node_modules/@anthropic-ai/claude-code/cli.js"], "sleeping", (True, "")),
    ("vim", ["vim", "claude"], "sleeping", (False, "ajan.surec-claude-degil")),
    ("python3", ["python3", "/tmp/claude"], "sleeping", (False, "ajan.surec-claude-degil")),
    ("cat", ["cat"], "sleeping", (False, "ajan.surec-claude-degil")),
    ("claude", ["claude"], "stopped", (False, "ajan.surec-durdurulmus")),
    ("claude", ["claude"], "zombie", (False, "ajan.surec-durdurulmus")),
])
def test_claude_tanima_kurallari(monkeypatch, ad, cmd, durum, beklenen):
    """Yalnız gerçekten Claude olan süreç kabul — `vim claude` gibi dosya adı Claude değildir;
    Ctrl+Z ile durdurulmuş claude'un önünde KABUK vardır."""
    import psutil
    from app.services import ajan_oturumlari as ao

    class Sahte:
        def __init__(self, pid): pass
        def name(self): return ad
        def cmdline(self): return cmd
        def status(self): return durum
    monkeypatch.setattr(psutil, "Process", Sahte)
    assert ao.claude_sureci_mi(1234) == beklenen


def test_surec_dogrulamasi_gercek_surecle():
    """Bu test sürecinin kendisi (python) Claude DEĞİL; olmayan pid canlı değil."""
    from app.services import ajan_oturumlari as ao
    assert ao.claude_sureci_mi(os.getpid()) == (False, "ajan.surec-claude-degil")
    assert ao.claude_sureci_mi(2 ** 22 + 12345)[0] is False


# ══════════════════════════════════════════════════════════════════════════════
#  ⑤ Algılama — genel yollar, konuşma içeriği DIŞARI ÇIKMAZ
# ══════════════════════════════════════════════════════════════════════════════

GIZLI = "GIZLI-KONUSMA-ICERIGI-7f3a"


def test_claude_algilama_icerik_dondurmez(monkeypatch, tmp_path):
    from app.services import ajan_oturumlari as ao
    kok = tmp_path / "claude"
    (kok / "sessions").mkdir(parents=True)
    (kok / "projects" / "-ev-kisi-proje-z").mkdir(parents=True)
    canli_sid, biten_sid = "aaaa1111-2222-3333-4444-555566667777", "bbbb1111-2222-3333-4444-555566667777"
    (kok / "sessions" / "4242.json").write_text(json.dumps({
        "pid": 4242, "sessionId": canli_sid, "cwd": "/ev/kisi/proje-z",
        "startedAt": int((time.time() - 600) * 1000), "status": "busy"}))
    (kok / "sessions" / "9999.json").write_text(json.dumps({     # hayalet: pid ölü
        "pid": 9999, "sessionId": "cccc1111-x", "cwd": "/ev/kisi/hayalet", "status": "idle"}))
    for sid in (canli_sid, biten_sid):
        (kok / "projects" / "-ev-kisi-proje-z" / f"{sid}.jsonl").write_text(
            json.dumps({"type": "user", "cwd": "/ev/kisi/proje-z", "message": {"content": GIZLI}}) + "\n"
            + json.dumps({"type": "assistant", "message": {"stop_reason": "end_turn", "content": GIZLI}}) + "\n")
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(kok))
    monkeypatch.setattr(ao, "claude_sureci_mi", lambda pid: (pid == 4242, ""))
    monkeypatch.setattr(ao, "tmux_paneleri", lambda: [])

    d = ao.claude_oturumlari()
    ham = json.dumps(d, ensure_ascii=False)
    assert GIZLI not in ham
    assert "/ev/kisi" not in ham, "tam yol dışarı çıktı — yalnız klasör adı gitmeli"
    assert d["kurulu"] is True
    durumlar = {o["id"]: o for o in d["oturumlar"]}
    assert durumlar["aaaa1111"]["durum"] == "calisiyor"
    assert durumlar["aaaa1111"]["proje"] == "proje-z"
    assert durumlar["aaaa1111"]["gonderilebilir"] is False     # tmux yok
    assert durumlar["bbbb1111"]["durum"] == "bitti"
    assert "cccc1111" not in durumlar, "pid'i ölü hayalet oturum canlı sayıldı"


def test_codex_algilama_icerik_ve_baslik_dondurmez(monkeypatch, tmp_path):
    from app.services import ajan_oturumlari as ao
    kok = tmp_path / "codex"
    gun = kok / "sessions" / time.strftime("%Y/%m/%d")
    gun.mkdir(parents=True)
    (kok / "session_index.jsonl").write_text(json.dumps({"id": "x", "thread_name": GIZLI}) + "\n")
    meta = {"type": "session_meta", "timestamp": "2026-10-04T10:00:00Z",
            "payload": {"cwd": "/ev/kisi/kod", "base_instructions": {"text": GIZLI}}}
    (gun / "rollout-2026-10-04T10-00-00-01a0fb5c-030f-7a41-9ee3-95334611b0a1.jsonl").write_text(
        json.dumps(meta) + "\n" + json.dumps({"type": "event_msg", "payload": {
            "type": "task_complete", "last_agent_message": GIZLI}}) + "\n")
    monkeypatch.setenv("CODEX_HOME", str(kok))
    d = ao.codex_oturumlari()
    ham = json.dumps(d, ensure_ascii=False)
    assert GIZLI not in ham and "/ev/kisi" not in ham
    assert d["oturumlar"][0]["proje"] == "kod"
    assert d["oturumlar"][0]["durum"] == "bekliyor"
    assert d["oturumlar"][0]["id"] == "01a0fb5c"


def test_kurulu_degilse_bos(monkeypatch, tmp_path):
    from app.services import ajan_oturumlari as ao
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "yok"))
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "yok2"))
    assert ao.claude_oturumlari() == {"kurulu": False, "oturumlar": []}
    assert ao.codex_oturumlari() == {"kurulu": False, "oturumlar": []}


# ══════════════════════════════════════════════════════════════════════════════
#  ⑥ Ekip olayları — tek kaynak event bus, run_id ile çerçeveli
# ══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def olaylar(monkeypatch):
    from app.services.event_bus import bus
    kayit = []

    async def yayin(konu, veri):
        kayit.append((konu, dict(veri)))
    monkeypatch.setattr(bus, "publish", yayin)
    return kayit


def test_tekli_delege_cerceveli_olay_yayar(olaylar, monkeypatch, test_ekibi):
    from app.services import orchestrator

    async def sahte(key, st):
        return "sonuç"
    monkeypatch.setattr(orchestrator, "delegate_to_persona", sahte)
    assert asyncio.run(orchestrator.companion_delegate("uzman_c", "şunu araştır")) == "sonuç"
    konular = [k for k, _ in olaylar]
    assert konular == ["team_start", "companion_active", "companion_done", "team_end"]
    run_ids = {v["run_id"] for _, v in olaylar}
    assert len(run_ids) == 1
    assert olaylar[0][1]["kip"] == "tekli"
    assert olaylar[0][1]["plan"][0]["persona"] == "uzman_c"
    assert olaylar[-1][1]["durum"] == "ok"


def test_tekli_delege_hatasi_durumu_tasir(olaylar, monkeypatch, test_ekibi):
    from app.services import orchestrator

    async def patla(key, st):
        raise RuntimeError("429 rate limit")
    monkeypatch.setattr(orchestrator, "delegate_to_persona", patla)
    asyncio.run(orchestrator.companion_delegate("uzman_a", "x"))
    assert olaylar[-1] == ("team_end", {"run_id": olaylar[0][1]["run_id"], "durum": "kota"})


def test_meclis_olaylari_ayni_run_id(olaylar, monkeypatch, test_ekibi):
    from app.services import orchestrator

    async def plan(goal):
        return [{"persona": "uzman_a", "subtask": "a"}, {"persona": "uzman_b", "subtask": "b"}]

    async def onay(goal, p):
        return True

    async def is_(key, st):
        return f"{key}:{st}"

    async def sentez(goal, parts):
        return "birlesik"
    monkeypatch.setattr(orchestrator, "_decompose", plan)
    monkeypatch.setattr(orchestrator, "_maliyet_onayi", onay)
    monkeypatch.setattr(orchestrator, "delegate_to_persona", is_)
    monkeypatch.setattr(orchestrator, "_synthesize", sentez)
    assert asyncio.run(orchestrator.run_team("hedef")) == "birlesik"
    assert olaylar[0][0] == "team_start" and olaylar[-1][0] == "team_end"
    rid = olaylar[0][1]["run_id"]
    assert all(v.get("run_id") == rid for _, v in olaylar)
    assert sorted(v["persona"] for k, v in olaylar if k == "companion_done") == ["uzman_a", "uzman_b"]


def test_maliyet_onayi_yoksa_calisma_baslamaz(olaylar, monkeypatch, test_ekibi):
    from app.services import orchestrator

    async def plan(goal):
        return [{"persona": "uzman_a", "subtask": "a"}]

    async def onay(goal, p):
        return False
    monkeypatch.setattr(orchestrator, "_decompose", plan)
    monkeypatch.setattr(orchestrator, "_maliyet_onayi", onay)
    asyncio.run(orchestrator.run_team("hedef"))
    assert olaylar == []


def test_onay_olayi_TEK_kanaldan():
    """tool_approval yalnız WS'in `subscribe_all` iletimiyle gider.

    🔴 2026-10-04 ölçüldü: açılıştaki ayrı bir işçi aynı olayı ikinci kez (sunumsuz)
    yayınlıyordu → iki onay kutusu; ve kalıcı abone olduğu için `abone_var` hep True
    → "dinleyen yoksa bekleme" kapısı ölüydü (komut ucu 30 sn asılı kaldı)."""
    import re
    from pathlib import Path
    from app.services.event_bus import _ALL_TOPICS
    kaynak = (Path(__file__).resolve().parents[1] / "app" / "main.py").read_text(encoding="utf-8")
    kod = "\n".join(s.split("#", 1)[0] for s in kaynak.splitlines())
    assert "tool_approval" in _ALL_TOPICS
    assert not re.search(r"subscribe\(\s*[\"']tool_approval", kod), "ikinci onay yayıncısı geri geldi"


def test_yeni_konular_ws_aboneligine_dahil():
    """/ws/realtime `subscribe_all` ile dinler — konu listede yoksa olay ekrana hiç gelmez."""
    from app.services.event_bus import _ALL_TOPICS
    assert {"team_start", "team_end", "companion_active", "companion_done"} <= set(_ALL_TOPICS)


# ══════════════════════════════════════════════════════════════════════════════
#  ⑦ Göz tur 1 düzeltmeleri (rapor: H-ajan-lane.md § Göz tur 1)
# ══════════════════════════════════════════════════════════════════════════════

_FE = Path(__file__).resolve().parents[2] / "frontend"


def _oku(yol: str) -> str:
    return (_FE / yol).read_text(encoding="utf-8")


def test_git_dali_yalniz_ad(tmp_path):
    from app.services import ajan_oturumlari as ao
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    (repo / ".git" / "HEAD").write_text("ref: refs/heads/ozellik/x-1\n")
    (repo / "alt" / "derin").mkdir(parents=True)
    assert ao._git_dali(str(repo)) == "ozellik/x-1"
    assert ao._git_dali(str(repo / "alt" / "derin")) == "ozellik/x-1", "alt klasörden üst depo bulunmadı"
    wt = tmp_path / "wt"
    (wt).mkdir()
    gd = tmp_path / "gitdirs" / "wt"
    gd.mkdir(parents=True)
    (gd / "HEAD").write_text("ref: refs/heads/wt-dali\n")
    (wt / ".git").write_text(f"gitdir: {gd}\n")
    assert ao._git_dali(str(wt)) == "wt-dali", "worktree (.git dosyası) izlenmedi"
    (repo / ".git" / "HEAD").write_text("0123456789abcdef0123456789abcdef01234567\n")
    assert ao._git_dali(str(repo)) == "", "ayrık HEAD'de commit kimliği gösterildi"
    assert ao._git_dali(str(tmp_path / "yok")) == "" and ao._git_dali("") == ""


def test_claude_oturumu_dal_tasir_tam_yol_tasimaz(monkeypatch, tmp_path):
    from app.services import ajan_oturumlari as ao
    proje = tmp_path / "ev" / "kisi" / "proje-d"
    (proje / ".git").mkdir(parents=True)
    (proje / ".git" / "HEAD").write_text("ref: refs/heads/bl-9\n")
    kok = tmp_path / "claude"
    (kok / "sessions").mkdir(parents=True)
    (kok / "sessions" / "4242.json").write_text(json.dumps({
        "pid": 4242, "sessionId": "dddd1111-2222", "cwd": str(proje),
        "startedAt": int((time.time() - 60) * 1000), "status": "idle"}))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(kok))
    monkeypatch.setattr(ao, "claude_sureci_mi", lambda pid: (True, ""))
    monkeypatch.setattr(ao, "tmux_paneleri", lambda: [])
    d = ao.claude_oturumlari()
    o = d["oturumlar"][0]
    assert o["dal"] == "bl-9" and o["proje"] == "proje-d"
    assert str(tmp_path) not in json.dumps(d)


def test_canli_durum_MOR_degil_yesil():
    """Belge §1.2: mor "canlı hissi" için kullanılmaz; canlı = semantik yeşil, altın yok."""
    import re
    css = _oku("css/ajan.css")
    kurallar = re.findall(r"([^{}]+)\{([^}]*)\}", re.sub(r"/\*.*?\*/", "", css, flags=re.S))
    for secici, govde in kurallar:
        if "canli" in secici or "aj-olcu-ray" in secici or "aj-deste-bas svg" in secici:
            assert "--mor" not in govde, f"{secici.strip()}: canlı/ölçü/süs mor"
        assert "--altin" not in govde, f"{secici.strip()}: altın"
    assert re.search(r"\.aj-kart\.d-canli \.aj-k-durum\s*\{[^}]*--yesil", css)
    assert re.search(r"\.aj-hap\.canli\s*\{[^}]*--yesil", css)


def test_kart_metni_gosterim_kurallari():
    js = _oku("js/ajan-view.js")
    assert "replace(/ /g, '\\u00a0')" in js, "süre sayı-birim arasından kırılabilir"
    assert "no: 'DISK'" not in js and "ajan-view.sistem.no-disk" in js
    assert "'karakter.' + u.name + '.unvan'" in js, "uzman rolü sözlükten gelmiyor (EN'de Türkçe)"
    assert "(calisan ? '<span" in js and "(bekleyen ? '<span" in js, "sıfır sayaç gösteriliyor"
    assert "siraNo(" in js, "aynı klasördeki oturumlar ayırt edilmiyor"
    assert "ayrintiSatirlari(o, true)" in js, "önizleme kitabın aynısı"
    for dil in ("tr", "en"):
        sozluk = _oku(f"js/diller/{dil}.js")
        for anahtar in ("ajan-view.et.dal", "ajan-view.et.basladi", "ajan-view.yuzde", "ajan-view.sistem.esik",
                        "ajan-view.sistem.no-disk", "ajan-view.sistem.no-surec", "ajan-view.durum.normal",
                        "ajan-view.durum.yuksek", "ajan-view.et.esik", "karakter.yuki.unvan"):
            assert f"'{anahtar}'" in sozluk, f"{dil}: {anahtar} yok"
    assert "'ajan-view.sistem.no-disk': 'DİSK'" in _oku("js/diller/tr.js")


def test_onay_kutusu_orantili_font_ve_44px():
    core = _oku("js/core.js")
    f = core[core.index("function _showToolApprovalModal"):core.index("function connect()")]
    assert "font-family: JetBrains Mono" not in f
    assert f.count("min-height: var(--hedef, 44px)") == 3, "onay düğmeleri 44px altında"
    for dil, birim in (("tr", " sn'"), ("en", " s'")):
        satir = next(s for s in _oku(f"js/diller/{dil}.js").splitlines() if "'onay.sure'" in s)
        assert "\\u00a0" in satir and satir.rstrip(",").endswith(birim.replace(" ", "\\u00a0")), satir


def test_kart_acikken_menu_dugmesi_gizli():
    assert "body.aj-kitap-acik #nav-ac { visibility: hidden; }" in _oku("css/ajan.css")
    js = _oku("js/ajan-view.js")
    assert "classList.add('aj-kitap-acik')" in js and "classList.remove('aj-kitap-acik')" in js
