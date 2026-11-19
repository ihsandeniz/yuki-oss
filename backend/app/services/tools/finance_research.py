"""Finansal araştırma aracı — hisse & kripto için 5-rol AI analizi.

Roller:
  1. Fiyat & Piyasa Verisi  — CoinGecko (kripto) / Yahoo Finance özeti (hisse)
  2. Haberler                — DuckDuckGo son haberler
  3. Sosyal Duyarlılık       — Reddit / forum başlıkları
  4. Analist / Hedef Fiyat   — web araması
  5. Özet (ham veri döner)   — LLM (Yuki) sentezler
"""
from __future__ import annotations

import asyncio
import re
import time
from typing import Optional

import httpx

# Kripto sembol → CoinGecko ID haritası
_CRYPTO_MAP: dict[str, str] = {
    "BTC": "bitcoin", "BITCOIN": "bitcoin",
    "ETH": "ethereum", "ETHEREUM": "ethereum",
    "SOL": "solana", "SOLANA": "solana",
    "BNB": "binancecoin",
    "XRP": "ripple",
    "ADA": "cardano",
    "DOGE": "dogecoin",
    "AVAX": "avalanche-2",
    "DOT": "polkadot",
    "MATIC": "matic-network",
    "LINK": "chainlink",
    "UNI": "uniswap",
    "ATOM": "cosmos",
    "LTC": "litecoin",
    "NEAR": "near",
    "APT": "aptos",
    "ARB": "arbitrum",
    "OP": "optimism",
    "SUI": "sui",
}

_RAPOR_ETIKETLERI = {
    "tr": {"baslik": "FİNANSAL ARAŞTIRMA RAPORU", "hisse": "HİSSE", "kripto": "KRİPTO", "kaynak": "KAYNAK",
           "rol1": "ROL 1 — FİYAT & PİYASA VERİSİ", "rol2": "ROL 2 — SON HABERLER",
           "rol3": "ROL 3 — SOSYAL DUYARLILIK", "rol4": "ROL 4 — ANALİST / HEDEF FİYAT"},
    "en": {"baslik": "FINANCIAL RESEARCH REPORT", "hisse": "STOCK", "kripto": "CRYPTO", "kaynak": "SOURCE",
           "rol1": "ROLE 1 — PRICE & MARKET DATA", "rol2": "ROLE 2 — LATEST NEWS",
           "rol3": "ROLE 3 — SOCIAL SENTIMENT", "rol4": "ROLE 4 — ANALYST / PRICE TARGET"},
}

_USDT_STRIP = re.compile(r"USDT$|BUSD$|USD$", re.IGNORECASE)


def _normalize_ticker(ticker: str) -> tuple[str, bool]:
    """Ticker'ı normalleştirir. (temiz_ticker, is_crypto) döner."""
    t = ticker.strip().upper()
    t = _USDT_STRIP.sub("", t)
    is_crypto = t in _CRYPTO_MAP
    return t, is_crypto


async def _fetch_crypto_price(ticker: str) -> str:
    coin_id = _CRYPTO_MAP.get(ticker, ticker.lower())
    url = "https://api.coingecko.com/api/v3/simple/price"
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.get(url, params={
                "ids": coin_id,
                "vs_currencies": "usd",
                "include_24hr_change": "true",
                "include_market_cap": "true",
                "include_24hr_vol": "true",
            })
            r.raise_for_status()
            data = r.json().get(coin_id, {})
        if not data:
            return f"{ticker}: Fiyat verisi alınamadı."
        price = data.get("usd", "?")
        change = data.get("usd_24h_change")
        mcap = data.get("usd_market_cap")
        vol = data.get("usd_24h_vol")
        change_str = f" ({change:+.2f}%)" if change is not None else ""
        mcap_str = f" | Market Cap: ${mcap/1e9:.2f}B" if mcap else ""
        vol_str = f" | 24h Hacim: ${vol/1e6:.1f}M" if vol else ""
        return f"Fiyat: ${price:,.4f}{change_str}{mcap_str}{vol_str}"
    except Exception as e:
        return f"Fiyat alınamadı: {e}"


async def _web_search(query: str, max_results: int = 4) -> str:
    try:
        from ddgs import DDGS

        def _run() -> list[dict]:
            with DDGS() as d:
                return list(d.text(query, max_results=max_results))

        results = await asyncio.to_thread(_run)
        if not results:
            return "Sonuç bulunamadı."
        lines = []
        for r in results:
            title = r.get("title", "")
            body = r.get("body", "")[:200]
            lines.append(f"• {title}: {body}")
        return "\n".join(lines)
    except Exception as e:
        return f"Arama başarısız: {e}"


async def research_stock(ticker: str, lang: str = "tr") -> str:
    """
    Hisse veya kripto için kapsamlı finansal araştırma raporu.

    Parametreler:
      ticker: Sembol (örn: AAPL, TSLA, BTC, ETH, SOL)
      lang:   Rapor dili — "tr" (varsayılan) veya "en"
    """
    clean, is_crypto = _normalize_ticker(ticker or "")
    if not clean:
        return "Hata: Sembol boş olamaz (ör. AAPL, BTC). Arama yapılmadı."
    # `lang` imzada vardı ama rapor başlıkları her zaman Türkçe çıkıyordu.
    etiket = _RAPOR_ETIKETLERI["en" if (lang or "").strip().lower() == "en" else "tr"]
    asset_type = etiket["kripto"] if is_crypto else etiket["hisse"]

    # 5 rol paralel çalışır
    tasks = []

    # Rol 1: Fiyat verisi
    if is_crypto:
        tasks.append(_fetch_crypto_price(clean))
    else:
        tasks.append(_web_search(f"{clean} stock price today 2026", max_results=2))

    # Rol 2: Haberler (son 7 gün)
    news_q = f"{clean} crypto news 2026" if is_crypto else f"{clean} stock news 2026"
    tasks.append(_web_search(news_q, max_results=4))

    # Rol 3: Sosyal duyarlılık
    social_q = f"{clean} reddit {'crypto' if is_crypto else 'stocks'} sentiment 2026"
    tasks.append(_web_search(social_q, max_results=3))

    # Rol 4: Analist / hedef fiyat
    analyst_q = f"{clean} {'price target prediction' if is_crypto else 'analyst price target'} 2026"
    tasks.append(_web_search(analyst_q, max_results=3))

    # Paralel çalıştır
    results = await asyncio.gather(*tasks, return_exceptions=True)

    price_data   = results[0] if not isinstance(results[0], Exception) else "Hata"
    news_data    = results[1] if not isinstance(results[1], Exception) else "Hata"
    social_data  = results[2] if not isinstance(results[2], Exception) else "Hata"
    analyst_data = results[3] if not isinstance(results[3], Exception) else "Hata"

    report = f"""=== {clean} {etiket["baslik"]} ({asset_type}) ===

[{etiket["rol1"]}]
{price_data}

[{etiket["rol2"]}]
{news_data}

[{etiket["rol3"]}]
{social_data}

[{etiket["rol4"]}]
{analyst_data}

[{etiket["kaynak"]}] Veri: CoinGecko + DuckDuckGo | Zaman: {time.strftime('%Y-%m-%d %H:%M')}
"""
    return report
