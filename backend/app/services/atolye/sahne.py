"""Araştırma Sahnesi motoru — Yuki Atölye.

Kullanıcı "şunu araştır" der → Atölye kuyruğunda `sahne` türü görev koşar → bu motor web'de
arar, sonucu 6-12 BLOK (başlık · kısa metin · sayı · kaynak · varsa görsel) olarak
`SAHNE.json` + okunur `RAPOR.md` diye çalışma alanına yazar. Ön yüz (ön yüz)
blokları HALKA'nın önüne dizer.

İki motor:
  · `anthropic` — Messages API + sunucu tarafı `web_search` aracı. Ücretli (API kredisi).
  · `sahte`     — ağ yok, para yok; aynı ilerleme olaylarını ve aynı biçimi üretir.
`YUKI_SAHNE_MOTOR=sahte` (varsayılan): ağa/API'ye hiç çıkmaz. `anthropic` yalnız kullanıcı
`YUKI_SAHNE_MOTOR=anthropic` dediyse ve kendi API anahtarı tanımlıysa kullanılır.

🔴 Anahtar: yalnız AYAR ADIYLA okunur (`ANTHROPIC_API_KEY`, panel > .env > ortam). Değeri
loglanmaz, kayda yazılmaz, hata metnine girmez; `anahtar_var()` yalnız bool döner.

Harcama tavanı (araştırma başına, varsayılan `YUKI_SAHNE_TAVAN_USD`=0,50 $): sunucu tarafı
arama döngüsünün token'ı yalnız SONDA gelir — koşu ortasında kesilemez. Bu yüzden tavan
ÖNDEN uygulanır: `plan_tavan` en kötü durum tahmini tavanı aşmayacak kadar arama
(`max_uses`) ve çıktı (`max_tokens`) seçer. Koşu sonunda gerçek maliyet hesaplanır;
tavanı aştıysa kayda `tavan_asildi` düşer ve `pause_turn` devamı yapılmaz.
Fiyatlar `FIYAT` tablosunda (USD / milyon token) — ayarla ezilebilir.

Bu motor SOHBET ucu değildir: Yuki'nin araç döngüsünü (`chat_stream`) taklit etmez, araç
vermez; yalnız sunucu tarafı web aramasını kullanan tek amaçlı bir rapor üreticisidir.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

SAHNE_DOSYA = "SAHNE.json"
RAPOR_DOSYA = "RAPOR.md"
HARCAMA_DOSYA = ".sahne-harcama.jsonl"       # atölye kökünde — toplam API harcaması
BLOK_ALT, BLOK_UST = 6, 12
ARAMA_UST = 8                                # tavan ne olursa olsun en çok bu kadar arama
WEB_ARAMA_ARACI = "web_search_20250305"

# USD / milyon token: (girdi, çıktı). Model listede yoksa `_VARSAYILAN_FIYAT`.
# ⚠️ Bu sayılar Console faturasıyla karşılaştırılmadı — tahmin; `YUKI_SAHNE_FIYAT_GIRDI/CIKTI`
# ayarı tabloyu ezer.
FIYAT: dict[str, tuple[float, float]] = {
    "claude-sonnet-5-5": (3.0, 15.0),
    "claude-haiku-5-5": (1.0, 5.0),
    "claude-opus-5-5": (5.0, 25.0),
}
_VARSAYILAN_FIYAT = (3.0, 15.0)
ARAMA_FIYATI = 10.0 / 1000                   # USD / arama
# Tavan planı için en kötü durum varsayımları
_TABAN_GIRDI = 3_000                         # sistem + istek + ilk tur
_ARAMA_BASINA_GIRDI = 12_000                 # bir arama sonucunun bağlama eklediği token
CIKTI_TOKEN = 6_000
SAHTE_BEKLEME = 0.35                         # sn — sahte motorun olaylar arası beklemesi (test 0)


class SahneHatasi(Exception):
    """Motorun kalıcı hatası (biçim bozuk, anahtar yok…) — mesajda anahtar YOK."""


class Iptal(Exception):
    """DURDUR — motor ilerleme sırasında iptal jetonunu gördü."""


@dataclass
class Sonuc:
    sahne: dict
    usage: dict = field(default_factory=dict)
    maliyet_usd: float = 0.0
    tavan_asildi: bool = False


# ── ayar ─────────────────────────────────────────────────────────────
def _ayar(ad: str, varsayilan):
    try:
        import app.config as c
        v = getattr(c, ad, None)
    except Exception:
        v = None
    if v in (None, ""):
        v = os.getenv(ad, "")
    return v if v not in (None, "") else varsayilan


def _anahtar() -> str:
    """Değer yalnız istemci kurulurken kullanılır — DÖNDÜRÜLEN değeri loglama."""
    return str(_ayar("ANTHROPIC_API_KEY", "") or "").strip()


def anahtar_var() -> bool:
    return bool(_anahtar())


def model() -> str:
    return str(_ayar("YUKI_SAHNE_MODEL", "claude-sonnet-5-5"))


def tavan_usd() -> float:
    try:
        v = float(_ayar("YUKI_SAHNE_TAVAN_USD", 0.50))
    except (TypeError, ValueError):
        v = 0.50
    return max(0.01, min(v, 5.0))


def motor_adi() -> str:
    """`sahte` | `anthropic`. `anthropic` istenip anahtar yoksa sahte DEĞİL, hata: kullanıcı
    ücretli motoru açıkça istediyse sessizce sahteye düşmek yanlış sonucu gerçek sandırır."""
    secim = str(_ayar("YUKI_SAHNE_MOTOR", "sahte")).strip().lower()
    if secim == "sahte":
        return "sahte"
    if secim == "anthropic":
        if not anahtar_var():
            raise SahneHatasi("YUKI_SAHNE_MOTOR=anthropic ama ANTHROPIC_API_KEY tanımlı değil")
        return "anthropic"
    return "sahte"


# ── maliyet ──────────────────────────────────────────────────────────
def _fiyat(m: str) -> tuple[float, float]:
    g, c = FIYAT.get(m, _VARSAYILAN_FIYAT)
    try:
        g = float(_ayar("YUKI_SAHNE_FIYAT_GIRDI", g))
        c = float(_ayar("YUKI_SAHNE_FIYAT_CIKTI", c))
    except (TypeError, ValueError):
        pass
    return g, c


def maliyet(usage: dict, m: str) -> float:
    """Anthropic usage → USD. Önbellek yazımı ×1,25, okuması ×0,1 girdi fiyatı."""
    g, c = _fiyat(m)
    girdi = (usage.get("input_tokens", 0)
             + 1.25 * usage.get("cache_creation_input_tokens", 0)
             + 0.10 * usage.get("cache_read_input_tokens", 0))
    usd = girdi * g / 1e6 + usage.get("output_tokens", 0) * c / 1e6
    usd += usage.get("web_search_requests", 0) * ARAMA_FIYATI
    return round(usd, 4)


def tahmin(arama: int, m: str, cikti: int = CIKTI_TOKEN) -> float:
    """En kötü durum: her arama sonucu bağlama eklenir ve her sonraki örnekleme turu
    tüm bağlamı yeniden okur (n arama → n+1 tur)."""
    g, c = _fiyat(m)
    girdi = sum(_TABAN_GIRDI + i * _ARAMA_BASINA_GIRDI for i in range(arama + 1))
    return girdi * g / 1e6 + cikti * c / 1e6 + arama * ARAMA_FIYATI


def plan_tavan(tavan: float, m: str) -> tuple[int, int]:
    """(max_uses, max_tokens): tahmini tavanı aşmayan en çok arama. Tek arama bile
    sığmıyorsa SahneHatasi (para harcanmadan)."""
    for n in range(ARAMA_UST, 0, -1):
        if tahmin(n, m) <= tavan:
            return n, CIKTI_TOKEN
    raise SahneHatasi(f"tavan {tavan:.2f} $ tek aramaya bile yetmiyor "
                      f"(en az ≈{tahmin(1, m):.2f} $)")


# ── çıktı biçimi ─────────────────────────────────────────────────────
SISTEM = f"""Sen Yuki'nin araştırma ajanısın. Kullanıcının konusunu web aramasıyla araştır.
Araştırma bitince YALNIZ tek bir JSON nesnesi yaz (```json bloğu içinde), başka metin yazma:
{{
  "baslik": "kısa rapor başlığı (en çok 60 karakter)",
  "ozet": "2-3 cümlelik genel sonuç (en çok 300 karakter)",
  "bloklar": [
    {{"tur": "metin|sayi|liste|zaman|kiyas|gorsel",
      "baslik": "en çok 50 karakter",
      "metin": "en çok 280 karakter, somut bilgi (liste/zaman/kiyas'ta 1 kısa cümle yeter)",
      "one_cikan": "true yalnız raporun en önemli 1-2 bloğunda (ekranda büyük gösterilir)",
      "sayi": "yalnız tur=sayi: öne çıkan rakam, ör. '42%' ya da '$1,2 Mr'",
      "sayi_etiket": "rakamın ne olduğu, en çok 40 karakter",
      "seri": "isteğe bağlı, yalnız tur=sayi: aynı ölçümün zaman içindeki 3-12 değeri, sayı dizisi",
      "maddeler": "yalnız tur=liste: 2-6 kısa madde (her biri en çok 80 karakter)",
      "olaylar": "yalnız tur=zaman: 2-6 öğe [{{\"tarih\": \"2026-07\", \"metin\": \"en çok 80 karakter\"}}]",
      "satirlar": "yalnız tur=kiyas: 2-6 öğe [{{\"ad\": \"en çok 30 karakter\", \"deger\": \"ör. '48%'\"}}]",
      "kaynak": "bu bilginin alındığı arama sonucunun URL'si",
      "gorsel": "yalnız tur=gorsel ise ve arama sonucunda doğrudan bir https görsel adresi varsa"}}
  ]
}}
Kurallar: {BLOK_ALT}-{BLOK_UST} blok. Her bloğun kaynağı arama sonuçlarından birinin URL'si
olmalı; uydurma URL yazma. En az 2 blok tur=sayi olsun (gerçek rakam varsa). Türleri karıştır:
sıralı gelişme varsa zaman, birden çok seçeneğin aynı ölçüsü varsa kiyas, adım/özellik sayımı
varsa liste kullan. Türkçe yaz. Emin olmadığın bilgiyi yazma; çelişen kaynak varsa metinde belirt."""

TURLER = ("metin", "sayi", "gorsel", "liste", "zaman", "kiyas")
ONE_CIKAN_UST = 2


def _ogeler(v, n: int = 6) -> list:
    return [x for x in v if x not in (None, "")][:n] if isinstance(v, list) else []


def _seri(v) -> list[float]:
    """Sparkline için 3-12 sonlu sayı; bozuksa boş (blok yine sayı olarak kalır)."""
    out = []
    for x in _ogeler(v, 12):
        try:
            f = float(str(x).replace(",", "."))
        except ValueError:
            return []
        if f != f or f in (float("inf"), float("-inf")):
            return []
        out.append(round(f, 4))
    return out if len(out) >= 3 else []


def _tur_alanlari(b: dict, blok: dict) -> None:
    """tur'a özgü alanları süzer; yetersizse blok metne düşer (eski SAHNE.json'lar bu alanları
    hiç taşımaz — ön yüz alan yoksa düz metin çizer)."""
    tur = blok["tur"]
    if tur == "sayi":
        blok["sayi"] = _kirp(b.get("sayi"), 16)
        blok["sayi_etiket"] = _kirp(b.get("sayi_etiket"), 48)
        if not blok["sayi"]:
            blok["tur"] = "metin"
        elif s := _seri(b.get("seri")):
            blok["seri"] = s
    elif tur == "liste":
        m = [_kirp(x, 90) for x in _ogeler(b.get("maddeler")) if isinstance(x, (str, int, float))]
        if len(m) >= 2:
            blok["maddeler"] = m
        else:
            blok["tur"] = "metin"
    elif tur == "zaman":
        o = [{"tarih": _kirp(x.get("tarih"), 16), "metin": _kirp(x.get("metin"), 90)}
             for x in _ogeler(b.get("olaylar")) if isinstance(x, dict)]
        o = [x for x in o if x["tarih"] and x["metin"]]
        if len(o) >= 2:
            blok["olaylar"] = o
        else:
            blok["tur"] = "metin"
    elif tur == "kiyas":
        r = [{"ad": _kirp(x.get("ad"), 32), "deger": _kirp(x.get("deger"), 16)}
             for x in _ogeler(b.get("satirlar")) if isinstance(x, dict)]
        r = [x for x in r if x["ad"] and x["deger"]]
        if len(r) >= 2:
            blok["satirlar"] = r
        else:
            blok["tur"] = "metin"


def _json_cikar(metin: str) -> dict:
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", metin, re.S)
    ham = m.group(1) if m else None
    if ham is None:
        bas, son = metin.find("{"), metin.rfind("}")
        if bas < 0 or son <= bas:
            raise SahneHatasi("modelin çıktısında JSON yok")
        ham = metin[bas:son + 1]
    try:
        v = json.loads(ham)
    except json.JSONDecodeError as e:
        raise SahneHatasi(f"modelin JSON'u bozuk: {e.msg}") from None
    if not isinstance(v, dict):
        raise SahneHatasi("modelin JSON'u nesne değil")
    return v


def _kirp(v, n: int) -> str:
    s = " ".join(str(v or "").split())
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def _https_mi(u: str) -> bool:
    try:
        p = urlparse(u)
    except ValueError:
        return False
    return p.scheme == "https" and bool(p.netloc)


def _url_anahtar(u: str) -> str:
    p = urlparse(u)
    return (p.netloc.lower().removeprefix("www.") + p.path.rstrip("/")).lower()


def sahne_kur(ham: dict, konu: str, kaynaklar: list[dict]) -> tuple[dict, list[str]]:
    """Modelin JSON'unu süzer: alanları kırpar, kaynağı arama sonuçlarında OLMAYAN URL'yi
    düşürür (uydurma kaynak), görseli yalnız https ise tutar. (sahne, uyarılar) döner."""
    uyarilar: list[str] = []
    bilinen = {_url_anahtar(k["url"]): k for k in kaynaklar if k.get("url")}
    bloklar = []
    for b in (ham.get("bloklar") or [])[:BLOK_UST]:
        if not isinstance(b, dict) or not str(b.get("baslik") or "").strip():
            continue
        tur = b.get("tur") if b.get("tur") in TURLER else "metin"
        blok = {"tur": tur, "baslik": _kirp(b.get("baslik"), 60), "metin": _kirp(b.get("metin"), 320)}
        _tur_alanlari(b, blok)
        if (b.get("one_cikan") is True or b.get("one_cikan") == "true") and sum(x.get("one_cikan", False) for x in bloklar) < ONE_CIKAN_UST:
            blok["one_cikan"] = True
        url = str(b.get("kaynak") or "").strip()
        if url and _https_mi(url) and _url_anahtar(url) in bilinen:
            k = bilinen[_url_anahtar(url)]
            blok["kaynak"] = {"url": url, "ad": _kirp(k.get("baslik") or urlparse(url).netloc, 70),
                              "alan": urlparse(url).netloc.removeprefix("www.")}
        else:
            blok["kaynak"] = None
            uyarilar.append(f"kaynaksız blok: {blok['baslik']}" if not url
                            else f"arama sonuçlarında olmayan kaynak düşürüldü: {blok['baslik']}")
        g = str(b.get("gorsel") or "").strip()
        if tur == "gorsel" and _https_mi(g):
            blok["gorsel"] = g
        elif tur == "gorsel":
            blok["tur"] = "metin"
        bloklar.append(blok)
    sahne = {
        "konu": _kirp(konu, 300),
        "baslik": _kirp(ham.get("baslik") or konu, 70),
        "ozet": _kirp(ham.get("ozet"), 360),
        "bloklar": bloklar,
        "kaynaklar": [{"url": k["url"], "baslik": _kirp(k.get("baslik"), 120)}
                      for k in kaynaklar][:60],
    }
    if len(bloklar) < BLOK_ALT:
        uyarilar.append(f"yalnız {len(bloklar)} blok (beklenen {BLOK_ALT}-{BLOK_UST})")
    return sahne, uyarilar


def rapor_md(s: dict) -> str:
    """Diskteki okunur rapor — sahneyi yeniden açmak için SAHNE.json, okumak için bu."""
    out = [f"# {s['baslik']}", "", f"**Konu:** {s['konu']}", "", s.get("ozet") or "", ""]
    for i, b in enumerate(s["bloklar"], 1):
        out.append(f"## {i:02d} · {b['baslik']}")
        if b.get("sayi"):
            out.append(f"**{b['sayi']}** — {b.get('sayi_etiket', '')}")
        out.append(b.get("metin") or "")
        out += [f"- {m}" for m in b.get("maddeler") or []]
        out += [f"- **{o['tarih']}** — {o['metin']}" for o in b.get("olaylar") or []]
        out += [f"- {r['ad']}: **{r['deger']}**" for r in b.get("satirlar") or []]
        if b.get("gorsel"):
            out.append(f"![]({b['gorsel']})")
        if b.get("kaynak"):
            out.append(f"Kaynak: [{b['kaynak']['ad']}]({b['kaynak']['url']})")
        out.append("")
    out += ["## Kaynaklar", ""] + [f"- [{k['baslik'] or k['url']}]({k['url']})" for k in s["kaynaklar"]]
    m = s.get("meta") or {}
    out += ["", "---", f"motor {m.get('motor')} · model {m.get('model')} · "
                       f"maliyet ≈{m.get('maliyet_usd', 0):.4f} $ · {m.get('tarih')}", ""]
    return "\n".join(out)


def kaydet(kok: Path, s: dict) -> None:
    from app.services.gorev import _atomik_yaz
    _atomik_yaz(kok / SAHNE_DOSYA, s)
    (kok / RAPOR_DOSYA).write_text(rapor_md(s), encoding="utf-8")


def harcama_yaz(atolye_kok: Path, gid: str, m: str, usd: float) -> None:
    satir = {"zaman": time.strftime("%Y-%m-%dT%H:%M:%S"), "gid": gid, "model": m, "usd": usd}
    with open(atolye_kok / HARCAMA_DOSYA, "a", encoding="utf-8") as f:
        f.write(json.dumps(satir, ensure_ascii=False) + "\n")


def harcama_toplam(atolye_kok: Path) -> float:
    try:
        satirlar = (atolye_kok / HARCAMA_DOSYA).read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return 0.0
    top = 0.0
    for s in satirlar:
        try:
            top += float(json.loads(s).get("usd", 0))
        except (ValueError, AttributeError):
            continue
    return round(top, 4)


Ilerle = Callable[..., None]     # ilerle(asama=, kaynak=, blok=) — senkron, hızlı


def _iptal_mi(iptal) -> bool:
    return bool(iptal is not None and iptal.is_cancelled)


# ── sahte motor ──────────────────────────────────────────────────────
async def _sahte(konu: str, ilerle: Ilerle, iptal, bekleme: float) -> tuple[dict, list[dict], dict]:
    kaynaklar = [{"url": f"https://ornek.invalid/kaynak-{i}", "baslik": f"Örnek kaynak {i}"}
                 for i in range(1, 9)]
    ilerle(asama="hazirlik", kaynak=0, blok=0)
    for i in range(1, len(kaynaklar) + 1):
        await asyncio.sleep(bekleme)
        if _iptal_mi(iptal):
            raise Iptal()
        ilerle(asama="arama", kaynak=i, blok=0)
    bloklar = []
    rakam = ["42%", "3,1 Mr $", "18 ay", "7/10"]
    # her blok türünden örnek: ön yüzün yerleşimi sahte motorla da denenebilsin
    ek = {
        1: {"tur": "sayi", "one_cikan": True, "sayi": "42%", "sayi_etiket": "örnek pazar payı",
            "seri": [12, 18, 17, 25, 31, 36, 42]},
        3: {"tur": "liste", "maddeler": ["Birinci örnek madde", "İkinci örnek madde, biraz daha uzun",
                                         "Üçüncü örnek madde"]},
        4: {"tur": "zaman", "olaylar": [{"tarih": "2024", "metin": "Örnek başlangıç"},
                                        {"tarih": "2025-06", "metin": "Örnek ara adım"},
                                        {"tarih": "2026-10", "metin": "Örnek bugünkü durum"}]},
        6: {"tur": "kiyas", "satirlar": [{"ad": "Örnek A", "deger": "48%"}, {"ad": "Örnek B", "deger": "31%"},
                                         {"ad": "Örnek C", "deger": "21%"}]},
    }
    for i in range(1, 9):
        await asyncio.sleep(bekleme)
        if _iptal_mi(iptal):
            raise Iptal()
        sayi = i in (2, 5, 7)
        bloklar.append({
            "tur": "sayi" if sayi else "metin",
            "baslik": f"Bulgu {i:02d}",
            "metin": f"SAHTE MOTOR — '{_kirp(konu, 60)}' konusunda örnek bulgu {i}. "
                     "Gerçek araştırma değildir; ekran ve akış denemesi içindir.",
            **({"sayi": rakam[i % len(rakam)], "sayi_etiket": "örnek ölçüm"} if sayi else {}),
            **ek.get(i, {}),
            "kaynak": kaynaklar[i - 1]["url"],
        })
        ilerle(asama="yazim", kaynak=len(kaynaklar), blok=i)
    ham = {"baslik": f"Sahte rapor: {_kirp(konu, 40)}",
           "ozet": "Bu rapor sahte motorla üretildi — ağ ve para kullanılmadı.", "bloklar": bloklar}
    return ham, kaynaklar, {}


# ── anthropic motoru ─────────────────────────────────────────────────
def _blok_say(metin: str) -> int:
    return min(BLOK_UST, len(re.findall(r'"baslik"\s*:', metin)) - 1) if '"bloklar"' in metin else 0


async def _anthropic(konu: str, ilerle: Ilerle, iptal, m: str, max_uses: int, max_tokens: int,
                     tavan: float, istemci=None) -> tuple[dict, list[dict], dict]:
    if istemci is None:
        import anthropic
        istemci = anthropic.AsyncAnthropic(api_key=_anahtar(), max_retries=2, timeout=300)
    mesajlar: list[dict] = [{"role": "user", "content": f"Araştırma konusu: {konu}"}]
    araclar = [{"type": WEB_ARAMA_ARACI, "name": "web_search", "max_uses": max_uses}]
    kaynaklar: list[dict] = []
    goruldu: set[str] = set()
    usage = {"input_tokens": 0, "output_tokens": 0, "cache_creation_input_tokens": 0,
             "cache_read_input_tokens": 0, "web_search_requests": 0}
    metin = ""
    ilerle(asama="hazirlik", kaynak=0, blok=0)
    for tur in range(3):                     # pause_turn devamı en çok 2 kez
        metin = ""
        async with istemci.messages.stream(model=m, max_tokens=max_tokens, system=SISTEM,
                                           messages=mesajlar, tools=araclar) as akis:
            async for olay in akis:
                if _iptal_mi(iptal):
                    raise Iptal()
                tip = getattr(olay, "type", "")
                if tip == "content_block_start":
                    blok = olay.content_block
                    if blok.type == "server_tool_use":
                        ilerle(asama="arama", kaynak=len(kaynaklar), blok=0)
                    elif blok.type == "web_search_tool_result":
                        icerik = blok.content if isinstance(blok.content, list) else []
                        for r in icerik:
                            url = getattr(r, "url", "")
                            if url and url not in goruldu:
                                goruldu.add(url)
                                kaynaklar.append({"url": url, "baslik": getattr(r, "title", "") or ""})
                        ilerle(asama="arama", kaynak=len(kaynaklar), blok=0)
                elif tip == "content_block_delta" and getattr(olay.delta, "type", "") == "text_delta":
                    onceki = _blok_say(metin)
                    metin += olay.delta.text
                    if _blok_say(metin) != onceki:
                        ilerle(asama="yazim", kaynak=len(kaynaklar), blok=max(0, _blok_say(metin)))
            son = await akis.get_final_message()
        u = son.usage
        for k in ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"):
            usage[k] += int(getattr(u, k, 0) or 0)
        stu = getattr(u, "server_tool_use", None)
        usage["web_search_requests"] += int(getattr(stu, "web_search_requests", 0) or 0)
        metin = "".join(getattr(b, "text", "") for b in son.content if b.type == "text") or metin
        if son.stop_reason != "pause_turn" or maliyet(usage, m) >= tavan:
            break
        # Sunucu arama döngüsü duraksadı → aynı içerikle sürdür (belgelenen yol).
        mesajlar = mesajlar[:1] + [{"role": "assistant", "content": son.content}]
    return _json_cikar(metin), kaynaklar, usage


async def arastir(konu: str, ilerle: Ilerle, iptal=None, *, motor: str | None = None,
                  tavan: float | None = None, bekleme: float | None = None, istemci=None) -> Sonuc:
    """Konuyu araştırır; `Sonuc.sahne` diske yazılmaya hazırdır (meta dahil).
    İptal → `Iptal`; kalıcı sorun → `SahneHatasi`; API hataları olduğu gibi yükselir."""
    motor = motor or motor_adi()
    tavan = tavan if tavan is not None else tavan_usd()
    m = model() if motor == "anthropic" else "sahte"
    if motor == "anthropic":
        max_uses, max_tokens = plan_tavan(tavan, m)
        ham, kaynaklar, usage = await _anthropic(konu, ilerle, iptal, m, max_uses, max_tokens,
                                                 tavan, istemci)
    elif motor == "sahte":
        max_uses = 0
        ham, kaynaklar, usage = await _sahte(konu, ilerle, iptal,
                                             SAHTE_BEKLEME if bekleme is None else bekleme)
    else:
        raise SahneHatasi(f"bilinmeyen motor: {motor!r}")
    usd = maliyet(usage, m) if motor == "anthropic" else 0.0
    sahne, uyarilar = sahne_kur(ham, konu, kaynaklar)
    sahne["meta"] = {"motor": motor, "model": m, "maliyet_usd": usd, "tavan_usd": tavan,
                     "arama_tavani": max_uses, "usage": usage, "uyarilar": uyarilar,
                     "tarih": time.strftime("%Y-%m-%d %H:%M")}
    ilerle(asama="dizim", kaynak=len(kaynaklar), blok=len(sahne["bloklar"]))
    return Sonuc(sahne=sahne, usage=usage, maliyet_usd=usd, tavan_asildi=usd > tavan)
