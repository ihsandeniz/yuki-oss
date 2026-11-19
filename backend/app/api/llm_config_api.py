"""LLM sağlayıcı / model seçici API — runtime değişiklik."""

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.limiter import limiter
from app.mesajlar import M
from app.services import llm_providers as _lp
from app.services import sirlar as _sirlar

router = APIRouter(prefix="/api/llm", tags=["llm"])

# ── BYOK sihirbazının model listesi ─────────────────────────────────────────
# 🔴 2026-08-01 dersi: liste `frontend/index.html`de SABİTTİ. OpenRouter üç ücretsiz
# modeli birden kaldırınca ürün yeni kullanıcıda sessizce öldü (404 No endpoints found)
# ve bunu ancak kullanıcı fark etti. Artık liste canlı API'den gelir; sabit liste
# yalnızca çevrimdışı yedektir.
#
# Gizlilik notu: openrouter.ai/api/v1/models **public** uçtur — anahtar gönderilmez,
# kullanıcı verisi gitmez ve bu çağrı yalnız ⚙ AYAR → 🔑 ANAHTAR paneli açıldığında
# yapılır. "Bizim sunucumuza hiç bağlanmaz" iddiası bozulmaz (bu bizim sunucumuz değil,
# kullanıcının zaten anahtar aldığı LLM sağlayıcısıdır).

# Gerçek anahtarla ölçüldü: araç çağırdı + Türkçesi akıcı (2026-08-01).
DEFAULT_FREE_MODEL = "google/gemma-4-26b-a4b-it:free"

VERIFIED_FREE = [
    {"id": DEFAULT_FREE_MODEL, "label_k": "llm.model-gemma"},
    {"id": "openai/gpt-oss-20b:free", "label_k": "llm.model-gptoss"},
]

# ⚠️ `tools` ilan ediyor ama ölçümde araç ÇAĞIRMADI → listeye alma.
# Ders: ilan edilen yetenek ≠ ölçülen yetenek.
BLOCKED_FREE = {"nvidia/nemotron-3-nano-30b-a3b:free"}

PAID_PICKS = [
    {"id": "openai/gpt-4.1-mini", "label_k": "llm.model-gpt41mini"},
]

_MODELS_URL = "https://openrouter.ai/api/v1/models"
_MODELS_TTL = 1800.0  # 30 dk — panel her açılışta ağa çıkmasın
_models_cache: dict = {"at": 0.0, "groups": None}
#: sağlayıcı-başı model listesi önbelleği (OpenRouter'ınki ayrı — üstteki)
_saglayici_cache: dict[str, dict] = {}


class ProviderConfig(BaseModel):
    provider: str  # "openrouter" | "anthropic"
    model: str


@router.get("/config")
@limiter.limit("100/minute")
async def get_llm_config(request: Request):
    """Mevcut sağlayıcı, model ve kullanılabilir ön ayarları döner."""
    from app.services.llm import get_runtime_config
    from app.config import ANTHROPIC_API_KEY, OPENROUTER_API_KEY, model_presets

    cfg = get_runtime_config()
    return {
        **cfg,
        "presets": model_presets(),
        "anthropic_available": bool(ANTHROPIC_API_KEY),
        "openrouter_available": bool(OPENROUTER_API_KEY),
    }


@router.post("/config")
@limiter.limit("30/minute")
async def set_llm_config(request: Request, body: ProviderConfig):
    """Sağlayıcı ve modeli çalışırken değiştir."""
    # Claude Code CLI modu — API key gereksiz, binary kontrolü yap
    if body.provider == "claude_code":
        import shutil
        if not shutil.which("claude"):
            return {"ok": False, "error": M("llm.claude-cli-yok")}
        from app.services.llm import set_runtime_config
        set_runtime_config("claude_code", "claude-code")
        return {"ok": True, "provider": "claude_code", "model": "claude-code"}

    sag = _lp.kayit(body.provider)
    if sag is None:
        return {"ok": False, "error": M("llm.bilinmeyen-saglayici", kimlik=body.provider)}
    # Yerel sağlayıcıda (Ollama) anahtar diye bir şey yok — burada anahtar aramak
    # kullanıcıyı olmayan bir alanı doldurmaya yollardı.
    if not sag.yerel and not _lp.anahtar(sag.kimlik):
        return {"ok": False,
                "error": M("llm.env-ayarlanmamis", env=sag.env)}

    # 🔴 Model ID artık SABİT ÖN AYAR LİSTESİNE karşı doğrulanmıyor.
    # Eski kod `MODEL_PRESETS`'te olmayan her ID'yi reddediyordu; o liste elle
    # bakımlı ve bayat (2026-08-01'de tam bu sınıf yüzünden ürün öldü). Model
    # listesi canlı `/api/llm/models`'ten geliyor; geçersiz ID'nin gerçek kapısı
    # sağlayıcının kendi 404'ü ve `_denetle_llm_model` denetimi.
    model = (body.model or "").strip() or sag.varsayilan_model

    from app.services.llm import set_runtime_config
    set_runtime_config(sag.kimlik, model)
    return {"ok": True, "provider": sag.kimlik, "model": model}


def _clean_label(name: str) -> str:
    return " ".join((name or "").split())


def _cevir(gruplar: list) -> list:
    """Grup başlığı/etiketi ÇIKIŞ anında aktif dilde üretilir.

    Önbellekte anahtar (`title_k`/`label_k`) durur, metin değil — liste 30 dk
    önbellekte kalıyor; metin dolum anında üretilseydi dil değişince eski dilde
    kalırdı. `ad` sağlayıcı kimliğidir, adı katalogdan (`_sag_metin`) çözülür.
    """
    from app.services import llm_providers as _lp

    def _baslik(g):
        if "title_k" not in g:
            return g.get("title", "")
        kw = dict(g.get("title_kw") or {})
        if "ad" in kw:
            sag = _lp.kayit(kw["ad"])
            kw["ad"] = _sag_metin(sag, "ad") if sag else kw["ad"]
        return M(g["title_k"], **kw)

    return [{"title": _baslik(g),
             "options": [{"id": o["id"],
                          "label": M(o["label_k"]) if "label_k" in o else o.get("label", o["id"])}
                         for o in g.get("options", [])]}
            for g in gruplar]


def _cikis(payload: dict, *, cached: bool) -> dict:
    return {**payload, "groups": _cevir(payload.get("groups") or []), "cached": cached}


def _fallback_groups() -> list:
    """Ağ yokken / OpenRouter erişilemezken gösterilecek sabit liste."""
    return [
        {"title_k": "llm.grup-ucretsiz-dogrulandi", "options": list(VERIFIED_FREE)},
        {"title_k": "llm.grup-ucretli", "options": list(PAID_PICKS)},
    ]


async def _fetch_live_groups() -> list:
    """OpenRouter'ın canlı model listesinden ücretsiz + araç-destekli olanları çıkar.

    Doğrulanmış modeller ancak CANLI listede de duruyorsa gösterilir — kalkmış bir
    modeli "doğrulandı" diye sunmak tam olarak 2026-08-01'de patlayan hataydı.
    """
    import httpx

    async with httpx.AsyncClient(timeout=6.0) as client:
        resp = await client.get(_MODELS_URL)
        resp.raise_for_status()
        data = resp.json().get("data") or []

    live_free = {}
    for m in data:
        mid = m.get("id") or ""
        if not mid.endswith(":free") or mid in BLOCKED_FREE:
            continue
        if "tools" not in (m.get("supported_parameters") or []):
            continue  # araç çağıramayan model Yuki'nin yarısını kapatır
        live_free[mid] = _clean_label(m.get("name") or mid)

    verified = [v for v in VERIFIED_FREE if v["id"] in live_free]
    others = [
        {"id": mid, "label": label}
        for mid, label in live_free.items()
        if not any(v["id"] == mid for v in verified)
    ][:8]

    groups = []
    if verified:
        groups.append({"title_k": "llm.grup-ucretsiz-dogrulandi", "options": verified})
    if others:
        groups.append({"title_k": "llm.grup-ucretsiz-canli", "options": others})
    groups.append({"title_k": "llm.grup-ucretli", "options": list(PAID_PICKS)})
    return groups


def _yerel_kok(sag) -> str:
    """`http://127.0.0.1:11434/v1` → `http://127.0.0.1:11434` (Ollama'nın kendi API kökü).

    ⚠️ `rstrip("/v1")` KULLANMA — rstrip karakter kümesi siler, sonek değil:
    `…:11434/v1` için tesadüfen çalışır ama `…/ollama/v1` gibi bir adreste
    sondaki harfleri de yer. Sonek olarak kesiyoruz.
    """
    kok = (sag.base_url or "").rstrip("/")
    return kok[:-3] if kok.endswith("/v1") else kok


class YerelModelYok(RuntimeError):
    """Ollama ayakta ama hiç sohbet modeli kurulu değil.

    Ayrı bir sınıf çünkü çözümü farklı: "Ollama'yı başlat" değil,
    "`ollama pull` ile model indir". Bunu istisna TİPİNDEN (RuntimeError vs
    diğerleri) ayırt etmeye çalışmak kırılgandı — her RuntimeError'ı "zaten
    anlaşılır" saymak, gerçek bir çalışma-zamanı hatasını olduğu gibi panele
    basardı (2026-08-08 testinde yakalandı).
    """


def _yerel_hata_metni(sag, e: Exception) -> str:
    """Yerel bağlantı hatasını kullanıcının anlayacağı TÜRKÇE cümleye çevir.

    🔴 2026-08-08, tarayıcıda görüldü: Ollama kapalıyken panelde ham httpx metni
    (*"All connection attempts failed"*) yazıyordu. İngilizce, teknik ve **ne
    yapılacağını söylemiyor** — kullanıcı bunu "Yuki bozuk" diye okur. Ham hata
    log'a aittir, panele değil.
    """
    ham = str(e)
    if isinstance(e, YerelModelYok):    # zaten TR ve ne yapılacağını söylüyor
        return ham[:220]
    # FAZ 3 · Dalga 2 · Blok 4B: cümle kataloğa taşındı. Teknik ek `{teknik}`
    # ile giriyor — ham hata ÇEVRİLMEZ, o log'un dilidir (yorumun kendi dersi:
    # "ham hata log'a aittir, panele değil"; burada panele giden kısım artık
    # kullanıcının dilinde, teknik kuyruk olduğu gibi).
    return M("yerel.ulasilamadi", adres=sag.base_url, teknik=ham[:90])


async def _yerel_modeller(sag) -> list:
    """Ollama'da KURULU olan modeller — `GET /api/tags`.

    Bulut sağlayıcılardan farkı: burada "sağlayıcının sunduğu modeller" diye bir
    katalog yok, yalnız kullanıcının kendi indirdiği modeller var. Hiç model
    indirilmemişse boş liste dönmek yerine bunu söyleyen bir istisna atarız —
    "liste boş" ile "Ollama kapalı" farklı sorunlardır ve çözümleri de farklıdır.
    """
    import httpx

    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.get(f"{_yerel_kok(sag)}/api/tags")
        resp.raise_for_status()
        govde = resp.json()

    adlar = []
    for m in (govde.get("models") or []):
        ad = (m.get("name") or m.get("model") or "").strip()
        if not ad or ad in adlar:
            continue
        # Gömme (embedding) modelleri sohbet edemez — listeye koymak kullanıcıyı
        # çalışmayan bir seçime yollar. Ollama tipi ilan etmediği için ad eleniyor.
        if any(im in ad.lower() for im in ("embed", "bge-", "nomic-")):
            continue
        adlar.append(ad)

    if not adlar:
        raise YerelModelYok(M("llm.yerel-model-yok"))

    boyut = {(m.get("name") or m.get("model") or ""): m.get("size") or 0
             for m in (govde.get("models") or [])}

    def _etiket(ad: str) -> str:
        gb = (boyut.get(ad) or 0) / 1_000_000_000
        return f"{ad} — {gb:.1f} GB" if gb >= 0.1 else ad

    return [{"title_k": "llm.grup-kurulu",
             "options": [{"id": a, "label": _etiket(a)} for a in adlar]}]


async def _saglayici_modelleri(sag) -> list:
    """OpenRouter DIŞINDAKİ sağlayıcıların model listesi (OpenAI-uyumlu `/models`).

    ⚠️ OpenRouter'ın aksine bu uçlar **anahtar ister**. Anahtar sağlayıcının kendi
    sunucusuna gider — bizim sunucumuza değil; vitrindeki gizlilik iddiası korunur.
    Anahtar yoksa ağa hiç çıkılmaz, kayıttaki öne çıkan modeller döner.
    """
    import httpx
    from app.services import llm_providers as _lp

    key = _lp.anahtar(sag.kimlik)
    one_cikan = [{"id": m, "label": m} for m in (sag.one_cikan or (sag.varsayilan_model,))]
    if not key:
        return [{"title_k": "llm.grup-onerilenler-anahtarsiz", "title_kw": {"ad": sag.kimlik},
                 "options": one_cikan}]

    if sag.sdk == "anthropic":
        url = f"{sag.base_url.rstrip('/')}/v1/models"
        basliklar = {"x-api-key": key, "anthropic-version": "2023-06-01"}
    else:
        url = f"{sag.base_url.rstrip('/')}/models"
        basliklar = {"Authorization": f"Bearer {key}"}

    async with httpx.AsyncClient(timeout=8.0) as client:
        resp = await client.get(url, headers=basliklar)
        resp.raise_for_status()
        govde = resp.json()

    ham = govde.get("data") if isinstance(govde, dict) else govde
    kimlikler = []
    for m in (ham or []):
        mid = (m.get("id") if isinstance(m, dict) else str(m)) or ""
        # Google OpenAI-uyumlu ucu "models/gemini-…" biçiminde döndürür; sohbet
        # çağrısında öneksiz ad da kabul edildiği için tekilleştirip sadeleştiriyoruz.
        mid = mid.split("models/")[-1] if mid.startswith("models/") else mid
        if mid:
            kimlikler.append(mid)

    onde = [m for m in (sag.one_cikan or ()) if m in kimlikler]
    kalan = [m for m in kimlikler if m not in onde][:40]
    gruplar = []
    if onde:
        gruplar.append({"title_k": "llm.grup-onerilen", "title_kw": {"ad": sag.kimlik},
                        "options": [{"id": m, "label": m} for m in onde]})
    if kalan:
        gruplar.append({"title_k": "llm.grup-tum", "title_kw": {"ad": sag.kimlik},
                        "options": [{"id": m, "label": m} for m in kalan]})
    return gruplar or [{"title_k": "llm.grup-ad", "title_kw": {"ad": sag.kimlik},
                        "options": one_cikan}]


@router.get("/models")
@limiter.limit("30/minute")
async def list_models(request: Request, provider: str | None = None):
    """BYOK sihirbazının model listesi.

    `provider` verilmezse aktif sağlayıcı kullanılır (geriye dönük: OpenRouter).
    """
    import time as _time
    from app.services import llm_providers as _lp
    from app.services.llm import aktif_saglayici

    kimlik = (provider or aktif_saglayici() or _lp.VARSAYILAN)
    sag = _lp.kayit(kimlik)

    if kimlik == "chatgpt":
        # Resmî giriş: liste hesabın kendi kataloğundan (anahtar yok, önbellek yok).
        from app.services.chatgpt_plan.istemci import ChatGPTAsyncClient, VARSAYILAN_MODEL
        liste = await ChatGPTAsyncClient().modeller(zorla=True)
        kaynak = "live" if liste else "fallback"
        liste = liste or [VARSAYILAN_MODEL]
        return {"ok": True, "source": kaynak, "provider": "chatgpt", "recommended": VARSAYILAN_MODEL
                if VARSAYILAN_MODEL in liste else liste[0], "free_available": True,
                "groups": [{"title": "ChatGPT", "options": [{"id": m, "label": m} for m in liste]}]}

    # ── Yerel (Ollama): katalog yok, kullanıcının indirdiği modeller var ──
    # 2026-08-08 öncesinde burada `if kimlik == "ollama": kimlik = VARSAYILAN`
    # yazıyordu — yerel modda panel sessizce OpenRouter'ın listesini gösteriyordu.
    if sag is not None and sag.yerel:
        try:
            gruplar = await _yerel_modeller(sag)
            kaynak, hata = "live", None
        except Exception as e:
            gruplar = [{"title_k": "llm.grup-onerilen", "title_kw": {"ad": sag.kimlik},
                        "options": [{"id": sag.varsayilan_model,
                                     "label": sag.varsayilan_model}]}]
            kaynak, hata = "fallback", _yerel_hata_metni(sag, e)
        tum = [o["id"] for g in gruplar for o in g["options"]]
        payload = {
            "ok": True, "source": kaynak, "provider": sag.kimlik, "groups": _cevir(gruplar),
            "recommended": (sag.varsayilan_model if sag.varsayilan_model in tum
                            else (tum[0] if tum else sag.varsayilan_model)),
            "free_available": True,      # yerel model = ücret yok
            "yerel": True,
            "ucretsiz_notu": _sag_metin(sag, "ucretsiz"),
        }
        if hata:
            payload["error"] = hata
        # Yerel liste ÖNBELLEKLENMEZ: kullanıcı `ollama pull` yapıp paneli
        # tazelediğinde yeni modeli hemen görmeli (ağ maliyeti de yok, localhost).
        return {**payload, "cached": False}

    if sag is not None and sag.kimlik != "openrouter":
        now = _time.monotonic()
        onbellek = _saglayici_cache.get(sag.kimlik)
        if onbellek and (now - onbellek["at"]) < _MODELS_TTL:
            return _cikis(onbellek["payload"], cached=True)
        try:
            gruplar = await _saglayici_modelleri(sag)
            kaynak, hata = "live", None
        except Exception as e:
            gruplar = [{"title_k": "llm.grup-onerilenler", "title_kw": {"ad": sag.kimlik},
                        "options": [{"id": m, "label": m}
                                    for m in (sag.one_cikan or (sag.varsayilan_model,))]}]
            kaynak, hata = "fallback", str(e)[:160]
        tum = [o["id"] for g in gruplar for o in g["options"]]
        payload = {
            "ok": True, "source": kaynak, "provider": sag.kimlik, "groups": gruplar,
            "recommended": sag.varsayilan_model if sag.varsayilan_model in tum
                           else (tum[0] if tum else sag.varsayilan_model),
            # ⚠️ `:free` etiketi OpenRouter'a özgü. Başka sağlayıcıda "ücretsiz model"
            # diye bir işaret YOK — kota hesabın kendisinde. Uydurma bilgi vermemek
            # için burada False dönüyoruz; ücretsiz kademe bilgisi /providers'ta.
            "free_available": False,
            "ucretsiz_notu": _sag_metin(sag, "ucretsiz"),
        }
        if hata:
            payload["error"] = hata
        if kaynak == "live":
            _saglayici_cache[sag.kimlik] = {"at": now, "payload": payload}
        return _cikis(payload, cached=False)

    now = _time.monotonic()
    if _models_cache["groups"] is not None and (now - _models_cache["at"]) < _MODELS_TTL:
        return _cikis(_models_cache["groups"], cached=True)

    try:
        groups = await _fetch_live_groups()
        source = "live"
        error = None
    except Exception as e:  # ağ yok / OpenRouter down / şema değişti
        groups = _fallback_groups()
        source = "fallback"
        error = str(e)[:160]

    free_ids = [
        o["id"]
        for g in groups
        for o in g["options"]
        if o["id"].endswith(":free")
    ]
    recommended = (
        DEFAULT_FREE_MODEL if DEFAULT_FREE_MODEL in free_ids
        else (free_ids[0] if free_ids else PAID_PICKS[0]["id"])
    )

    payload = {
        "ok": True,
        "source": source,
        "provider": "openrouter",
        "groups": groups,
        "recommended": recommended,
        "free_available": bool(free_ids),
        # 🔴 2026-08-05: ücretsiz kotanın rakamları ürünün HİÇBİR yerinde yazmıyordu.
        # Kredisiz kullanıcı günde 50 isteği bitirince 429 alıyor ve bunu "Yuki
        # bozuldu" diye okuyordu. Sınırı önden söylemek, sonradan hata mesajıyla
        # açıklamaktan ucuz.
        "ucretsiz_notu": (_sag_metin(_lp.kayit("openrouter"), "ucretsiz") if _lp.kayit("openrouter") else ""),
    }
    if error:
        payload["error"] = error
    if source == "live":
        _models_cache["groups"] = payload
        _models_cache["at"] = now
    return _cikis(payload, cached=False)


# ── BYOK: OpenRouter anahtarı yaz + uygula + doğrula ────────────────────────
import os as _os
import re as _re
import threading as _threading

_env_lock = _threading.RLock()  # eşzamanlı key yazımına karşı read-modify-write'ı atomikleştirir


def _persist_env(key: str, value: str) -> None:
    """Kök .env'de `KEY=...` satırını değiştir/ekle (yorum satırlarına dokunmaz).

    Atomik: temp dosyaya yaz + os.replace → yarım yazma (disk dolu/kesinti) .env'i bozmaz.
    Lock: iki istemci aynı anda key girerse read-modify-write kaybolmasın.
    """
    from app.config import ENV_PATH
    from app.services import sirlar
    env_path = ENV_PATH   # yazılabilir dizin (paketlenmiş üründe userData; dev'de proje kökü)
    with _env_lock:
        # API anahtarı önce işletim sistemi anahtarlığına. Tutarsa `.env`'de eski
        # kopyası kalmasın — kalsaydı açılışta ortama o yüklenir, diskte düz metin kalırdı.
        if sirlar.sir_mi(key) and sirlar.kaydet(key, value):
            sirlar.env_satir_sil(env_path, [key])
            return
        lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
        for i, ln in enumerate(lines):
            s = ln.lstrip()
            if s.startswith(f"{key}=") and not s.startswith("#"):
                lines[i] = f"{key}={value}"
                break
        else:
            lines.append(f"{key}={value}")
        tmp = env_path.with_suffix(env_path.suffix + ".tmp")
        tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
        _os.replace(tmp, env_path)
        sirlar.env_izin_kis(env_path)   # anahtarlık yoksa anahtar burada: yalnız sahibi okusun


def _sag_metin(sag, alan: str) -> str:
    """Sağlayıcı metninin ÇEVİRİSİ — katalog önde, dataclass yedekte.

    (FAZ 3 · Dalga 2 · Blok 4B, 2026-09-19)

    🔴 Neden gerekti: Blok 4'te 🔑 ANAHTAR panelinin frontend metinleri
    çevrildi ve canlı tur "İngilizce ekranda Türkçe kalan: 0" dedi. Ekran
    görüntüsünde panelin yarısı hâlâ Türkçeydi — çünkü rehberin gövdesi
    frontend'den DEĞİL buradan geliyor (`ucretsiz` · `not_` · `uyari` ve
    Ollama'nın adı). Yani panel yarı çevrilmiş kalıyordu.

    🔑 Kademeli tek sahiplik (`intro-sequences.js::_catAd` ile AYNI desen):
    kaynak hâlâ `llm_providers.py` — orası ölçümün yaşadığı yer ve bir kısıt
    değişince (Ollama'nın bağlam penceresi gibi) tek yerde güncellenmeli.
    Katalog onu **çeviriyor**, yeniden yazmıyor: Türkçe değerin dataclass'la
    birebir aynı olduğunu `test_saglayici_metni_KAYNAKLA_AYNI` denetliyor.

    ⚠️ `M()` bilinmeyen anahtarda ANAHTARI döndürür, boş string değil — o
    yüzden "çeviri var mı" sorusu `cev == anahtar` ile sorulur. `if not cev`
    yazılsaydı çevirisi olmayan her sağlayıcı arayüzde
    `saglayici.groq.ucretsiz` diye görünürdü.
    """
    yedek = getattr(sag, "not_" if alan == "not" else alan, "") or ""
    anahtar = f"saglayici.{sag.kimlik}.{alan}"
    cev = M(anahtar)
    return yedek if cev == anahtar else cev


def _mask_key(k: str) -> str:
    return _lp.maskele(k)


class ApiKeyBody(BaseModel):
    key: str
    model: str | None = None
    provider: str | None = None   # yoksa "openrouter" (geriye dönük uyum)


@router.get("/providers")
@limiter.limit("60/minute")
async def list_providers(request: Request):
    """Desteklenen sağlayıcılar + hangisinin anahtarı girilmiş.

    `dogrulandi=False` olan sağlayıcı arayüzde "denenmedi" etiketiyle gösterilir.
    Bu alanı doldururken tek ölçüt vardır: **gerçek anahtarla uçtan uca denendi mi.**

    2026-08-08: liste bulut + **yerel** (Ollama). `yerel=True` olanda anahtar
    alanı gösterilmez. Hiçbir kademe kapısı yoktur — Lite kullanıcısı da görür.
    """
    from app.services.llm import aktif_saglayici
    aktif = aktif_saglayici()
    return {
        "ok": True,
        "aktif": aktif,
        "saglayicilar": [
            {
                "kimlik": s.kimlik,
                "ad": _sag_metin(s, "ad"),
                "anahtar_url": s.anahtar_url,
                "ucretsiz": _sag_metin(s, "ucretsiz"),
                "dogrulandi": s.dogrulandi,
                "toplayici": s.toplayici,
                "not": _sag_metin(s, "not"),
                "on_ek": list(s.on_ek),
                "varsayilan_model": s.varsayilan_model,
                "yerel": s.yerel,
                "uyari": _sag_metin(s, "uyari"),
                "anahtar_gerekir": not s.yerel,
                "anahtar_var": bool(_lp.anahtar(s.kimlik)),
                "maskeli": _lp.maskele(_lp.anahtar(s.kimlik)),
            }
            for s in _lp.tumu()
        ],
    }


@router.get("/key/status")
@limiter.limit("100/minute")
async def get_key_status(request: Request):
    """Anahtar ayarlı mı (maskeli) + aktif model + aktif sağlayıcı.

    `set`/`masked` alanları aktif sağlayıcıya aittir (eski istemciler bunları okuyor);
    `saglayicilar` haritası hangi firmaların anahtarının girili olduğunu verir.
    """
    from app.services.llm import get_runtime_config, aktif_saglayici
    aktif = aktif_saglayici()
    anahtar = _lp.anahtar(aktif)
    sag = _lp.kayit(aktif)
    chatgpt = aktif == "chatgpt"          # resmî girişle bağlı: anahtar yok, oturum var
    # B4 (11-14): bilgisayardaki `claude` programı (claude_code) anahtarsız — "anahtar yok / kurulum
    # gerekli" rozetleri bunu da yerel saysın (sohbet çalışırken her yer "kurulum yok" diyordu).
    claude_cli = aktif == "claude_code"
    if chatgpt:
        from app.services.chatgpt_plan import kimlik as _cg
        anahtar = "oturum" if _cg.durum().get("plan_acik") else ""
    return {
        "set": bool(anahtar),
        "masked": _lp.maskele(anahtar),
        "model": get_runtime_config().get("model"),
        "provider": aktif,
        "provider_ad": "ChatGPT" if chatgpt else (_sag_metin(sag, "ad") if sag else aktif),
        # Yerelde `set:false` normaldir — arayüz bunu "anahtar eksik" uyarısına
        # çevirmesin diye ayrı bir alan gerekiyor.
        "yerel": bool(sag and sag.yerel) or claude_cli,
        "anahtar_gerekir": not (chatgpt or claude_cli or bool(sag and sag.yerel)),
        "ucretsiz_notu": _sag_metin(sag, "ucretsiz") if sag else "",
        "saglayicilar": {k: _lp.maskele(_lp.anahtar(k)) for k in _lp.anahtarli_kimlikler()},
        # Anahtar nerede saklanıyor: "anahtarlik" (işletim sistemi) | "dosya" (şifresiz .env,
        # izin 600). Arayüz "dosya"da uyarı gösterir; metin dile göre buradan gelir.
        "depo": _sirlar.durum()["depo"],
        "depo_uyari": "" if _sirlar.durum()["depo"] == "anahtarlik" else M("llm.depo-dosya"),
    }


def _lisans_anahtarina_benziyor(k: str) -> bool:
    """Ed25519 lisans anahtarı biçimi: `<b64url gövde>.<b64url imza>` — tek nokta.

    OpenRouter anahtarları `sk-or-` ile başlar ve nokta içermez, bu yüzden
    karışma riski yok.
    """
    if "." not in k or k.startswith("sk-"):
        return False
    parcalar = k.split(".")
    return (
        len(parcalar) == 2
        and all(len(p) >= 24 for p in parcalar)
        and all(_re.fullmatch(r"[A-Za-z0-9_-]+", p) for p in parcalar)
    )




async def _anahtari_dene(sag, key: str, model: str) -> None:
    """Anahtarı sağlayıcıya karşı GERÇEKTEN dene. Başarısızsa istisna fırlatır.

    Kaydetmeden önce çalıştırılır — 2026-08-02 saha raporunun kuralı: geçersiz bir
    anahtar çalışan bir kurulumu yok etmemeli.
    """
    if sag.sdk == "anthropic":
        import anthropic as _anthropic
        istemci = _anthropic.AsyncAnthropic(api_key=key, timeout=20.0)
        await istemci.messages.create(
            model=model, max_tokens=1,
            messages=[{"role": "user", "content": "ping"}],
        )
        return

    from openai import AsyncOpenAI
    istemci = AsyncOpenAI(
        base_url=sag.base_url, api_key=key, timeout=20.0,
        default_headers=dict(sag.basliklar) or None,
    )
    await istemci.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": "ping"}],
        max_tokens=1,
    )


@router.post("/key")
@limiter.limit("10/minute")
async def set_api_key(request: Request, body: ApiKeyBody):
    """BYOK: seçilen sağlayıcının anahtarını DOĞRULA, ancak sonra kaydet + uygula.

    🔴 2026-08-02 — SAHA RAPORU (Windows 10, gerçek kullanıcı makinesi).
    Eski akış YIKICIYDI: önce `.env`'e yazıyor, runtime'a uyguluyor, EN SON test
    ediyordu. Yani **geçersiz bir anahtar, çalışan bir kurulumu yok ediyordu** ve
    yanıt yine de `ok: True` dönüyordu ("Anahtar kaydedildi ama test başarısız").

    Yaşanan: kullanıcı çalışan bir OpenRouter anahtarı girmişti; sonra **Ultra
    LİSANS anahtarını** bu kutuya yapıştırdı → çalışan anahtar ezildi → sohbet
    tamamen öldü. `fmt_ok` zaten hesaplanıyordu ama **hiçbir şeyi engellemiyordu**.

    Akış: sağlayıcı seç → lisans-anahtarı kontrolü → biçim → canlı test →
    **yalnız başarılıysa** kalıcı yazma. Başarısızsa eski anahtar olduğu gibi kalır.

    🆕 2026-08-05: `provider` alanı geldi. Verilmezse `openrouter` — eski istemciler
    (ve eski testler) aynen çalışır. Her sağlayıcının anahtarı AYRI saklanır;
    Google anahtarı girmek OpenAI anahtarını silmez.
    """
    key = (body.key or "").strip()
    if not key:
        return {"ok": False, "error": M("llm.anahtar-bos")}

    kimlik = (body.provider or "openrouter").strip()
    sag = _lp.kayit(kimlik)
    if sag is None:
        return {"ok": False, "applied": False, "hata_tipi": "saglayici",
                "error": M("llm.bilinmeyen-saglayici", kimlik=kimlik)}
    if sag.yerel:
        # Yerel sağlayıcıda anahtar yoktur. Buraya gelen bir anahtarı sessizce
        # kabul etmek, kullanıcıya "bir şey ayarladım" hissi verip hiçbir şey
        # ayarlamamak olurdu.
        return {"ok": False, "applied": False, "hata_tipi": "yerel",
                "error": M("llm.yerel-anahtar-istemez", ad=_sag_metin(sag, "ad"))}

    # ── 1) Yanlış kutu kontrolü — en sık kullanıcı hatası ────────────────
    if _lisans_anahtarina_benziyor(key):
        return {
            "ok": False, "applied": False, "fmt_ok": False, "tested": False,
            "hata_tipi": "lisans_anahtari",
            "error": M("llm.lisans-anahtari-kutusu", ad=_sag_metin(sag, "ad"),
                       url=sag.anahtar_url),
        }

    # ── 2) Biçim — yalnız ÖN EKİ BİLİNEN sağlayıcılarda ─────────────────
    # Ön eki bilinmeyen sağlayıcıda uydurma bir kalıp dayatmak, geçerli anahtarı
    # reddeden sessiz bir duvar olurdu; orada kapı zaten canlı testtir.
    fmt_ok = _lp.bicim_uygun(sag, key)
    if not fmt_ok:
        return {
            "ok": False, "applied": False, "fmt_ok": False, "tested": False,
            "hata_tipi": "bicim",
            "error": M("llm.anahtar-bicim", ad=_sag_metin(sag, "ad"), onek=sag.on_ek[0],
                       url=sag.anahtar_url),
        }

    # ── 3) KAYDETMEDEN test et — geçici istemciyle ──────────────────────
    from app.services import llm as _llm
    from app import config as _cfg

    if body.model:
        model = body.model
    elif kimlik == (_llm.get_runtime_config().get("provider") or "openrouter"):
        model = _llm.get_runtime_config().get("model") or sag.varsayilan_model
    else:
        # Sağlayıcı değişiyorsa eski modelin ID'si yeni sağlayıcıda yoktur
        # ("google/gemma-…:free" OpenAI'da 404) → kaydın varsayılanı kullanılır.
        model = sag.varsayilan_model

    try:
        await _anahtari_dene(sag, key, model)
    except Exception as e:
        # "Mevcut anahtarın korundu" yalnız GERÇEKTEN bir anahtar varken söylenir — ilk kurulumda
        # ekranda "henüz bağlı değil" yazarken bu cümle kendini yalanlıyordu (goz, 09-28)
        return {
            "ok": False, "applied": False, "fmt_ok": True, "tested": False,
            "hata_tipi": "test",
            "error": M("llm.anahtar-reddedildi" if _lp.anahtar(sag.kimlik) else "llm.anahtar-reddedildi-ilk",
                       ad=_sag_metin(sag, "ad"), sebep=str(e)[:220]),
        }

    # ── 4) Test geçti → ancak ŞİMDİ kalıcı yaz ve runtime'a uygula ──────
    try:
        _persist_env(sag.env, key)
        _persist_env("LLM_PROVIDER", sag.kimlik)
        _persist_env("LLM_MODEL", model)
    except Exception as e:
        return {"ok": False, "applied": False, "error": M("llm.env-yazilamadi", sebep=e)}

    _llm.set_provider_key(sag.kimlik, key)
    if sag.kimlik == "openrouter":
        _cfg.OPENROUTER_API_KEY = key
    elif sag.kimlik == "anthropic":
        _cfg.ANTHROPIC_API_KEY = key
    _llm.set_runtime_config(sag.kimlik, model)

    mesaj = M("llm.anahtar-calisiyor", ad=_sag_metin(sag, "ad"))
    return {"ok": True, "applied": True, "fmt_ok": True, "tested": True,
            "provider": sag.kimlik, "model": model,
            "ucretsiz_notu": _sag_metin(sag, "ucretsiz"),
            "message": mesaj, "masked": _lp.maskele(key)}


# ── Kayıtlı anahtarla servis/model seçimi — anahtarı yeniden girmeden ─────────

class SecimBody(BaseModel):
    provider: str
    model: str | None = None


@router.post("/sec")
@limiter.limit("10/minute")
async def set_secim(request: Request, body: SecimBody):
    """Anahtarı ZATEN kayıtlı bir servise geç ya da modeli değiştir — KALICI.

    🔴 2026-09-27 ( panel 8): `/config` yalnız çalışan süreci değiştiriyor
    (`set_runtime_config`), `.env`'e yazmıyor → ANAHTAR panelinden seçilen model
    yeniden başlatınca sessizce eskiye dönerdi. Anahtar yolunun kuralı burada da
    geçerli: **önce dene, geçerse yaz**; geçmezse çalışan ayar olduğu gibi kalır.
    Yerel servis (Ollama) `/yerel`'den gider — orada anahtar yok, deneme başka.
    """
    kimlik = (body.provider or "").strip()
    sag = _lp.kayit(kimlik)
    if sag is None:
        return {"ok": False, "hata_tipi": "saglayici",
                "error": M("llm.bilinmeyen-saglayici", kimlik=kimlik)}
    if sag.yerel:
        return {"ok": False, "hata_tipi": "yerel",
                "error": M("llm.yerel-anahtar-istemez", ad=_sag_metin(sag, "ad"))}
    key = _lp.anahtar(sag.kimlik)
    if not key:
        return {"ok": False, "hata_tipi": "anahtar_yok",
                "error": M("llm.secim-anahtar-yok", ad=_sag_metin(sag, "ad"))}

    from app.services import llm as _llm
    if body.model and body.model.strip():
        model = body.model.strip()
    elif sag.kimlik == (_llm.get_runtime_config().get("provider") or "openrouter"):
        model = _llm.get_runtime_config().get("model") or sag.varsayilan_model
    else:
        model = sag.varsayilan_model   # eski servisin model ID'si yenisinde yoktur

    try:
        await _anahtari_dene(sag, key, model)
    except Exception as e:
        return {"ok": False, "hata_tipi": "test",
                "error": M("llm.secim-denenemedi", ad=_sag_metin(sag, "ad"), model=model,
                           sebep=str(e)[:220])}
    try:
        _persist_env("LLM_PROVIDER", sag.kimlik)
        _persist_env("LLM_MODEL", model)
    except Exception as e:
        return {"ok": False, "error": M("llm.env-yazilamadi", sebep=e)}
    _llm.set_runtime_config(sag.kimlik, model)
    return {"ok": True, "provider": sag.kimlik, "model": model,
            "message": M("llm.secim-uygulandi", ad=_sag_metin(sag, "ad"), model=model)}


# ── Yerel sağlayıcı (Ollama) seçimi — anahtarsız yol ────────────────────────

class YerelBody(BaseModel):
    model: str | None = None
    provider: str | None = None   # yoksa tek yerel sağlayıcı


@router.post("/yerel")
@limiter.limit("10/minute")
async def set_yerel(request: Request, body: YerelBody):
    """Yerel modeli (Ollama) etkin sağlayıcı yap — anahtar yok, kademe kapısı yok.

    🔴 Neden ayrı uç: `/key` akışının tamamı bir anahtarın etrafında kurulu
    (biçim denetimi, lisans-anahtarı karışması, maskeleme). Yerelde bunların
    hiçbiri yok; oraya boş anahtarla girmek her adımı bir istisnaya çevirirdi.

    Ama **kural aynı kalır: kaydetmeden ÖNCE gerçekten dene.** Bulut tarafında
    2026-08-02'de geçersiz bir anahtar çalışan kurulumu yok etmişti; buranın
    karşılığı "Ollama kurulu değil / model indirilmemiş" hâlinde sohbeti
    sessizce öldürmektir. Ollama'ya canlı bir istek atılır, ancak geçerse
    kalıcı yazılır.
    """
    from app.services import llm as _llm

    kimlik = (body.provider or "").strip() or (
        _lp.yereller()[0].kimlik if _lp.yereller() else ""
    )
    sag = _lp.kayit(kimlik)
    if sag is None or not sag.yerel:
        return {"ok": False, "applied": False, "hata_tipi": "saglayici",
                "error": M("llm.yerel-degil", kimlik=kimlik or M("llm.bos"))}

    model = (body.model or "").strip() or sag.varsayilan_model

    # ── 1) Sunucu ayakta mı + model KURULU mu ───────────────────────────
    import httpx
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{_yerel_kok(sag)}/api/tags")
            resp.raise_for_status()
            kurulu = [
                (m.get("name") or m.get("model") or "")
                for m in (resp.json().get("models") or [])
            ]
    except Exception as e:
        return {
            "ok": False, "applied": False, "tested": False, "hata_tipi": "baglanti",
            "error": M("llm.ollama-ulasilamadi", adres=sag.base_url, teknik=str(e)[:120]),
        }

    # Ollama etiketi `:latest` eksik yazıldığında da çözer; karşılaştırmayı
    # ikisini de kabul edecek şekilde yapıyoruz.
    if model not in kurulu and f"{model}:latest" not in kurulu:
        return {
            "ok": False, "applied": False, "tested": False, "hata_tipi": "model_yok",
            "error": (M("llm.yerel-model-kurulu-degil-liste", model=model,
                        kurulu=", ".join(kurulu[:6])) if kurulu
                      else M("llm.yerel-model-kurulu-degil", model=model)),
        }

    # ── 2) Gerçek bir tamamlama iste — "kurulu" ≠ "çalışıyor" ───────────
    try:
        from openai import AsyncOpenAI
        istemci = AsyncOpenAI(base_url=sag.base_url, api_key="ollama", timeout=60.0)
        await istemci.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=1,
        )
    except Exception as e:
        return {
            "ok": False, "applied": False, "tested": False, "hata_tipi": "test",
            "error": M("llm.yerel-model-yanitsiz", model=model, sebep=str(e)[:200]),
        }

    # ── 3) Geçti → kalıcı yaz + runtime'a uygula ────────────────────────
    try:
        _persist_env("LLM_PROVIDER", sag.kimlik)
        _persist_env("LLM_MODEL", model)
        _persist_env("OLLAMA_MODEL", model)
    except Exception as e:
        return {"ok": False, "applied": False, "error": M("llm.env-yazilamadi", sebep=e)}

    _llm.set_runtime_config(sag.kimlik, model)

    return {
        "ok": True, "applied": True, "tested": True,
        "provider": sag.kimlik, "model": model, "yerel": True,
        "ucretsiz_notu": _sag_metin(sag, "ucretsiz"),
        # Ölçülmüş kısıt başarı anında da söylenir: kullanıcı bağlam penceresi
        # kırpmasını ilk biçimsiz yanıtta değil, en baştan bilsin (2026-08-08).
        "uyari": _sag_metin(sag, "uyari"),
        "message": M("llm.yerel-hazir", model=model),
    }
