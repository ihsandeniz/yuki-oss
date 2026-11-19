"""Araç doğruluğu (F2b) — kişiseldeki fix(arac) doğruluk kalemlerinin yuki-oss ölçümü.

Yan etki yok: görev deposu geçici dizinde, PG yolu sahte havuz, ağ/model/hyprctl sahte.
· D2  git_status: `status --short` çıktısı baştan kırpılınca ilk satırın durum sütunu kayar,
      değişmiş (unstaged) dosya "staged" sayılırdı; `MM` hiç unstaged sayılmazdı
· D5  list_todos (PG): `ORDER BY priority DESC` metin sırası → mid, low, high; çöpteki görev listede
· D6  update_todo: `done` completed_at yazmıyordu (listede açık görünür); geçersiz değer sessizce atlanırdı
· D12 parse_when: "5 dakika önce" ileri tarihe alarm kuruyordu
· D16 browse_web: 404 ve PDF dürüst hata verir (yuki-oss'ta zaten var — kanıt testi)
· D17 create_todo: anlaşılmayan tarih sessizce düşer, görev tarihsiz eklenirdi; boş başlık eklenirdi
· D18 search_todos: "faturalar" → "fatura öde" bulunmuyordu
· D19 generate_image: boş tarif modele gidiyordu
· D21 run_skill: zorunlu parametre eksikken adımlar boş girdiyle koşuyordu
· D22 skill ikamesi: metne gömülen ekran görüntüsü base64 döküm olurdu
· D23 start_mode: pencere taşınamadıysa yine "açıldı" (başarı) deniyordu
· D31 boş not · geçersiz görev filtresi "tümü" sayılıyordu · geçersiz para birimi "veri yok"
· D32 fitness: eksi kalori / sıfır set kaydediliyordu; şablon listesi olmayan JSON kabul ediliyordu
· D33 deprem: sorgu USGS varsayılanı (30 gün) iken boş cevap "son 24 saatte" diyordu
· D34 research_stock: boş sembolle 4 arama yapılıyordu; lang="en" başlıkları Türkçe kalıyordu
· D37 skill_run: girdi HTML kodlanıyordu (`"` → `&quot;`), model bozuk metin görüyordu
· S1  açılış: Anthropic seçili ve anahtarı varken "OPENROUTER_API_KEY yok" uyarısı çıkıyordu
· C1  check_updates: kendi süresi 60+30 sn iken genel 10 sn tavanında kesiliyordu
· K1  sistem metni: ekip araçları (delegate_to_companion / run_team) için niyet örneği yoktu;
      restore_note için araç ipucu yoktu
"""
from __future__ import annotations

import asyncio
import json
import subprocess
import types

import pytest

from app.services import todo_store
from app.services.tools import todo_tools


def _kos(coro):
    return asyncio.run(coro)


# ── Görev deposu (DB yok yolu) ───────────────────────────────────────────────
@pytest.fixture
def depo(tmp_path, monkeypatch):
    monkeypatch.setattr(todo_store, "_STORE_FILE", tmp_path / "todo_store.json")
    monkeypatch.setattr(todo_store, "_LEGACY_FILE", tmp_path / "todos.json")

    async def _yok():
        return None
    monkeypatch.setattr(todo_tools, "_pool", _yok)
    return tmp_path


def _acik_basliklar():
    return [t["title"] for t in todo_store.open_tasks()]


# ── PG yolu: sahte havuz, SQL yakalanır ──────────────────────────────────────
class _Conn:
    def __init__(self, ilk_bos=True):
        self.sqller: list[tuple[str, tuple]] = []
        self.ilk_bos = ilk_bos

    async def fetch(self, sql, *a):
        self.sqller.append((sql, a))
        if len(self.sqller) == 1 and self.ilk_bos:
            return []
        return [{"id": "t1", "title": "fatura öde", "priority": "mid", "due_date": None,
                 "completed_at": None, "list_name": "gelen kutusu"}]

    async def fetchrow(self, sql, *a):
        self.sqller.append((sql, a))
        if "todo_lists" in sql:
            return None
        return {"id": "t1", "title": "x", "priority": "mid", "due_date": None}

    async def fetchval(self, sql, *a):
        self.sqller.append((sql, a))
        return 0


class _Havuz:
    def __init__(self, conn):
        self.conn = conn

    def acquire(self):
        conn = self.conn

        class _C:
            async def __aenter__(self):
                return conn

            async def __aexit__(self, *e):
                return False
        return _C()


@pytest.fixture
def pg(monkeypatch):
    conn = _Conn()

    async def _h():
        return _Havuz(conn)
    monkeypatch.setattr(todo_tools, "_pool", _h)
    return conn


# ── D2 git_status ────────────────────────────────────────────────────────────
def _git(d, *a):
    subprocess.run(["git", "-C", str(d), *a], check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path):
    d = tmp_path / "r"
    d.mkdir()
    _git(d, "init", "-q")
    _git(d, "config", "user.email", "t@t")
    _git(d, "config", "user.name", "t")
    (d / "a.txt").write_text("1")
    (d / "b.txt").write_text("1")
    _git(d, "add", ".")
    _git(d, "commit", "-qm", "ilk")
    return d


def test_d2_degismis_dosya_staged_sayilmaz(repo):
    from app.services.tools.data import git_status
    (repo / "a.txt").write_text("2")
    out = git_status(str(repo))
    assert "Staged" not in out, out
    assert "Unstaged (1): a.txt" in out, out


def test_d2_MM_hem_staged_hem_unstaged(repo):
    from app.services.tools.data import git_status
    (repo / "a.txt").write_text("2")
    _git(repo, "add", "a.txt")
    (repo / "a.txt").write_text("3")
    out = git_status(str(repo))
    assert "Staged (1): a.txt" in out, out
    assert "Unstaged (1): a.txt" in out, out


# ── D5 öncelik sırası + çöp (PG) ─────────────────────────────────────────────
@pytest.mark.parametrize("filtre", ["today", "week", "overdue", "all"])
def test_d5_pg_liste_oncelik_metin_sirasi_degil_ve_copu_gostermez(pg, filtre):
    _kos(todo_tools.list_todos(filtre))
    sql = pg.sqller[-1][0]
    assert "priority DESC" not in sql, sql
    assert "CASE t.priority WHEN 'high'" in sql, sql
    assert "deleted_at IS NULL" in sql, sql


# ── D6 update_todo ───────────────────────────────────────────────────────────
def test_d6_done_tamamlandi_sayilir_depo(depo):
    tid = todo_store.create_task(todo_store.INBOX_ID, title="kira")["id"]
    out = _kos(todo_tools.update_todo(tid, status="done"))
    assert "güncellendi" in out, out
    assert todo_store.get_task(tid)["completed_at"], "done ama completed_at boş → listede açık görünür"
    assert "kira" not in _acik_basliklar()


def test_d6_done_disi_durum_tamamlanmayi_geri_alir_depo(depo):
    tid = todo_store.create_task(todo_store.INBOX_ID, title="kira")["id"]
    _kos(todo_tools.update_todo(tid, status="done"))
    _kos(todo_tools.update_todo(tid, status="todo"))
    assert not todo_store.get_task(tid)["completed_at"]


def test_d6_done_pg_completed_at_yazar(pg):
    _kos(todo_tools.update_todo("t1", status="done"))
    sql = pg.sqller[-1][0]
    assert "completed_at = COALESCE(completed_at, NOW())" in sql, sql


@pytest.mark.parametrize("alan", [{"priority": "acil"}, {"status": "bitti"}])
def test_d6_gecersiz_deger_reddedilir(depo, alan):
    tid = todo_store.create_task(todo_store.INBOX_ID, title="kira")["id"]
    out = _kos(todo_tools.update_todo(tid, title="yeni", **alan))
    assert out.startswith("Hata"), out
    assert todo_store.get_task(tid)["title"] == "kira", "geçersiz alan atlandı, kalanı yazıldı"


# ── D17 create_todo ──────────────────────────────────────────────────────────
@pytest.mark.parametrize("alan", [{"due_date": "yarın"}, {"reminder_at": "akşam"}])
def test_d17_anlasilmayan_tarih_gorevi_eklemez_depo(depo, alan):
    out = _kos(todo_tools.create_todo("kira", **alan))
    assert out.startswith("Hata"), out
    assert _acik_basliklar() == []


@pytest.mark.parametrize("alan", [{"due_date": "yarın"}, {"reminder_at": "akşam"}])
def test_d17_anlasilmayan_tarih_gorevi_eklemez_pg(pg, alan):
    out = _kos(todo_tools.create_todo("kira", **alan))
    assert out.startswith("Hata"), out
    assert not any("INSERT" in s for s, _ in pg.sqller)


def test_d17_bos_baslik_eklenmez(depo):
    out = _kos(todo_tools.create_todo("   "))
    assert out.startswith("Hata"), out
    assert _acik_basliklar() == []


# ── D18 Türkçe ekli arama ────────────────────────────────────────────────────
def test_d18_ekli_sozcuk_depoda_bulunur(depo):
    todo_store.create_task(todo_store.INBOX_ID, title="fatura öde")
    out = _kos(todo_tools.search_todos("faturalar"))
    assert "fatura öde" in out, out


def test_d18_pg_tam_metin_bossa_kok_aramasi(pg):
    out = _kos(todo_tools.search_todos("faturaları"))
    assert len(pg.sqller) == 2, "yedek arama yapılmadı"
    assert pg.sqller[1][1][0] == ["fatura"], pg.sqller[1][1]
    assert "fatura öde" in out


def test_d18_kok_cok_kisaysa_yedek_yok():
    assert todo_tools._kaba_kokler("da") == []
    assert todo_tools._kaba_kokler("İzmirde") == ["izmir"]


# ── D31 filtre / boş not / para birimi ───────────────────────────────────────
def test_d31_gecersiz_filtre_reddedilir(depo):
    out = _kos(todo_tools.list_todos("acil olanlar"))
    assert out.startswith("Hata"), out


def test_d31_turkce_filtre_calisir(depo):
    from datetime import date
    todo_store.create_task(todo_store.INBOX_ID, title="bugünkü", due_date=date.today().isoformat())
    todo_store.create_task(todo_store.INBOX_ID, title="tarihsiz")
    out = _kos(todo_tools.list_todos("bugün"))
    assert "bugünkü" in out and "tarihsiz" not in out, out


def test_d31_bos_not_kaydedilmez(tmp_path, monkeypatch):
    from app.services.tools import notes_tools
    monkeypatch.setattr(notes_tools, "_NOTES_FILE", tmp_path / "notes.json")
    out = notes_tools.create_note("   ")
    assert out.startswith("Hata"), out
    assert notes_tools._load() == []


class _Yanit:
    def __init__(self, veri):
        self._v = veri

    def raise_for_status(self):
        pass

    def json(self):
        return self._v


def _sahte_httpx(monkeypatch, veri, yakala=None):
    import httpx

    class _Istemci:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *e):
            return False

        async def get(self, url, params=None, **k):
            if yakala is not None:
                yakala.append(params)
            return _Yanit(veri)
    monkeypatch.setattr(httpx, "AsyncClient", _Istemci)


def test_d31_gecersiz_para_birimi_soylenir(monkeypatch):
    from app.services.tools.data import get_crypto_price
    _sahte_httpx(monkeypatch, {"bitcoin": {}, "ethereum": {}})
    out = _kos(get_crypto_price("bitcoin,ethereum", "xyz"))
    assert out.startswith("Hata") and "XYZ" in out, out


def test_d31_gecerli_para_birimi_bozulmaz(monkeypatch):
    from app.services.tools.data import get_crypto_price
    _sahte_httpx(monkeypatch, {"bitcoin": {"usd": 50000.0}, "ethereum": {}})
    out = _kos(get_crypto_price("bitcoin,ethereum", "usd"))
    assert "50,000.00 USD" in out and "ethereum: veri yok" in out, out


# ── D33 deprem ───────────────────────────────────────────────────────────────
def test_d33_sure_iddiasi_sorguya_bagli(monkeypatch):
    from app.services.tools.data import get_earthquake_alerts
    yakala: list = []
    _sahte_httpx(monkeypatch, {"features": []}, yakala)
    out = _kos(get_earthquake_alerts(min_magnitude=6.0))
    assert "starttime" in yakala[0], yakala
    assert "24 saat" not in out and "30 gün" in out, out


# ── D12 parse_when ───────────────────────────────────────────────────────────
@pytest.mark.parametrize("ifade", ["5 dakika önce", "2 saat önce"])
def test_d12_gecmis_ifade_alarm_olmaz(ifade):
    from app.services.scheduler import parse_when
    assert parse_when(ifade) is None


def test_d12_ileri_ifade_bozulmaz():
    from datetime import datetime
    from app.services.scheduler import parse_when
    assert parse_when("5 dakika sonra") > datetime.now()


# ── D16 browse_web (zaten var) ───────────────────────────────────────────────
def _sahte_get(monkeypatch, durum, tip, metin=""):
    from app.services.tools import network
    network._browse_cache.clear()
    yanit = types.SimpleNamespace(status_code=durum, headers={"content-type": tip}, text=metin,
                                  url="https://ornek.test/x")

    async def _g(client, url):
        return yanit, None
    monkeypatch.setattr(network, "_guvenli_get", _g)
    return network


def test_d16_404_hata_sayfasi_icerik_sanilmaz(monkeypatch):
    network = _sahte_get(monkeypatch, 404, "text/html", "<p>Not Found</p>" * 20)
    out = _kos(network.browse_web("https://ornek.test/x"))
    assert out.startswith("Hata") and "404" in out, out
    assert not network._browse_cache


def test_d16_pdf_dürüst_hata(monkeypatch):
    network = _sahte_get(monkeypatch, 200, "application/pdf")
    out = _kos(network.browse_web("https://ornek.test/x.pdf"))
    assert out.startswith("Hata") and "pdf" in out.lower(), out


# ── D19 generate_image ───────────────────────────────────────────────────────
def test_d19_bos_tarif_modele_gitmez(monkeypatch):
    import openai
    from app.services.tools import vision_extra

    def _patla(*a, **k):
        raise AssertionError("boş tarifle istemci kuruldu")
    monkeypatch.setattr(openai, "AsyncOpenAI", _patla)
    out = _kos(vision_extra.generate_image("  "))
    assert out.startswith("Hata"), out


# ── D21 / D22 skill kayıt defteri ────────────────────────────────────────────
@pytest.fixture
def sahte_skill(monkeypatch):
    from app.services import skill_registry as sr
    kosulan: list = []
    sk = {"name": "dene", "parameters": {"konu": {"type": "string", "required": True}},
          "steps": [{"tool": "web_search", "args": {"query": "{{konu}}"}}]}
    monkeypatch.setitem(sr._SKILLS, "dene", sk)

    async def _arac(name, args):
        kosulan.append((name, args))
        return "sonuç"
    monkeypatch.setattr("app.services.tools.call_tool", _arac)
    return sr, kosulan


def test_d21_zorunlu_parametre_eksikse_adim_kosmaz(sahte_skill):
    sr, kosulan = sahte_skill
    out = _kos(sr.run_skill("skill__dene", {"konu": " "}))
    assert out.startswith("Hata") and "konu" in out, out
    assert kosulan == []


def test_d21_parametre_varsa_kosar(sahte_skill):
    sr, kosulan = sahte_skill
    _kos(sr.run_skill("skill__dene", {"konu": "deprem"}))
    assert kosulan == [("web_search", {"query": "deprem"})]


def test_d22_metne_gomulen_goruntu_dokulmez():
    from app.services.skill_registry import _subst
    cikti = ["SCREENSHOT_DATA:" + "A" * 500]
    assert _subst("Özet: {{steps.0}}", {}, cikti) == "Özet: [ekran görüntüsü]"
    assert _subst("{{steps.0}}", {}, cikti) == cikti[0], "tek başına kalan görüntü modele gitmeli"


# ── D37 skill_run girdisi ────────────────────────────────────────────────────
def test_d37_skill_girdisi_bozulmaz(tmp_path, monkeypatch):
    from app.services.tools import skills
    (tmp_path / "ozet.md").write_text("Şunu özetle: $ARGUMENTS", encoding="utf-8")
    monkeypatch.setattr(skills, "SKILLS_DIR", tmp_path)
    out = skills.skill_run("ozet", 'a < b & "c"')
    assert 'a < b & "c"' in out, out


# ── D23 start_mode penceresi ─────────────────────────────────────────────────
def test_d23_tasinamayan_pencere_basari_sayilmaz(monkeypatch):
    from app.services.tools import modes
    monkeypatch.setattr(modes, "_resolve_app", lambda a: "kitty")
    monkeypatch.setattr(modes, "detect_env", lambda: {"features": {"workspace_move": True}})
    monkeypatch.setattr(modes, "_safe_env", lambda: {})
    monkeypatch.setattr(modes, "_get_window_addrs", lambda env: set())
    monkeypatch.setattr(modes, "_popen_detached", lambda *a, **k: None)
    monkeypatch.setattr(modes, "_move_new_win", lambda *a, **k: False)
    ok, mesaj = modes._open_app("kitty", "2")
    assert ok is False and "doğrulanmadı" in mesaj, (ok, mesaj)
    monkeypatch.setattr(modes, "_move_new_win", lambda *a, **k: True)
    assert modes._open_app("kitty", "2") == (True, "kitty→2")


# ── D32 fitness ──────────────────────────────────────────────────────────────
@pytest.fixture
def fit(monkeypatch):
    from app.services.tools import fitness_tools

    cagrildi: list = []

    async def _kaydet():
        cagrildi.append(1)
        raise RuntimeError("depo")
    monkeypatch.setattr(fitness_tools, "_pool", _kaydet)
    fitness_tools._cagrildi = cagrildi
    return fitness_tools


@pytest.mark.parametrize("cagri", [
    lambda f: f.log_meal("elma", -50),
    lambda f: f.log_meal("elma", 50, protein=-1),
    lambda f: f.log_workout_exercise("squat", sets=0),
    lambda f: f.log_workout_exercise("squat", reps=-3),
    lambda f: f.update_fitness_config(cal_goal=-100),
    lambda f: f.save_fitness_template("A", '{"name": "x"}'),
    lambda f: f.save_fitness_template("A", '["x"]'),
])
def test_d32_gecersiz_fitness_girdisi(fit, cagri):
    out = _kos(cagri(fit))
    assert out.startswith("Hata"), out
    assert fit._cagrildi == [], f"geçersiz girdiyle depoya gidildi: {out}"


# ── D34 research_stock ───────────────────────────────────────────────────────
def test_d34_bos_sembol_arama_yapmaz(monkeypatch):
    from app.services.tools import finance_research as fr

    async def _patla(*a, **k):
        raise AssertionError("boş sembolle arama")
    monkeypatch.setattr(fr, "_web_search", _patla)
    monkeypatch.setattr(fr, "_fetch_crypto_price", _patla)
    out = _kos(fr.research_stock("  "))
    assert out.startswith("Hata"), out


def test_d34_ingilizce_rapor_basliklari(monkeypatch):
    from app.services.tools import finance_research as fr

    async def _veri(*a, **k):
        return "veri"
    monkeypatch.setattr(fr, "_web_search", _veri)
    en = _kos(fr.research_stock("AAPL", lang="en"))
    assert "FINANCIAL RESEARCH REPORT (STOCK)" in en and "ROL 1" not in en, en
    tr = _kos(fr.research_stock("AAPL"))
    assert "FİNANSAL ARAŞTIRMA RAPORU (HİSSE)" in tr, tr


# ── S1 açılış anahtar uyarısı ────────────────────────────────────────────────
@pytest.fixture
def sv(monkeypatch):
    from app.services import startup_validator as sv
    from app.services import llm_providers as lp
    monkeypatch.setattr(sv, "OPENROUTER_API_KEY", "")
    monkeypatch.setattr(sv, "USE_LOCAL_LLM", False)
    return sv, lp


def _anahtar_uyarisi(uyarilar):
    return [u for u in uyarilar if "anahtar" in u.lower() or "key" in u.lower()]


def test_s1_secili_saglayicinin_anahtari_varsa_openrouter_uyarisi_yok(sv, monkeypatch):
    sv, lp = sv
    monkeypatch.setattr("app.config.LLM_PROVIDER", "anthropic")
    monkeypatch.setitem(lp._anahtarlar, "anthropic", "sk-ant-deneme")
    assert _anahtar_uyarisi(sv.validate_startup()) == []


def test_s1_secili_saglayicinin_anahtari_yoksa_uyarir(sv, monkeypatch):
    sv, lp = sv
    monkeypatch.setattr("app.config.LLM_PROVIDER", "anthropic")
    monkeypatch.delitem(lp._anahtarlar, "anthropic", raising=False)
    assert _anahtar_uyarisi(sv.validate_startup()), "anahtarsız seçili sağlayıcı sessiz kaldı"


# ── C1 check_updates süresi ──────────────────────────────────────────────────
def test_c1_check_updates_genel_tavanda_kesilmez(monkeypatch):
    from app.services import runner

    monkeypatch.setattr(runner, "TOOL_TIMEOUT", 0.05)

    class _Bus:
        async def publish(self, *a, **k):
            pass

    async def _yavas(name, args):
        await asyncio.sleep(0.2)
        return "güncel"

    r = runner.LLMRunner(None, "m", [], cancel_token=runner.CancellationToken())

    def _tc(ad):
        return types.SimpleNamespace(id="1", function=types.SimpleNamespace(name=ad, arguments="{}"))

    sonuc = _kos(r._execute_tools([_tc("check_updates")], _yavas, _Bus()))
    assert sonuc[0][2] == "güncel", sonuc
    sonuc = _kos(r._execute_tools([_tc("list_packages")], _yavas, _Bus()))
    assert "yanıt vermedi" in sonuc[0][2], "genel tavan bozuldu"


# ── K1 sistem metni + araç ipucu ─────────────────────────────────────────────
def test_k1_ekip_araclari_icin_niyet_ornegi(monkeypatch):
    from app import config
    import app.services.tools as tools
    acik = [{"function": {"name": n}} for n in ("delegate_to_companion", "run_team", "web_search")]
    monkeypatch.setattr(tools, "get_active_tools", lambda: acik)
    bolum, _ = config._tool_inventory()
    assert "`delegate_to_companion`" in bolum and "`run_team`" in bolum, bolum


def test_k1_ekip_araci_kapaliysa_vaat_yok(monkeypatch):
    from app import config
    import app.services.tools as tools
    monkeypatch.setattr(tools, "get_active_tools", lambda: [{"function": {"name": "web_search"}}])
    bolum, _ = config._tool_inventory()
    assert "`run_team`" not in bolum and "`delegate_to_companion`" not in bolum


def test_k1_restore_note_arac_ipucu():
    from pathlib import Path
    yol = Path(__file__).resolve().parents[1] / "app" / "services" / "arac-yonlendirme.json"
    kurallar = json.loads(yol.read_text(encoding="utf-8"))
    kurallar = kurallar.get("kurallar", kurallar) if isinstance(kurallar, dict) else kurallar
    assert any("restore_note" in (k.get("araclar") or []) for k in kurallar)
