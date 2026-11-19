"""In-process orkestrasyon — Yuki koordinatör, personalar uzman companion (Faz 22).

Zoey OS türevi: Yuki bir hedefi alt-görevlere böler, her birini bir uzman
personaya İZOLE bir alt-turda delege eder, sonuçları sentezler.

🔑 Uzman = `personas.PERSONAS`'ta Yuki DIŞINDAKİ her persona (`uzman_anahtarlari()`),
canlı okunur. 2026-11-14 ürün kararıyla Yuki dışındaki karakterler kaldırıldı →
uzman yok → ekip araçları (`EKIP_ARACLARI`) LLM'e sunulmaz (dispatcher
`get_active_tools`) ve çağrılırsa `ekip_yok_metni()` döner. Persona eklenince
hepsi kendiliğinden geri gelir. Bekçi: tests/test_tek_karakter.py

KRİTİK izolasyon kuralı: persona (`personas._current_persona`) ve history
(`llm._get_history`) süreç-içi GLOBAL state'tir. Eşzamanlı alt-ajanlar bunu
ASLA ezmemeli — yoksa ana konuşma bozulur. Bu yüzden alt-turlar:
  - persona'yı argümanla taşır (set_persona ÇAĞIRMAZ),
  - taze bir `messages` listesi kullanır (global history'e dokunmaz),
  - worker toolset'inden switch_character/switch_tab + orkestrasyon araçlarını
    çıkarır (global UI mutasyonu + recursion guard).

Tüm ağır bağımlılıklar (runner/llm/tools) fonksiyon içinde LAZY import edilir —
dispatcher → orchestrator → runner → tools/__init__ → dispatcher döngüsel
import'unu önlemek için.
"""
from __future__ import annotations

import asyncio
import contextvars
import json
import logging
import uuid

from app.mesajlar import M

logger = logging.getLogger(__name__)

# ── Recursion guard: alt-ajanlar tekrar meclis/delege çağıramaz ──
_depth: contextvars.ContextVar[int] = contextvars.ContextVar("orchestrator_depth", default=0)
MAX_DEPTH = 1

# ── Alt-tur ayarları (VARSAYILAN — kullanıcı ayarı ezer, bkz. `_ayar()`) ──
WORKER_MAX_STEPS = 4      # tek companion alt-turundaki max araç-döngüsü adımı
WORKER_TIMEOUT = 90.0     # saniye — tek companion alt-turu
COUNCIL_MAX_TASKS = 4     # bir meclis en fazla kaç uzmana böler
COUNCIL_CONCURRENCY = 2   # aynı anda koşan uzman sayısı — bkz. § Maliyet kapısı


def _ayar(ad: str, varsayilan):
    """Kullanıcının AYAR panelinden verdiği değer, yoksa modül varsayılanı.

    Config CANLI okunur (import anında değil): kullanıcı ücretsiz kotadayken
    4/4'ü 2/2'ye çekerse yeniden başlatmadan geçerli olsun.
    """
    try:
        from app import config as cfg
        v = int(getattr(cfg, ad, varsayilan))
        return v if v > 0 else varsayilan
    except Exception:
        return varsayilan


# ══════════════════════════════════════════════════════════════════════
# D8 — ALT AJANLAR SALT OKUR (geliştirici kararı 2026-08-12, R5 §4)
# ══════════════════════════════════════════════════════════════════════
# Alt ajanlar okuyabilir; **yazamaz, çalıştıramaz, kullanıcıya seslenemez.**
# Üç gerekçe: ① 4 uzman paralel yazarsa birbirini ezer ② yetki yüzeyi 4 katına
# çıkar ③ D10 — yalnız Yuki seslenir.
#
# 🔴 Neden İZİN listesi (deny değil): deny listesi **fail-open**'dır — yarın
# eklenen yeni bir yazma aracı listede olmadığı için worker'a sessizce açılır.
# İzin listesinde ise yeni araç varsayılan olarak KAPALIDIR. Sınıflandırmayı
# unutmak da yakalanır: `test_companion_ekibi.py` registry'deki HER aracın iki
# kümeden birinde olmasını şart koşar (yeni araç → test kırmızı).
#
# Ölçüt "dosyaya yazıyor mu" değil **"dış dünyada kalıcı bir etki bırakıyor mu"**:
# ekran görüntüsü diske dosya yazar · `youtube_music` medya oynatır ·
# `send_notification` kullanıcıya seslenir — üçü de okuma değildir.
WORKER_READONLY_TOOLS: frozenset[str] = frozenset({
    # bilgi/ağ okuma
    "web_search", "browse_web", "get_weather", "get_current_datetime",
    "get_exchange_rate", "get_crypto_price", "get_earthquake_alerts",
    "get_public_ip", "ping_host", "research_stock",
    # not/görev/takvim/fitness/bütçe — yalnız LİSTELEME ve OKUMA
    "get_note", "list_notes", "list_todos", "search_todos", "list_todo_lists",
    "list_reminders", "get_calendar_events", "get_budget_summary",
    "get_fitness_summary", "get_fitness_config", "list_meals", "list_workout",
    "list_fitness_templates",
    # dosya/git — okuma
    "list_directory", "read_file", "search_file", "diff_files",
    "git_status", "git_log", "read_journal",
    # görü — yerel görseli çözümler, dış dünyaya bir şey bırakmaz
    "analyze_image", "ocr_image", "read_qr",
    # sistem — salt okunur teşhis
    "get_system_info", "get_battery", "monitor_system", "monitor_process",
    "get_clipboard", "check_service", "check_updates",
    "list_packages", "list_modes", "list_tabs", "list_characters",
    # hafıza — D9: alt ajan kendi hafızasını OKUR (yazmaz)
    "memory_search", "memory_stats",
    # bilgi kasası — okuma (wiki_index yalnız index sayfalarını okur, üretmez)
    "wiki_search", "wiki_read", "wiki_index",
    # altyapı durumu — okuma
    "list_routines", "skill_list",
    # harita — yalnız haritanın o anki durumunu okur
    "map_status", "list_media",
})

# Worker'a KAPALI araçlar — sınıflandırma tamlığı için (çalışma zamanında
# kullanılmaz; kapı `WORKER_READONLY_TOOLS` izin listesidir).
WORKER_MUTATING_TOOLS: frozenset[str] = frozenset({
    # orkestrasyon — recursion guard (bir alt ajan başka alt ajanla konuşamaz)
    "delegate_to_companion", "run_team",
    # global UI/aktif-karakter mutasyonu
    "switch_character", "switch_tab", "start_mode",
    # kamera görüşü — biyometrik, rızası kullanıcının; alt ajan kameraya bakmaz (G4b)
    "kameraya_bak",
    # harita — kullanıcının açık haritasını taşır / katman değiştirir
    "map_goto", "map_layer", "show_media",
    # masaüstü Yuki — süreci açar/kapatır ve MASAUSTU_YUKI ayarını kalıcı yazar
    "masaustu_yuki",
    # ana turun araç şemasını genişletir (alan_secici) — worker'ın şeması ayrı, anlamsız
    "arac_alani_ac",
    # kullanıcıya seslenme — D10: yalnız Yuki konuşur
    "send_notification", "send_screenshot_to_chat",
    # dosya sistemi + arşiv
    "write_file", "append_file", "compress_file", "extract_archive",
    # ekran görüntüsü: diske dosya yazar + kullanıcının ekranını kaydeder
    "take_screenshot",
    # not/görev/hatırlatma/takvim yazma
    "create_note", "delete_note", "restore_note", "create_todo", "update_todo", "delete_todo",
    "complete_todo", "set_reminder", "cancel_reminder",
    "create_calendar_event", "delete_calendar_event",
    # fitness yazma
    "log_meal", "delete_meal", "log_workout_exercise", "update_fitness_config",
    "save_fitness_template", "delete_fitness_template",
    # hafıza yazma — `memory_reflect` duplikat anıları SİLER (D9: yazmaz)
    "memory_reflect",
    # bilgi kasası yazma
    "wiki_write",
    # rutin yazma
    "create_routine", "delete_routine",
    # ortam/medya/oyun/uygulama — kalıcı yan etki
    "set_clipboard", "set_language", "control_media", "youtube_music",
    "open_application", "launch_game", "close_game",
    "update_game", "smart_home_control", "generate_image",
    # altyapı tetikleme
    "skill_run", "trigger_n8n",
})

# Uzman/işçi gerektiren araçlar — uzman yokken LLM'e SUNULMAZ (dispatcher).
EKIP_ARACLARI: frozenset[str] = frozenset({"delegate_to_companion", "run_team"})
_HATA_KIRP = 200  # hata metni modele ve kullanıcıya gider; kısa tutulur


def uzmanlar() -> list[str]:
    """Uzman ekibi = Yuki dışındaki personalar (canlı; boş = ekip yok)."""
    from app.services.personas import uzman_anahtarlari
    return uzman_anahtarlari()


def ekip_var() -> bool:
    return bool(uzmanlar())


def varsayilan_uzman() -> str | None:
    """Bilinmeyen/eksik persona adı bu uzmana düşer (eski sabit `DEFAULT_WORKER`)."""
    u = uzmanlar()
    return u[0] if u else None


def ekip_yok_metni() -> str:
    return ("Hata: Uzman ekibi yok — Yuki dışında tanımlı karakter bulunmuyor. "
            "Bu işi ekip olmadan, kendi araçlarınla yap.")


def _rol_ipucu(key: str) -> str:
    """Koordinatörün görev dağıtım ipucu: personanın `rol` alanı, yoksa unvanı."""
    from app.services.personas import PERSONAS
    m = PERSONAS.get(key, {})
    return str(m.get("rol") or m.get("title") or key)


# ────────────────────────────────────────────────────────────────────
# Yardımcılar
# ────────────────────────────────────────────────────────────────────
def _worker_tools() -> list[dict]:
    """Worker alt-turunun kullanabileceği araçlar — D8: SALT OKUR.

    İki kapıdan geçer:
      ① `WORKER_READONLY_TOOLS` izin listesi (yazma/çalıştırma/seslenme yok)
      ② kullanıcının kendi kademesi (`yetki.tool_allowed`) — alt ajan,
         kullanıcının satın almadığı bir aracı kullanamaz. Aksi hâlde ekip,
         paywall'ın etrafından dolaşan bir kapı olurdu.
    """
    from app.services.tools import TOOLS
    try:
        from app.services import yetki
        kademe_izinli = yetki.tool_allowed
    except Exception:  # pragma: no cover — entitlement kurulmadıysa izin listesi tek kapı
        def kademe_izinli(_ad: str) -> bool:
            return True
    return [
        t for t in TOOLS
        if (ad := t.get("function", {}).get("name")) in WORKER_READONLY_TOOLS
        and kademe_izinli(ad)
    ]


def _yanit_dili() -> str:
    from app.config import yanit_dili
    return yanit_dili()


def _worker_system_prompt(persona_key: str) -> str:
    """Bir uzman companion için compact worker promptu (config global prompt'una bağımlı DEĞİL)."""
    from app.services.personas import get_persona_meta
    m = get_persona_meta(persona_key)
    return (
        f"Sen {m.get('label', persona_key)} — {m.get('title', 'uzman companion')}. "
        "Bir AI companion ekibinin uzman üyesisin; koordinatör Yuki sana tek bir alt-görev verdi.\n\n"
        f"KİMLİK:\n{m.get('identity', '')}\n\n"
        f"KİŞİLİK:\n{m.get('personality', '')}\n\n"
        "KURALLAR:\n"
        "- SADECE verilen alt-görevi yap. Gerekiyorsa araçları kullan.\n"
        "- Araçların SALT OKUNUR. Dosya yazamaz, komut çalıştıramaz, ayar "
        "değiştiremez, kullanıcıya bildirim gönderemezsin. Bir işin yapılması "
        "gerekiyorsa onu YAPMA — sonucunda ne yapılması gerektiğini yaz, "
        "koordinatör Yuki uygular.\n"
        f"- Yanıt dili: {_yanit_dili()}. Net ve öz yanıt ver. Selamlama/sohbet açma yok.\n"
        "- [EMOTION]/[BEHAVIOR] etiketi KULLANMA — çıktın koordinatöre gidiyor, kullanıcıya değil.\n"
        "- Sonucu doğrudan ve uygulanabilir biçimde döndür; süsleme yapma."
    )


# ────────────────────────────────────────────────────────────────────
# Çekirdek: tek personaya izole delege
# ────────────────────────────────────────────────────────────────────
async def delegate_to_persona(persona_key: str, subtask: str) -> str:
    """Tek bir uzman personaya İZOLE alt-turda görev delege eder.

    Global persona/history state'ine dokunmaz. Kendi taze mesaj listesi + scoped
    araç seti + kendi LLMRunner'ı ile çalışır.
    """
    from app.services.llm import _yan_istemci, _background_model
    from app.config import LLM_MODEL_FAST, LLM_MODEL
    from app.services.runner import LLMRunner, CancellationToken

    varsayilan = varsayilan_uzman()
    if varsayilan is None:
        return ekip_yok_metni()
    key = (persona_key or "").lower().strip()
    if key not in uzmanlar():
        logger.info("bilinmeyen/uzman olmayan persona '%s' → %s", persona_key, varsayilan)
        key = varsayilan

    messages = [
        {"role": "system", "content": _worker_system_prompt(key)},
        {"role": "user", "content": subtask},
    ]
    client = _yan_istemci()
    # Kullanıcı BYOK'ta model seçtiyse uzman ajanlar da onu kullanır — yoksa
    # ücretsiz anahtarlı kullanıcıda ekip çağrısı ücretli modele gidip ölür.
    model = _background_model(LLM_MODEL_FAST or LLM_MODEL)
    runner = LLMRunner(
        client, model, _worker_tools(),
        max_steps=_ayar("WORKER_MAX_STEPS", WORKER_MAX_STEPS),
        cancel_token=CancellationToken(),
    )
    chunks: list[str] = []
    async for ch in runner.run(messages):
        chunks.append(ch)
    out = "".join(chunks).strip()
    return out or "(companion boş yanıt döndürdü)"


# ────────────────────────────────────────────────────────────────────
# Koordinatör: hedef → plan → paralel delege → sentez
# ────────────────────────────────────────────────────────────────────
def _parse_plan(raw: str, goal: str) -> list[dict]:
    """Koordinatörün JSON planını sağlamca ayrıştır; başarısızsa tek-görev fallback."""
    gecerli = uzmanlar()
    varsayilan = varsayilan_uzman()
    items: list[dict] = []
    i, j = raw.find("["), raw.rfind("]")
    if i != -1 and j != -1 and j > i:
        try:
            plan = json.loads(raw[i:j + 1])
        except Exception:
            plan = None
        if isinstance(plan, list):
            for el in plan[:_ayar("COUNCIL_MAX_TASKS", COUNCIL_MAX_TASKS)]:
                if not isinstance(el, dict):
                    continue
                st = str(el.get("subtask", "")).strip()
                if not st:
                    continue
                p = str(el.get("persona", "")).lower().strip()
                if p not in gecerli:
                    p = varsayilan
                items.append({"persona": p, "subtask": st})
    if not items:
        items = [{"persona": varsayilan, "subtask": goal}]
    return items


async def _decompose(goal: str) -> list[dict]:
    """Hedefi 1-4 alt-göreve böl ve her birini bir uzmana ata."""
    from app.services.llm import _yan_istemci, _background_model
    from app.config import LLM_MODEL_FAST, LLM_MODEL

    ekip = uzmanlar()
    roles = "\n".join(f"- {k}: {_rol_ipucu(k)}" for k in ekip)
    ornek = ekip[0] if ekip else "uzman"
    tavan = _ayar("COUNCIL_MAX_TASKS", COUNCIL_MAX_TASKS)
    sys = (
        "Sen Yuki, bir AI companion ekibinin koordinatörüsün. Kullanıcının hedefini "
        f"1-{tavan} alt-göreve böl ve her alt-görevi en uygun uzmana ata.\n"
        f"Uzmanlar:\n{roles}\n\n"
        "SADECE bir JSON dizisi döndür, başka HİÇBİR metin ekleme. Biçim: "
        f'[{{"persona":"{ornek}","subtask":"..."}}]. '
        "Uzmanların araçları SALT OKUNUR — onlara yazma/çalıştırma gerektiren "
        "alt-görev verme, yalnız araştırma/analiz/hazırlık ver.\n"
        "Hedef tek uzmanlık gerektiriyorsa tek elemanlı dizi döndür. Alt-görevler "
        "birbirinden bağımsız ve paralel çalışabilir olsun."
    )
    client = _yan_istemci()
    model = _background_model(LLM_MODEL_FAST or LLM_MODEL)
    try:
        resp = await client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": sys},
                      {"role": "user", "content": goal}],
            temperature=0.3,
            max_tokens=500,
        )
        raw = (resp.choices[0].message.content or "").strip()
    except Exception as e:
        logger.warning("decompose hata: %s — tek-görev fallback", e)
        raw = ""
    return _parse_plan(raw, goal)


async def _synthesize(goal: str, parts: list[dict]) -> str:
    """Uzman sonuçlarını tek, kullanıcıya dönük Yuki yanıtında birleştir."""
    from app.services.llm import _yan_istemci, _background_model
    from app.config import LLM_MODEL_STRONG, LLM_MODEL

    body = "\n\n".join(
        f"[{p['label']} — {p['subtask']}]\n{p['result']}" for p in parts
    )
    sys = (
        "Sen Yuki. Ekip arkadaşların alt-görevleri tamamladı. Sonuçları TEK, tutarlı "
        f"ve kullanıcıya dönük bir yanıtta birleştir. Yanıt dili: {_yanit_dili()}; net, akıcı. Kime ne "
        "yaptırdığını doğal biçimde belirtebilirsin ama kuru rapor gibi olmasın."
    )
    client = _yan_istemci()
    model = _background_model(LLM_MODEL_STRONG or LLM_MODEL)
    try:
        resp = await client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": sys},
                      {"role": "user", "content": f"Hedef: {goal}\n\nEkip sonuçları:\n{body}"}],
            temperature=0.5,
            max_tokens=900,
        )
        out = (resp.choices[0].message.content or "").strip()
        return out or body
    except Exception as e:
        logger.warning("synthesize hata: %s — ham sonuçlar döndürülüyor", e)
        return body


# ══════════════════════════════════════════════════════════════════════
# MALİYET KAPISI (R5 FAZ 2) — bu özelliğin cilası değil ÖN KOŞULU
# ══════════════════════════════════════════════════════════════════════
# Bir meclis ≈18-22 LLM isteği. Kredisiz OpenRouter hesabı **günde 50 · dakikada
# 20** alır → tek meclis günlük kotanın ~%40'ı. Kapı olmadan kullanıcı günde iki
# kez kullanır, üçüncüsünde 429 yer ve "Yuki bozuldu" der. Bu üründe yanlış
# teşhis iki kez ölçüldü (ElevenLabs 401 = kota · slowapi 429 = geçersiz lisans).
_KOTA_IPUCLARI = ("429", "rate limit", "rate_limit", "quota", "too many requests")


def _kota_hatasi_mi(e: BaseException) -> bool:
    """Bu hata kota/hız sınırı mı? (kod değil METİN söyler — sağlayıcılar farklı)"""
    metin = f"{type(e).__name__} {e}".lower()
    return any(ip in metin for ip in _KOTA_IPUCLARI)


def maliyet_tahmini(gorev_sayisi: int) -> dict:
    """Bir meclisin LLM istek sayısı — en iyi ve en kötü senaryo.

    decompose (1) + her uzman [1 … WORKER_MAX_STEPS] + sentez (1).
    Tek görevli planda sentez yapılmaz (sonuç doğrudan döner) → +1 yerine +0.
    """
    adim = _ayar("WORKER_MAX_STEPS", WORKER_MAX_STEPS)
    sentez = 0 if gorev_sayisi <= 1 else 1
    return {
        "gorevler": gorev_sayisi,
        "en_az": 1 + gorev_sayisi + sentez,
        "en_cok": 1 + gorev_sayisi * adim + sentez,
    }


async def _maliyet_onayi(goal: str, plan: list[dict]) -> bool:
    """Meclis başlamadan kullanıcıya maliyeti göster ve onay al.

    🔴 Onay `_decompose`'dan SONRA istenir: o an planın kaç uzmana bölündüğü
    BİLİNİR, yani kullanıcıya tahmin değil ölçüm gösterilir. Bedeli 1 istek.

    ⚠️ Cevaplayacak kimse yoksa kapı uygulanmaz (arka plan rutini / WS kapalı) —
    kimsenin göremediği bir onay penceresi kapı değil, 30 saniyelik sessiz bir
    kilittir ve rutini reddedilmiş gibi düşürür.
    """
    from app.services.event_bus import bus
    from app.services.tools.approval_gate import request_approval

    if not bus.abone_var("tool_approval"):
        logger.info("meclis onayı atlandı — dinleyen istemci yok (arka plan çağrısı)")
        return True

    t = maliyet_tahmini(len(plan))
    satirlar = [f"{p['label']}: {p['subtask']}" for p in plan]
    kota = _kota_metni()
    mesaj = M("ekip.maliyet-mesaj", gorevler=t["gorevler"], en_az=t["en_az"], en_cok=t["en_cok"])
    if kota:
        mesaj += f"\n{kota}"
    return await request_approval(
        "run_team",
        {"goal": goal[:200], "gorevler": t["gorevler"]},
        sunum={"baslik": M("ekip.maliyet-baslik"),
               "mesaj": mesaj, "satirlar": satirlar},
    )


def _kota_metni() -> str:
    """Kullanıcının ücretsiz kotası — 🩺 SAĞLIK panelinin AYNI fonksiyonundan.

    🔑 Kendi kopyasını yazmıyor: `self_check._denetle_ucretsiz_kota()` aynı soruya
    zaten cevap veriyor ve `:free` olmayan modelde kotanın uygulanmadığını da
    biliyor. İkinci bir kopya er geç ayrışır ve ayrıştığı yere kimse bakmaz
    (`surum.js` dersi).
    """
    try:
        from app.services.self_check import _denetle_ucretsiz_kota
        d = _denetle_ucretsiz_kota()
        detay = (d.get("detay") or "").strip()
        return M("ekip.kota", detay=detay) if detay and not d.get("kota_bilinmiyor") else ""
    except Exception:
        return ""


# ══════════════════════════════════════════════════════════════════════
# EKİP OLAYLARI — AJAN sekmesi "kim ne yapıyor"u buradan görür
# ══════════════════════════════════════════════════════════════════════
# Tek kaynak event bus: /ws/realtime olayları zaten taşıyor, ikinci bir
# toplayıcı/ölçer YOK. Her çalışma bir `run_id` taşır; companion_* olayları
# hangi çalışmaya ait olduklarını bu kimlikle söyler (iki meclis üst üste
# binerse kartlar karışmasın). team_start/team_end çalışmanın çerçevesidir.
# ⚠️ Olay yayını işi ASLA düşürmez — yayın hatası yutulur.
async def _yayinla(konu: str, veri: dict) -> None:
    try:
        from app.services.event_bus import bus
        await bus.publish(konu, veri)
    except Exception:
        pass


def _yeni_calisma() -> str:
    return uuid.uuid4().hex[:8]


async def _run_council_impl(goal: str) -> str:
    from app.services.personas import get_persona_meta

    if not ekip_var():
        return ekip_yok_metni()
    plan = await _decompose(goal)
    logger.info("council plan (%d görev): %s", len(plan),
                [(p["persona"], p["subtask"][:40]) for p in plan])

    if not await _maliyet_onayi(goal, plan):
        return ("Ekip çalışması başlatılmadı — maliyet onayı verilmedi. "
                "İstersen ben tek başıma yanıtlayayım.")

    run_id = _yeni_calisma()
    await _yayinla("team_start", {
        "run_id": run_id, "kip": "meclis", "goal": goal[:200],
        "plan": [{"persona": p["persona"],
                  "label": get_persona_meta(p["persona"]).get("label", p["persona"]),
                  "subtask": p["subtask"][:200]} for p in plan],
    })
    try:
        return await _meclis_yurut(goal, plan, run_id)
    except BaseException:
        await _yayinla("team_end", {"run_id": run_id, "durum": "hata"})
        raise


async def _meclis_yurut(goal: str, plan: list[dict], run_id: str) -> str:
    from app.services.event_bus import bus
    from app.services.personas import get_persona_meta

    # Eşzamanlılık sınırı: sınırsız `gather` dakikada-20 sınırını TEK çağrıda
    # aşabiliyordu (kullanıcı hiçbir şey yapmadan 429 yer). [VARSAYIM] 2 sayısı
    # akıl yürütmeyle seçildi, gerçek kotayla ölçülmedi — kullanıcı ayarı var.
    sem = asyncio.Semaphore(max(1, _ayar("COUNCIL_CONCURRENCY", COUNCIL_CONCURRENCY)))
    kota_carpti = False

    async def _one(item: dict) -> dict:
        nonlocal kota_carpti
        key, st = item["persona"], item["subtask"]
        label = get_persona_meta(key).get("label", key)
        try:
            await bus.publish("companion_active",
                              {"persona": key, "label": label, "subtask": st[:80],
                               "run_id": run_id})
        except Exception:
            pass
        durum = "ok"
        async with sem:
            try:
                res = await asyncio.wait_for(delegate_to_persona(key, st), timeout=WORKER_TIMEOUT)
            except asyncio.TimeoutError:
                res, durum = f"({label} zaman aşımına uğradı, {int(WORKER_TIMEOUT)}s)", "timeout"
            except Exception as e:
                # 🔴 Bir uzmanın kotaya çarpması TÜM meclisi düşürmez — kısmi sonuç
                # sıfır sonuçtan iyidir ve kullanıcı NEDEN eksik olduğunu görür.
                if _kota_hatasi_mi(e):
                    kota_carpti = True
                    res, durum = f"({label}: kota/hız sınırı nedeniyle tamamlanamadı)", "kota"
                else:
                    res, durum = f"({label} hata: {str(e)[:_HATA_KIRP]})", "hata"
        if durum == "ok" and not (res or "").strip():
            res, durum = "(companion boş yanıt döndürdü)", "bos"
        try:
            await bus.publish("companion_done", {"persona": key, "label": label, "durum": durum,
                                                 "run_id": run_id})
            # FAZ 3.3 — "kim ne dedi": sentez tek bir Yuki cevabı üretir, ama
            # kullanıcı uzmanların ham çıktısını da açabilmeli. Bu olay olmadan
            # ekip hissi oluşmaz; kullanıcı yalnız "biraz daha yavaş cevap" görür.
            await bus.publish("companion_result", {
                "persona": key, "label": label,
                "subtask": st[:200], "result": res[:4000], "durum": durum,
                "run_id": run_id,
            })
        except Exception:
            pass
        return {"persona": key, "label": label, "subtask": st, "result": res, "durum": durum}

    parts = await asyncio.gather(*[_one(it) for it in plan])
    # Sentez modeli hata metinlerinden de akıcı bir cevap yazar: hiçbir uzman çalışmamışken
    # kullanıcı başarı görürdü.
    if all(p["durum"] != "ok" for p in parts):
        await _yayinla("team_end", {"run_id": run_id, "durum": "kota" if kota_carpti else "hata"})
        ozet = "; ".join(p["result"] for p in parts)
        return f"Hata: Ekip çalışmadı, hiçbir uzman sonuç üretemedi: {ozet}"
    if len(parts) == 1:
        await _yayinla("team_end", {"run_id": run_id, "durum": "kota" if kota_carpti else "ok"})
        return parts[0]["result"]
    out = await _synthesize(goal, parts)
    if kota_carpti:
        out += ("\n\n_(Not: bazı uzmanlar model kotası dolduğu için tamamlayamadı — "
                "bu bir hata değil, günlük istek sınırı. Yanıt eksik olabilir.)_")
    await _yayinla("team_end", {"run_id": run_id, "durum": "kota" if kota_carpti else "ok"})
    return out


# ────────────────────────────────────────────────────────────────────
# Araç yüzeyi (dispatcher bunları çağırır) — recursion guard'lı
# ────────────────────────────────────────────────────────────────────
async def companion_delegate(persona_key: str, subtask: str) -> str:
    """Araç: tek uzman companion'a izole alt-görev delege et."""
    if not (subtask or "").strip():
        return "Hata: Alt görev boş olamaz."  # boş görev de modele gidip para harcıyordu
    if _depth.get() >= MAX_DEPTH:
        return "(iç içe delege engellendi — bir alt-ajan tekrar delege edemez)"
    if not ekip_var():
        return ekip_yok_metni()  # olay da yayınlanmaz: AJAN sekmesinde hayalet kart yok
    tok = _depth.set(_depth.get() + 1)
    # Tekli delege de bir ekip çalışmasıdır (1 uzman) — AJAN sekmesi onu da görür.
    # Bilinmeyen persona `delegate_to_persona`daki gibi varsayılan uzmana düşer;
    # olay, işi GERÇEKTEN yapan uzmanın adını taşısın.
    from app.services.personas import get_persona_meta
    key = (persona_key or "").lower().strip()
    key = key if key in uzmanlar() else varsayilan_uzman()
    label = get_persona_meta(key).get("label", key)
    run_id = _yeni_calisma()
    await _yayinla("team_start", {"run_id": run_id, "kip": "tekli", "goal": subtask[:200],
                                  "plan": [{"persona": key, "label": label, "subtask": subtask[:200]}]})
    await _yayinla("companion_active", {"persona": key, "label": label,
                                        "subtask": subtask[:80], "run_id": run_id})
    durum = "ok"
    try:
        return await asyncio.wait_for(
            delegate_to_persona(persona_key, subtask), timeout=WORKER_TIMEOUT
        )
    except asyncio.TimeoutError:
        durum = "timeout"
        return f"(companion '{persona_key}' zaman aşımına uğradı)"
    except Exception as e:
        durum = "kota" if _kota_hatasi_mi(e) else "hata"
        return f"(companion delege hatası: {e})"
    finally:
        _depth.reset(tok)
        await _yayinla("companion_done", {"persona": key, "label": label,
                                          "durum": durum, "run_id": run_id})
        await _yayinla("team_end", {"run_id": run_id, "durum": durum})


async def run_team(goal: str) -> str:
    """Araç: hedefi companion ekibine dağıt (decompose → paralel delege → sentez)."""
    if not (goal or "").strip():
        return "Hata: Hedef boş olamaz."  # plan çıkarmak da bir model çağrısı
    if _depth.get() >= MAX_DEPTH:
        return "(iç içe meclis engellendi — bir alt-ajan meclis kuramaz)"
    if not ekip_var():
        return ekip_yok_metni()
    tok = _depth.set(_depth.get() + 1)
    try:
        return await _run_council_impl(goal)
    except Exception as e:
        logger.error("run_team hata: %s", e)
        return f"(ekip çalışması başarısız: {e})"
    finally:
        _depth.reset(tok)
