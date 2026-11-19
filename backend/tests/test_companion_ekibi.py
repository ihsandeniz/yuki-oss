"""Companion ekibi (R5) — kademe kapısı · alt-ajan yetkisi · maliyet kapısı.

geliştiricinin kuralı: *"pro ve ultrada yuki ana olarak sayılacak, diğer karakterler
alt ajan; yuki hepsi ile konuşabilir ama diğer karakterler yuki ve kendileri
dışında başka bir karakterle konuşamaz."*

Mimarinin çekirdeği 2026-08-11'de ölçüldüğünde ZATEN yazılıydı (`orchestrator.py`).
Bu turda eklenen üç şey ve onların kapıları:

  FAZ 1  kademe bağlantısı  → `delegate_to_companion` ∈ p4 (Pro) · `run_team` ∈ p7 (Ultra)
  FAZ 2  maliyet kapısı     → onay + eşzamanlılık sınırı + kısmi sonuç (429)
  FAZ 4  D8 salt-okur       → alt ajan yazamaz/çalıştıramaz/kullanıcıya seslenemez

🔑 Bu dosyanın varlık sebebi iki eski ders:
  · *"kapı VAR" ≠ "arayüz kapıya bakıyor"* (karakter kilidi, 08-09)
  · *"araç listede yok" ≠ "çağrılamaz"* — model olmayan bir aracı uydurup çağırabilir,
    o yüzden LLM'e sunulan liste ve `call_tool` guard'ı AYRI AYRI ölçülür.
"""

import asyncio

import pytest

# Ürün kaydında Yuki dışında persona yok (2026-11-14); ekip mekaniği geçici test
# uzmanlarıyla ölçülür (conftest `test_ekibi`). Uzmansız davranış: test_tek_karakter.py
pytestmark = pytest.mark.usefixtures("test_ekibi")

from app.services import orchestrator as orch
from app.services import yetki


# ══════════════════════════════════════════════════════════════════════
# FAZ 4 / D8 — alt ajanlar SALT OKUR
# ══════════════════════════════════════════════════════════════════════
def test_her_arac_siniflandirilmis():
    """🔴 Bu testin asıl işi: YARIN eklenen aracı yakalamak.

    Worker toolset'i bir İZİN listesidir (fail-closed): sınıflandırılmamış yeni
    bir araç worker'a zaten gitmez. Ama sınıflandırmayı unutmak da sessiz kalırsa
    okunabilir bir araç boşuna kapalı kalır. Bu yüzden tamlık şart koşuluyor.
    """
    from app.services.tools.dispatcher import TOOLS
    registry = {t["function"]["name"] for t in TOOLS}
    sinifli = orch.WORKER_READONLY_TOOLS | orch.WORKER_MUTATING_TOOLS
    dev_only: set[str] = set()
    assert not (registry - sinifli - dev_only), (
        f"Sınıflandırılmamış araç: {sorted(registry - sinifli - dev_only)} — "
        "worker'a açılacak mı (okur) yoksa kapalı mı (yazar), karara bağla."
    )
    assert not (sinifli - registry), f"Registry'de olmayan ad: {sorted(sinifli - registry)}"
    assert not (orch.WORKER_READONLY_TOOLS & orch.WORKER_MUTATING_TOOLS)


@pytest.mark.parametrize("arac", [
    "write_file", "append_file",
    "send_notification", "set_clipboard", "create_todo", "wiki_write",
    "memory_reflect", "take_screenshot", "generate_image", "skill_run",
])
def test_yan_etkili_arac_worker_listesinde_yok(arac):
    """D8: alt ajan yazamaz/çalıştıramaz/kullanıcıya seslenemez."""
    assert arac not in orch.WORKER_READONLY_TOOLS


def test_alt_ajan_baska_alt_ajanla_konusamaz():
    """geliştiricinin asıl kuralı — yıldız topolojisi, uçlar arası kenar yok."""
    for arac in ("delegate_to_companion", "run_team", "delegate_task", "switch_character"):
        assert arac not in orch.WORKER_READONLY_TOOLS


def test_worker_toolset_yetkiye_saygi_gosterir(monkeypatch):
    """Alt ajan, yetkinin kapattığı bir aracı kullanamaz (orchestrator → yetki.tool_allowed).

    Kademe kalktı; kapı mekanizması duruyor — bir kısıt alt ajan
    üzerinden dolaşılamamalı.
    """
    monkeypatch.setattr(yetki, "tool_allowed", lambda ad: ad != "web_search")
    adlar = {t["function"]["name"] for t in orch._worker_tools()}
    assert "web_search" not in adlar, "yetkinin kapattığı araç alt ajana sızdı"
    assert adlar, "alt ajana hiç araç verilmemiş"
    assert not (adlar - orch.WORKER_READONLY_TOOLS)


def test_worker_promptu_salt_okunur_oldugunu_soyler():
    """Model kısıtı BİLMELİ — yoksa yapamayacağı işi denemeye çalışır ve
    kullanıcıya "yaptım" der (araç reddedildiğini modele söylemez sanmak tuzağı)."""
    p = orch._worker_system_prompt("uzman_a").lower()
    assert "salt okunur" in p


def test_recursion_guard_derinlik_1():
    assert orch.MAX_DEPTH == 1

    async def _dene():
        tok = orch._depth.set(1)
        try:
            return await orch.run_team("x"), await orch.companion_delegate("uzman_a", "x")
        finally:
            orch._depth.reset(tok)

    meclis, delege = asyncio.run(_dene())
    assert "engellendi" in meclis and "engellendi" in delege


# ══════════════════════════════════════════════════════════════════════
# FAZ 2 — maliyet kapısı
# ══════════════════════════════════════════════════════════════════════
def test_maliyet_tahmini_gercek_formulu_veriyor():
    """1 (plan) + görev×adım (uzmanlar) + 1 (sentez). Tek görevde sentez yok."""
    t = orch.maliyet_tahmini(4)
    assert t["en_az"] == 1 + 4 + 1
    assert t["en_cok"] == 1 + 4 * orch._ayar("WORKER_MAX_STEPS", orch.WORKER_MAX_STEPS) + 1
    tek = orch.maliyet_tahmini(1)
    assert tek["en_az"] == 2, "tek görevli planda sentez yapılmaz, sayılmamalı"


def test_meclis_kotanin_buyuk_kismini_yiyor_uyarisi_gercek():
    """Bu özelliğin maliyet kapısı olmadan yayınlanamamasının SEBEBİ ölçülü kalsın.

    Kredisiz OpenRouter: günde 50. Varsayılan ayarlarla en kötü meclis bunun
    üçte birinden fazlasını yer → kapı bir cila değil ön koşul.
    """
    assert orch.maliyet_tahmini(4)["en_cok"] > 50 / 3


def test_esszamanlilik_sinirli():
    """Sınırsız `gather` DAKİKALIK sınırı (20) tek çağrıda aşabiliyordu."""
    assert 1 <= orch.COUNCIL_CONCURRENCY < orch.COUNCIL_MAX_TASKS


def test_kota_hatasi_taninir():
    """Kod değil METİN söyler — sağlayıcılar 429'u farklı biçimde bildirir."""
    assert orch._kota_hatasi_mi(Exception("Error code: 429 - rate limit exceeded"))
    assert orch._kota_hatasi_mi(Exception("free-models-per-day quota reached"))
    assert not orch._kota_hatasi_mi(Exception("connection reset by peer"))


def test_onay_dinleyen_yokken_uygulanmaz():
    """Kimsenin cevaplayamayacağı onay kapı değil, 30 sn'lik sessiz kilittir.

    Arka planda koşan bir rutin (`routines.py` → run_team) WS istemcisi yokken
    onay penceresi açarsa 30 sn bekler ve REDDEDİLMİŞ sayılır.
    """
    from app.services.event_bus import bus
    assert not bus.abone_var("tool_approval")
    assert asyncio.run(orch._maliyet_onayi("hedef", [{"persona": "uzman_a",
                                                      "label": "Uzman A",
                                                      "subtask": "ara"}]))


def test_onay_dinleyen_varken_insan_dilinde_soruluyor():
    """Maliyet onayı bir satış yüzeyi — ham `{"goal": ...}` JSON'u değil."""
    from app.services.event_bus import bus
    from app.services.tools import approval_gate

    q = bus.subscribe("tool_approval")
    yakalanan: dict = {}

    async def _ak():
        async def _onayla():
            ev = await asyncio.wait_for(q.get(), timeout=2)
            yakalanan.update(ev)
            approval_gate.resolve_approval(ev["approval_id"], True)

        gorev = asyncio.create_task(_onayla())
        ok = await orch._maliyet_onayi("rapor hazırla", [
            {"persona": "uzman_a", "label": "Uzman A", "subtask": "kaynakları tara"},
            {"persona": "uzman_b", "label": "Uzman B", "subtask": "tabloyu çıkar"},
        ])
        await gorev
        return ok

    try:
        assert asyncio.run(_ak()) is True
    finally:
        bus.unsubscribe("tool_approval", q)

    sunum = yakalanan.get("sunum")
    assert sunum, "onay kutusu ham JSON ile soruluyor — sunum katmanı yok"
    assert "model isteği" in sunum["mesaj"]
    assert any("Uzman A" in s for s in sunum["satirlar"])


def test_ayar_canli_okunuyor():
    """Kullanıcı 4/4'ü 2/2'ye çekince yeniden başlatma gerekmemeli."""
    from app import config as cfg
    onceki = getattr(cfg, "COUNCIL_MAX_TASKS", 4)
    try:
        cfg.COUNCIL_MAX_TASKS = 2
        assert orch._ayar("COUNCIL_MAX_TASKS", orch.COUNCIL_MAX_TASKS) == 2
    finally:
        cfg.COUNCIL_MAX_TASKS = onceki


def test_bozuk_ayar_varsayilana_duser():
    """0/negatif bir ayar meclisi sessizce boşa düşürmemeli."""
    from app import config as cfg
    onceki = getattr(cfg, "COUNCIL_MAX_TASKS", 4)
    try:
        cfg.COUNCIL_MAX_TASKS = 0
        assert orch._ayar("COUNCIL_MAX_TASKS", 4) == 4
    finally:
        cfg.COUNCIL_MAX_TASKS = onceki


# ══════════════════════════════════════════════════════════════════════
# FAZ 3 — arayüz kancası (olay akışı)
# ══════════════════════════════════════════════════════════════════════
def test_companion_olaylari_ws_e_iletiliyor():
    """Olay yayınlansa da `_ALL_TOPICS`te yoksa WebSocket'e HİÇ ulaşmaz.

    `subscribe_all` yalnız bu listedeki topic'lere abone olur — yeni bir olay
    eklerken buraya yazmayı unutmak, olayı sessizce yok eder.
    """
    from app.services.event_bus import _ALL_TOPICS
    for olay in ("companion_active", "companion_done", "companion_result"):
        assert olay in _ALL_TOPICS


# ══════════════════════════════════════════════════════════════════════
# GERÇEK MECLİS AKIŞI — LLM'siz, ama gerçek `_run_council_impl` koşuyor
# ══════════════════════════════════════════════════════════════════════
# 🔑 Neden böyle: yukarıdaki testler parçaları ölçüyor. Burada plan→delege→
# sentez zincirinin KENDİSİ koşuyor; yalnız iki dış uç (model çağrısı) taklit
# ediliyor. Olay adları/alanları, eşzamanlılık sınırı ve kısmi sonuç davranışı
# ancak burada görünür — parça testleri bunları kaçırırdı.
def _meclisi_kosur(monkeypatch, plan, sonuclar):
    """`_decompose` + `delegate_to_persona` taklit edilir, gerisi GERÇEK kod."""
    olaylar: list[dict] = []
    esZamanli, tepe = [0], [0]

    async def _sahte_decompose(goal):
        return plan

    async def _sahte_delege(persona, subtask):
        esZamanli[0] += 1
        tepe[0] = max(tepe[0], esZamanli[0])
        try:
            await asyncio.sleep(0.02)
            sonuc = sonuclar[persona]
            if isinstance(sonuc, Exception):
                raise sonuc
            return sonuc
        finally:
            esZamanli[0] -= 1

    async def _sahte_sentez(goal, parts):
        return " | ".join(f"{p['label']}:{p['result']}" for p in parts)

    monkeypatch.setattr(orch, "_decompose", _sahte_decompose)
    monkeypatch.setattr(orch, "delegate_to_persona", _sahte_delege)
    monkeypatch.setattr(orch, "_synthesize", _sahte_sentez)

    from app.services.event_bus import bus
    gercek_publish = bus.publish

    async def _kaydet(topic, data):
        olaylar.append({"type": topic, **data})
        await gercek_publish(topic, data)

    monkeypatch.setattr(bus, "publish", _kaydet)
    cikti = asyncio.run(orch._run_council_impl("hedef"))
    return cikti, olaylar, tepe[0]


def test_gercek_akista_her_uzman_icin_uc_olay_yayinlaniyor(monkeypatch):
    plan = [{"persona": "uzman_a", "subtask": "ara"}, {"persona": "uzman_b", "subtask": "yaz"}]
    _, olaylar, _ = _meclisi_kosur(monkeypatch, plan, {"uzman_a": "A", "uzman_b": "B"})
    for tip in ("companion_active", "companion_done", "companion_result"):
        assert len([o for o in olaylar if o["type"] == tip]) == 2, f"{tip} eksik"


def test_yayinlanan_alanlar_arayuzun_okuduklariyla_ayni(monkeypatch):
    """🔴 Yayıncı ile tüketici arasındaki alan adı sözleşmesi.

    Backend `label` yayınlarken frontend `name` okusaydı hiçbir test kırmızı
    yanmaz, ekranda sessizce boş chip çıkardı. Alan adları burada YAZILI.
    """
    plan = [{"persona": "uzman_a", "subtask": "ara"}]
    _, olaylar, _ = _meclisi_kosur(monkeypatch, plan, {"uzman_a": "A"})
    sonuc = next(o for o in olaylar if o["type"] == "companion_result")
    assert {"persona", "label", "subtask", "result", "durum"} <= set(sonuc)
    aktif = next(o for o in olaylar if o["type"] == "companion_active")
    assert {"persona", "label", "subtask"} <= set(aktif)
    # Frontend bu adları gerçekten okuyor mu (kopyala-yapıştır ayrışmasın)
    c = (Path(__file__).resolve().parents[2] / "frontend" / "js" / "core.js").read_text(encoding="utf-8")
    for alan in ("d.persona", "d.label", "d.subtask", "d.result", "d.durum"):
        assert alan in c, f"arayüz {alan} alanını okumuyor"


def test_esszamanlilik_gercekten_sinirlaniyor(monkeypatch):
    """Sınır bir SABİT değil, çalışma zamanında ölçülen bir davranış olmalı."""
    plan = [{"persona": p, "subtask": "x"} for p in ("uzman_a", "uzman_c", "uzman_d", "uzman_b")]
    _, _, tepe = _meclisi_kosur(monkeypatch, plan, dict.fromkeys(
        ("uzman_a", "uzman_c", "uzman_d", "uzman_b"), "ok"))
    assert tepe <= orch.COUNCIL_CONCURRENCY, (
        f"aynı anda {tepe} uzman koştu, sınır {orch.COUNCIL_CONCURRENCY} — "
        "dakikada-20 sınırı tek çağrıda aşılabilir"
    )


def test_bir_uzman_kotaya_carpsa_meclis_dusmuyor(monkeypatch):
    """Kısmi sonuç sıfır sonuçtan iyidir — ve kullanıcı NEDEN eksik olduğunu görür."""
    plan = [{"persona": "uzman_a", "subtask": "ara"}, {"persona": "uzman_b", "subtask": "yaz"}]
    cikti, olaylar, _ = _meclisi_kosur(monkeypatch, plan, {
        "uzman_a": Exception("Error code: 429 - free-models-per-day quota"),
        "uzman_b": "tablo hazır",
    })
    assert "tablo hazır" in cikti, "sağlam uzmanın sonucu kayboldu"
    assert "kota" in cikti.lower(), "kullanıcıya sebep söylenmiyor"
    durumlar = {o["persona"]: o["durum"] for o in olaylar if o["type"] == "companion_result"}
    assert durumlar["uzman_a"] == "kota" and durumlar["uzman_b"] == "ok"


def test_onay_reddedilirse_hicbir_uzman_kosmuyor(monkeypatch):
    """Maliyet kapısı gerçekten KAPI mı — yoksa yalnız bir bildirim mi?"""
    kosan = []

    async def _sahte_decompose(goal):
        return [{"persona": "uzman_a", "subtask": "ara"}]

    async def _sahte_delege(persona, subtask):
        kosan.append(persona)
        return "olmamalı"

    async def _hayir(goal, plan):
        return False

    monkeypatch.setattr(orch, "_decompose", _sahte_decompose)
    monkeypatch.setattr(orch, "delegate_to_persona", _sahte_delege)
    monkeypatch.setattr(orch, "_maliyet_onayi", _hayir)
    cikti = asyncio.run(orch._run_council_impl("hedef"))
    assert not kosan, "onay reddedildi ama uzmanlar yine de koştu"
    assert "onay" in cikti.lower()


# ── Arayüz: "kapı VAR" ≠ "arayüz kapıya bakıyor" (08-09 dersi) ─────────
from pathlib import Path  # noqa: E402

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"


def _core() -> str:
    return (FRONTEND / "js" / "core.js").read_text(encoding="utf-8")


def _index() -> str:
    return (FRONTEND / "index.html").read_text(encoding="utf-8")


def test_ekip_dugmesi_tek_karakterde_yok():
    """11-14: Yuki dışındaki karakterler kaldırıldı → uzman ekibi yok. "Görünmeyen özellik
    satılmaz"ın tersi de geçerli: OLMAYAN özelliğin düğmesi gösterilmez (backend ekip araçlarını
    uzman yokken modele sunmuyor — test_tek_karakter.py). Karakter eklenince düğme geri konur."""
    h = _index()
    assert 'id="team-btn"' not in h
    assert "ekibeSor()" not in h


def test_uzman_ciktisi_html_olarak_yorumlanmiyor():
    """Uzman çıktısı MODEL ürünüdür = güvenilmez girdi. `innerHTML` ile
    basılsaydı model üretimi bir metin XSS taşıyabilirdi."""
    c = _core()
    blok = c[c.find("d.type === 'companion_result'"):]
    blok = blok[:blok.find("else if (d.type ===", 10)]
    assert "innerHTML" not in blok
    assert "textContent" in blok


def test_maliyet_onayi_ham_json_gostermiyor():
    """Onay kutusu kullanıcının parasını harcayan karar — ham JSON ile sorulmaz."""
    c = _core()
    assert "_showToolApprovalModal(d.approval_id, d.tool, d.args, d.timeout, d.sunum)" in c
    assert "sunum.satirlar" in c


def test_aria_disabled_kullanilmiyor():
    """Kilitli düğme devre DIŞI değil — tıklanınca satış mesajı gösteriyor.
    `aria-disabled` hem ekran okuyucuyu hem Playwright'ı yanıltır (08-08 dersi)."""
    h = _index()
    blok = h[h.find('id="team-btn"'):]
    blok = blok[:blok.find("</button>")]
    assert "aria-disabled" not in blok
