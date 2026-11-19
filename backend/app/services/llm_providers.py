"""Sağlayıcı kaydı — BYOK'ta hangi firmanın anahtarı kabul edilir.

Neden bu modül var
------------------
Ürün 2026-08-05'e kadar **yalnız OpenRouter** anahtarı kabul ediyordu. Elinde
zaten OpenAI / Google / Anthropic anahtarı olan bir kullanıcı ürünü kullanamıyordu;
OpenRouter'a ayrıca kaydolmak zorundaydı. Oysa bu firmaların neredeyse tamamı
OpenAI SDK'sıyla **aynı** protokolü konuşuyor — fark yalnızca `base_url`, anahtar
biçimi ve model adları. Tek fark eden Anthropic (kendi SDK'sı; `llm.py` içinde
zaten ayrı bir yolu vardı).

🔴 Bu dosyanın kuralı: **ilan edilen yetenek ≠ ölçülen yetenek.**
`dogrulandi=True` yalnız gerçek bir anahtarla uçtan uca denenmiş sağlayıcıya
yazılır. Denenmemiş olan listede *durur* ama arayüzde "denenmedi" etiketiyle
gösterilir. 2026-08-01'de üç sabit model ID'si ölçülmeden listede durduğu için
ürün yeni kullanıcıda sessizce ölmüştü; aynı hatayı sağlayıcı ölçeğinde tekrar
etmiyoruz.

Ücretsiz kota notları (`ucretsiz`) sağlayıcının **kendi ilanıdır**, bizim
ölçümümüz değildir — metinlerde bu ayrım korunur. Tek istisna OpenRouter:
rakamları 2026-08-05'te resmî dokümandan doğrulandı.

Gizlilik: model listesi ve anahtar testi **kullanıcının kendi sağlayıcısına**
gider; bizim sunucumuza hiçbir şey gitmez. Vitrindeki "sunucumuza hiç bağlanmaz"
iddiası bozulmaz.

2026-08-08: buluta ek olarak **yerel** sağlayıcı (Ollama) da kayıtta —
`YERELLER`. Anahtar istemez, kademe kapısı yoktur (Lite dâhil). Ayrıntı aşağıda.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, replace


@dataclass(frozen=True)
class Saglayici:
    kimlik: str                     # iç ad ("openrouter") — .env ve API'de kullanılan
    ad: str                         # kullanıcıya görünen ad
    sdk: str                        # "openai" (uyumlu uç) | "anthropic" (kendi SDK'sı)
    base_url: str
    env: str                        # .env değişken adı
    anahtar_url: str                # anahtarın alındığı sayfa
    varsayilan_model: str           # anahtar testi + ilk seçim
    on_ek: tuple[str, ...] = ()     # anahtar ön eki; boşsa biçim denetimi YAPILMAZ
    one_cikan: tuple[str, ...] = () # listenin başına alınacak model ID'leri
    ucretsiz: str = ""              # ücretsiz kullanım notu (sağlayıcının ilanı)
    dogrulandi: bool = False        # gerçek anahtarla uçtan uca ölçüldü mü
    toplayici: bool = False         # OpenRouter gibi çok-modelli aracı mı
    basliklar: dict = field(default_factory=dict)
    not_: str = ""
    yerel: bool = False             # model kullanıcının kendi makinesinde koşuyor mu
    uyari: str = ""                 # ölçülmüş kısıt (kullanıcıya önden söylenir)
    uyumlu_url: str = ""            # sdk != "openai" ise sağlayıcının resmî OpenAI-uyumlu ucu
    yan_model: str = ""             # arka plan / ekip işçisi için ucuz model (boşsa aktif model)


# ──────────────────────────────────────────────────────────────────────────
# ⚠️ `on_ek` yalnız EMİN olunan sağlayıcılar için doldurulur.
# Ön ek varsa yanlış biçimli anahtar canlı teste bile gitmeden, anlaşılır bir
# mesajla reddedilir (lisans anahtarını API kutusuna yapıştırma vakası —
# 2026-08-02 saha raporu). Emin olmadığımız yerde ön ek YAZILMAZ: uydurulmuş
# bir ön ek, geçerli anahtarı reddeden sessiz bir duvar olur. Ön ek yoksa
# kapı zaten canlı testtir.
# ──────────────────────────────────────────────────────────────────────────

SAGLAYICILAR: tuple[Saglayici, ...] = (
    Saglayici(
        kimlik="openrouter", ad="OpenRouter", sdk="openai", toplayici=True,
        base_url="https://openrouter.ai/api/v1",
        env="OPENROUTER_API_KEY",
        anahtar_url="https://openrouter.ai/keys",
        varsayilan_model="google/gemma-4-26b-a4b-it:free",
        on_ek=("sk-or-",),
        ucretsiz=(
            "Ücretsiz (`:free`) modeller kredi yüklemeden çalışır. Sınır: "
            "dakikada 20, günde 50 istek. Hesabına bir kez 10$ kredi alırsan "
            "günlük sınır 1.000'e çıkar. Yeni hesap/anahtar açmak sınırı "
            "değiştirmez — kota hesap bazlı değil, genel."
        ),
        dogrulandi=True,
        basliklar={"HTTP-Referer": "https://github.com/yuki-oss/yuki",
                   "X-Title": "Yuki AI Assistant"},
        not_="Tek anahtarla yüzlerce model. Ücretsiz başlamak için en kolayı.",
    ),
    Saglayici(
        kimlik="google", ad="Google Gemini", sdk="openai",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        env="GOOGLE_API_KEY",
        anahtar_url="https://aistudio.google.com/apikey",
        varsayilan_model="gemini-3.5-flash-lite",
        on_ek=("AIza",),
        one_cikan=("gemini-3.5-flash-lite", "gemini-3.8-flash", "gemini-4-hydrogen"),
        ucretsiz="Google AI Studio anahtarının ücretsiz kullanım hakkı var (model başına "
                 "günlük/dakikalık istek sınırıyla).",
        not_="AI Studio anahtarı. Vertex AI (Google Cloud) anahtarı DEĞİL.",
    ),
    Saglayici(
        kimlik="openai", ad="OpenAI", sdk="openai",
        base_url="https://api.openai.com/v1",
        env="OPENAI_API_KEY",
        anahtar_url="https://platform.openai.com/api-keys",
        varsayilan_model="gpt-4.1-mini",
        on_ek=("sk-",),
        one_cikan=("gpt-4.1-mini", "gpt-4.1", "gpt-4o-mini"),
        ucretsiz="",
        not_="⚠ ChatGPT Plus aboneliği API değildir — platform.openai.com'da ayrıca "
             "bakiye gerekir.",
    ),
    Saglayici(
        kimlik="anthropic", ad="Anthropic (Claude)", sdk="anthropic",
        base_url="https://api.anthropic.com",
        env="ANTHROPIC_API_KEY",
        anahtar_url="https://console.anthropic.com/settings/keys",
        varsayilan_model="claude-haiku-4-5-20251001",
        on_ek=("sk-ant-",),
        # Ekip işçisi ve arka plan işleri (OpenAI SDK'sıyla konuşan yollar) bu uçtan
        # Anthropic'te kalır — eskiden OpenRouter'a düşüyordu (2026-11-12 ölçümü).
        uyumlu_url="https://api.anthropic.com/v1/",
        yan_model="claude-haiku-5-5",
        one_cikan=("claude-haiku-4-5-20251001", "claude-sonnet-4-6"),
        ucretsiz="",
        not_="⚠ Claude Pro/Max aboneliği API değildir — console.anthropic.com'da "
             "ayrıca bakiye gerekir.",
    ),
    Saglayici(
        kimlik="groq", ad="Groq", sdk="openai",
        base_url="https://api.groq.com/openai/v1",
        env="GROQ_API_KEY",
        anahtar_url="https://console.groq.com/keys",
        varsayilan_model="llama-3.3-70b-versatile",
        on_ek=("gsk_",),
        ucretsiz="Ücretsiz kullanım hakkı var (dakikalık/günlük istek ve token sınırıyla).",
        not_="Çok hızlı çıkarım. Model listesi dar.",
    ),
    Saglayici(
        kimlik="cerebras", ad="Cerebras", sdk="openai",
        base_url="https://api.cerebras.ai/v1",
        env="CEREBRAS_API_KEY",
        anahtar_url="https://cloud.cerebras.ai/",
        varsayilan_model="llama-3.3-70b",
        on_ek=("csk-",),
        ucretsiz="Ücretsiz kullanım hakkı var (günlük token sınırıyla).",
    ),
    Saglayici(
        kimlik="deepseek", ad="DeepSeek", sdk="openai",
        base_url="https://api.deepseek.com/v1",
        env="DEEPSEEK_API_KEY",
        anahtar_url="https://platform.deepseek.com/api_keys",
        varsayilan_model="deepseek-chat",
        one_cikan=("deepseek-chat", "deepseek-reasoner"),
        ucretsiz="",
        not_="Ucuz ama ücretli — kredi yüklemek gerekir.",
    ),
    Saglayici(
        kimlik="mistral", ad="Mistral", sdk="openai",
        base_url="https://api.mistral.ai/v1",
        env="MISTRAL_API_KEY",
        anahtar_url="https://console.mistral.ai/api-keys",
        varsayilan_model="mistral-small-latest",
        ucretsiz="Ücretsiz (deneysel) kullanım hakkı var.",
    ),
    Saglayici(
        kimlik="xai", ad="xAI (Grok)", sdk="openai",
        base_url="https://api.x.ai/v1",
        env="XAI_API_KEY",
        anahtar_url="https://console.x.ai/",
        varsayilan_model="grok-3-mini",
        on_ek=("xai-",),
        ucretsiz="",
    ),
    Saglayici(
        kimlik="together", ad="Together AI", sdk="openai", toplayici=True,
        base_url="https://api.together.xyz/v1",
        env="TOGETHER_API_KEY",
        anahtar_url="https://api.together.ai/settings/api-keys",
        varsayilan_model="meta-llama/Llama-3.3-70B-Instruct-Turbo",
        ucretsiz="Bazı modellerde ücretsiz kullanım sunuyor.",
    ),
    Saglayici(
        kimlik="fireworks", ad="Fireworks AI", sdk="openai", toplayici=True,
        base_url="https://api.fireworks.ai/inference/v1",
        env="FIREWORKS_API_KEY",
        anahtar_url="https://fireworks.ai/account/api-keys",
        varsayilan_model="accounts/fireworks/models/llama-v3p3-70b-instruct",
        on_ek=("fw_",),
        ucretsiz="",
    ),
    Saglayici(
        kimlik="deepinfra", ad="DeepInfra", sdk="openai", toplayici=True,
        base_url="https://api.deepinfra.com/v1/openai",
        env="DEEPINFRA_API_KEY",
        anahtar_url="https://deepinfra.com/dash/api_keys",
        varsayilan_model="meta-llama/Llama-3.3-70B-Instruct",
        ucretsiz="",
    ),
    Saglayici(
        kimlik="nebius", ad="Nebius AI Studio", sdk="openai", toplayici=True,
        base_url="https://api.studio.nebius.com/v1",
        env="NEBIUS_API_KEY",
        anahtar_url="https://studio.nebius.com/settings/api-keys",
        varsayilan_model="meta-llama/Llama-3.3-70B-Instruct",
        ucretsiz="Kayıtta deneme bakiyesi veriyor.",
    ),
    Saglayici(
        kimlik="chutes", ad="Chutes", sdk="openai", toplayici=True,
        base_url="https://llm.chutes.ai/v1",
        env="CHUTES_API_KEY",
        anahtar_url="https://chutes.ai/app/api",
        varsayilan_model="deepseek-ai/DeepSeek-V3-0324",
        on_ek=("cpk_",),
        ucretsiz="Ücretsiz kullanım hakkı var (günlük istek sınırıyla).",
    ),
)

# ──────────────────────────────────────────────────────────────────────────
# YEREL SAĞLAYICI — Ollama (2026-08-08)
#
# 🔴 Neden ayrı tuple: yukarıdaki `SAGLAYICILAR` **anahtar isteyen bulut**
# sağlayıcılarının kaydıdır; `ENV_ADLARI` / `_env_yukle` / `anahtarli_kimlikler`
# hep onun üzerinden çalışır. Ollama'yı oraya koymak `OLLAMA_MODEL`i bir "API
# anahtarı" gibi okutur ve "anahtarı var mı" sorusunu bozardı. Kayıt aynı
# dataclass, liste ayrı.
#
# **Kademe kapısı YOKTUR ve olmayacaktır** (geliştirici kararı, 2026-07-30). Vitrindeki
# *"makinende kalıyor"* cümlesi iki okuyucu tarafından "model de yerelde koşuyor"
# diye anlaşıldı. Gerçekten yerelde koşturmak isteyen kullanıcıya ücretli kademe
# göstermek o yanlış anlamayı besler → yerel sağlayıcı **Lite dâhil her kademede**
# seçilebilir. Regresyon: tests/test_yerel_saglayici.py.
#
# ⚠️ `dogrulandi=True`: 2026-08-08'de bu makinede gerçek `ollama serve` + llama3.1
# ile uçtan uca ölçüldü (model listesi + araç çağıran sohbet turu). Bu alan hâlâ
# ölçüm bildirir, ilan değil.
# ──────────────────────────────────────────────────────────────────────────

YEREL_ADRES = (os.getenv("OLLAMA_BASE_URL") or "http://127.0.0.1:11434/v1").strip()

YERELLER: tuple[Saglayici, ...] = (
    Saglayici(
        kimlik="ollama", ad="Ollama (kendi bilgisayarın)", sdk="openai", yerel=True,
        base_url=YEREL_ADRES,
        env="OLLAMA_MODEL",          # anahtar değil, model adı — yerelde anahtar yok
        anahtar_url="https://ollama.com/download",
        varsayilan_model=(os.getenv("OLLAMA_MODEL") or "llama3.1").strip(),
        # ⚠️ Arayüz bu metnin başına "💳 Ücret yok:" ekliyor — cümle "Ücret yok"la
        # başlarsa ekranda iki kez yazıyor (2026-08-08'de tarayıcıda görüldü).
        ucretsiz=(
            "kota ve istek sınırı yok, model senin bilgisayarında çalışır. "
            "Karşılığı donanım: 8B'lik bir model için ~8 GB RAM (ya da VRAM) "
            "ister ve bulut modellerinden yavaştır."
        ),
        dogrulandi=True,
        not_="Önce ollama.com/download'dan Ollama'yı kur, sonra `ollama pull llama3.1` "
             "ile bir model indir. Anahtar gerekmez.",
        # 🔴 2026-08-08 CANLI ÖLÇÜM (gerçek `ollama serve` + llama3.1:latest).
        # Boru hattı çalıştı: araç ÇAĞRILDI (`get_current_datetime`) ve doğru
        # tarih döndü. Ama Ollama sunucu log'u şunu bastı:
        #   `truncating input prompt limit=2050 prompt=4097`
        # Yuki'nin sistem promptu + 20 araç tanımı ≈ 4.100 token; varsayılan
        # bağlam penceresi bunun YARISI → model talimatın yarısını hiç görmüyor.
        # Sonuç: yanıtlar biçimsiz (bozuk `[EMOTION:…]` etiketi, ham JSON).
        # Bu bir "çalışmıyor" değil, **ayar** sorunu; ama sessiz kalırsa kullanıcı
        # bunu "Yuki bozuk" diye okur — 429'u "Yuki bozuldu" diye okuması gibi.
        uyari=(
            "Yuki'nin sistem promptu + araç tanımları ≈ 4.100 token. Ollama'nın "
            "varsayılan bağlam penceresi çoğu kurulumda bundan küçüktür ve prompt "
            "sessizce kırpılır → yanıtlar biçimsiz gelir. Sunucuyu "
            "`OLLAMA_CONTEXT_LENGTH=8192 ollama serve` ile başlat. Ayrıca küçük "
            "modeller (8B) araç çağırabilse de Yuki'nin yanıt biçimini bulut "
            "modelleri kadar tutarlı izlemez."
        ),
    ),
)

_ILE_KIMLIK = {s.kimlik: s for s in SAGLAYICILAR + YERELLER}

#: `.env`'de anahtarı aranacak tüm değişken adları (YALNIZ bulut — yerelde anahtar yok)
ENV_ADLARI = tuple(s.env for s in SAGLAYICILAR)

VARSAYILAN = "openrouter"


def uyumlu_kayit(kimlik: str | None) -> Saglayici | None:
    """Sağlayıcıyla OpenAI SDK'sı üzerinden konuşulabiliyorsa onun kaydı.

    `sdk == "openai"` → kaydın kendisi. Kendi SDK'sı olan sağlayıcı (Anthropic)
    resmî OpenAI-uyumlu ucu varsa **ve anahtarı girilmişse** o uca çevrilmiş kopya
    olarak döner. Yoksa `None` — çağıran eski yedeğe (varsayılan sağlayıcı) düşer.
    """
    s = kayit(kimlik)
    if s is None:
        return None
    if s.sdk == "openai":
        return s
    if s.uyumlu_url and anahtar(s.kimlik):
        return replace(s, sdk="openai", base_url=s.uyumlu_url)
    return None


def kayit(kimlik: str | None) -> Saglayici | None:
    """Kimlikten sağlayıcı kaydı (bulut + yerel). Bilinmeyen kimlikte None."""
    return _ILE_KIMLIK.get((kimlik or "").strip())


def hepsi() -> tuple[Saglayici, ...]:
    """Anahtar isteyen BULUT sağlayıcıları."""
    return SAGLAYICILAR


def yereller() -> tuple[Saglayici, ...]:
    """Anahtar istemeyen YEREL sağlayıcılar (Ollama)."""
    return YERELLER


def tumu() -> tuple[Saglayici, ...]:
    """Kullanıcıya sunulan tüm sağlayıcılar — bulut + yerel."""
    return SAGLAYICILAR + YERELLER


def yerel_mi(kimlik: str | None) -> bool:
    sag = kayit(kimlik)
    return bool(sag and sag.yerel)


def anahtar_gerekir(kimlik: str | None) -> bool:
    """Bu sağlayıcı için API anahtarı şart mı? Yerelde değil."""
    return not yerel_mi(kimlik)


# ──────────────────────────────────────────────────────────────────────────
# Anahtar deposu — sağlayıcı başına bir anahtar, hepsi aynı anda saklanır
#
# Neden hepsi birden: kullanıcı OpenAI'dan Google'a geçip geri dönerse
# anahtarını tekrar girmek zorunda kalmaz. Tek `LLM_API_KEY` alanı olsaydı
# geçiş her seferinde bir anahtarı silerdi — 2026-08-02'de çalışan bir anahtarın
# üstüne yazılması ürünü tamamen susturmuştu.
# ──────────────────────────────────────────────────────────────────────────

_anahtarlar: dict[str, str] = {}


def _env_yukle() -> None:
    for s in SAGLAYICILAR:
        v = (os.getenv(s.env) or "").strip()
        if v:
            _anahtarlar.setdefault(s.kimlik, v)


_env_yukle()


def anahtar(kimlik: str) -> str:
    """Sağlayıcının anahtarı (runtime > .env). Yoksa boş string."""
    return _anahtarlar.get(kimlik, "")


def anahtar_ayarla(kimlik: str, deger: str) -> None:
    """Runtime'da anahtarı güncelle. Kalıcı yazma çağıranın işi (`_persist_env`)."""
    if deger:
        _anahtarlar[kimlik] = deger
    else:
        _anahtarlar.pop(kimlik, None)


def anahtarli_kimlikler() -> list[str]:
    return [s.kimlik for s in SAGLAYICILAR if anahtar(s.kimlik)]


def bicim_uygun(s: Saglayici, key: str) -> bool:
    """Ön ek denetimi. Ön ek tanımlı değilse denetim yok → daima True."""
    if not s.on_ek:
        return True
    return any(key.startswith(p) for p in s.on_ek)


def maskele(k: str) -> str:
    if not k:
        return ""
    return (k[:8] + "…" + k[-4:]) if len(k) > 14 else (k[:3] + "…")
