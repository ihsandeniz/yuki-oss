"""MAP panosu — harita katmanı uçları (Dalga 3 kalanı, 2026-09-18).

Kişisel `api/intel.py`'nin harita bölümünden taşındı. Kademe: **Pro** (Pro+Ultra).

🔑 **Neden GeoLibre DEĞİL bu taşındı** (geliştirici kararı 2026-09-18): dalga planı
*"GeoLibre + sismik katman"* diyordu ama ölçüm ikisinin ayrı olduğunu gösterdi.
GeoLibre (198 MB GIS tezgâhı) kişiselde **navigasyona hiç bağlanmadı** — 2026-08-21
kararının kendi ifadesiyle *"kullanım kanıtı yok, hiç insan eli değmedi"*. Sismik
katman ise GeoLibre'de değil, **bu panoda** (`earthquakes` ucu + `map-engine.js`).
Kişiselde bile kullanılmayan 198 MB'ı Pro özelliği diye satmak yerine gerçekten
kullanılan pano taşındı.

🟢 **Kullanıcıda kutudan çıkar çıkmaz çalışır:** 22 uçtan **20'si anahtarsız**
(ölçüldü). Yalnız `solar` (NASA_API_KEY) ve `cctv` (WINDY_API_KEY) dış anahtar
ister ve anahtar yoksa kendi dürüst hatasını döner — Drive gibi OAuth kurulumu
gerekmez.

⚠️ Dayanıklılık `services/map_resilience.py`'de: TTL cache + tek retry +
stale-on-error + stampede kilidi. O dosya üründe ZATEN vardı ama **hiçbir yerden
çağrılmıyordu** (ölü kod, 2026-09-18 ölçümü) — bu modülle canlandı.
"""

from __future__ import annotations

import time
from collections import deque
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
# Dönüş tipleri modül düzeyinde: `from __future__ import annotations` altında FastAPI notu bu
# modülün globals'ından çözer; çözemezse app.openapi() düşer (/openapi.json ve /docs açılmaz).
from fastapi.responses import Response, StreamingResponse

from app.mesajlar import M
from app.services.map_resilience import health_snapshot, resilient


def _izin_var() -> bool:
    """Kademe izni — **fail-closed**: entitlements patlarsa kapalı sayılır."""
    try:
        from app.services import yetki
        return bool(yetki.feature_allowed("map_panel"))
    except Exception:
        return False


def require_map() -> None:
    """MAP panosu kademe kapısı — **Pro**.

    Router düzeyinde: bu modülde 22 uç var ve uç uç yazılan kapıda bir uç
    atlanır (`api/memory.py`, 2026-08-06: 9 uçtan 4'ü kapısızdı). Yarın
    eklenen 23. katman kapıyı kendiliğinden devralır.
    """
    if not _izin_var():
        raise HTTPException(
            status_code=403,
            detail=M("harita.pro-gerekli"),
        )


router = APIRouter(dependencies=[Depends(require_map)])

#: Olay halkası — harita uçları `log_event` çağırıyor (4 yer). INTEL sekmesinin
#: `/api/events` ucu ÜRÜNE TAŞINMADI; halka yalnız teşhis için burada duruyor.
_event_log: deque[dict] = deque(maxlen=200)



# ── Vekil uçların SSRF koruması — kapı `services/adres_kapisi.py`'de (browse_web de kullanır) ──
from app.services.adres_kapisi import ozel_adres_mi as _ozel_adres_mi  # noqa: E402


def log_event(tag: str, action: str) -> None:
    """Dispatcher ve diğer servislerden çağrılır."""
    _event_log.appendleft({
        "ts":     datetime.now().strftime("%H:%M:%S"),
        "tag":    tag,
        "action": action,
    })


# ── /api/status ──────────────────────────────────────────────── #


@router.get("/api/map/config")
async def map_config() -> dict:
    """Harita sekmesi frontend yapılandırması. Mapbox public token varsa döner
    (trafikli rota + autocomplete + isochrone); yoksa boş → OSRM/Nominatim fallback."""
    from app.config import MAPBOX_TOKEN
    return {"mapbox_token": MAPBOX_TOKEN}


@router.get("/api/map/health")
async def map_health() -> dict:
    """Map veri kaynaklarının sağlık durumu (dayanıklılık katmanı kaydı)."""
    return {"sources": health_snapshot()}


@router.get("/api/map/fires")
async def proxy_fires() -> dict:
    """NASA FIRMS VIIRS aktif yangınlar (proxy + 10dk cache + stale-on-error).

    Global 24h CSV ağır (~5-7s); cache'siz her katman açılışı yeniden indirip
    timeout riski yaratıyordu.
    """
    async def _fetch() -> dict:
        import httpx
        url = "https://firms.modaps.eosdis.nasa.gov/data/active_fire/suomi-npp-viirs-c2/csv/SUOMI_VIIRS_C2_Global_24h.csv"
        async with httpx.AsyncClient(timeout=25.0) as client:
            r = await client.get(url)
            r.raise_for_status()
            txt = r.text
        lines = txt.strip().split("\n")[1:301]  # başlık satırını atla, max 300
        fires: list[dict] = []
        for line in lines:
            cols = line.split(",")
            try:
                lat = float(cols[0])
                lon = float(cols[1])
                conf = cols[8].strip() if len(cols) > 8 else "n"
                fires.append({"lat": lat, "lon": lon, "conf": conf})
            except (ValueError, IndexError):
                continue
        if not fires:
            raise RuntimeError(M("harita.firms-bos"))
        return {"fires": fires, "count": len(fires)}

    return await resilient("fires", ttl=600, fetcher=_fetch)


@router.get("/api/map/flights")
async def proxy_flights() -> dict:
    """OpenSky Network uçuş durumları (proxy + 60s cache + stale-on-error).

    Anonim OpenSky sert rate-limit'li; 60s cache istek sayısını düşürür,
    429 anında son-iyi-veri döner.
    """
    async def _fetch() -> dict:
        import httpx
        url = "https://opensky-network.org/api/states/all?lamin=-60&lomin=-180&lamax=85&lomax=180"
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.get(url)
            if r.status_code == 429:
                raise RuntimeError("rate_limited")
            r.raise_for_status()
            d = r.json()
        states = (d.get("states") or [])[:500]
        if not states:
            raise RuntimeError(M("harita.opensky-bos"))
        return {"states": states, "count": len(states)}

    return await resilient("flights", ttl=60, fetcher=_fetch, retries=0)


@router.get("/api/map/volcanoes")
async def proxy_volcanoes() -> dict:
    """USGS Volcano Hazards — izlenen yanardağlar (proxy + 1sa cache + stale)."""
    async def _fetch() -> dict:
        import httpx
        # volcanoesUS → tüm izlenen yanardağlar, lat/long/alertLevel içerir
        url = "https://volcanoes.usgs.gov/vsc/api/volcanoApi/volcanoesUS"
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get(url)
            r.raise_for_status()
            data = r.json()
        items = data if isinstance(data, list) else data.get("results", [])
        volcanoes: list[dict] = []
        for v in items:
            try:
                lat = float(v.get("lat") or v.get("latitude", 0))
                lon = float(v.get("long") or v.get("longitude", 0))
                if not lat and not lon:
                    continue
                volcanoes.append({
                    "name":    v.get("vName", "Unknown"),
                    "alert":   (v.get("alertLevel") or "Normal").capitalize(),
                    "country": "US",
                    "lat":     lat,
                    "lon":     lon,
                })
            except (KeyError, TypeError, ValueError):
                continue
        if not volcanoes:
            raise RuntimeError(M("harita.volkan-bos"))
        return {"volcanoes": volcanoes, "count": len(volcanoes)}

    return await resilient("volcanoes", ttl=3600, fetcher=_fetch)


# Hava durumu + hava kalitesi katmanlarının ortak şehir listesi
_WORLD_CITIES: list[tuple[str, float, float]] = [
    ("Istanbul", 41.0082, 28.9784), ("Ankara", 39.9334, 32.8597),
    ("London", 51.5074, -0.1278), ("Paris", 48.8566, 2.3522),
    ("Berlin", 52.5200, 13.4050), ("Madrid", 40.4168, -3.7038),
    ("Rome", 41.9028, 12.4964), ("Moscow", 55.7558, 37.6173),
    ("New York", 40.7128, -74.0060), ("Los Angeles", 34.0522, -118.2437),
    ("Tokyo", 35.6762, 139.6503), ("Beijing", 39.9042, 116.4074),
    ("Dubai", 25.2048, 55.2708), ("Mumbai", 19.0760, 72.8777),
    ("Sydney", -33.8688, 151.2093), ("Cairo", 30.0444, 31.2357),
    ("Sao Paulo", -23.5505, -46.6333), ("Lagos", 6.5244, 3.3792),
    ("Toronto", 43.6532, -79.3832), ("Seoul", 37.5665, 126.9780),
]


@router.get("/api/map/weather")
async def proxy_weather() -> dict:
    """Open-Meteo dünya şehirleri hava durumu (proxy + 10dk cache + stale)."""
    async def _fetch() -> dict:
        import asyncio
        import httpx

        async def fetch_city(client: httpx.AsyncClient, name: str, lat: float, lon: float) -> dict | None:
            try:
                url = (
                    f"https://api.open-meteo.com/v1/forecast"
                    f"?latitude={lat}&longitude={lon}"
                    f"&current_weather=true&timezone=auto"
                )
                r = await client.get(url, timeout=8.0)
                r.raise_for_status()
                d = r.json()
                cw = d.get("current_weather", {})
                return {
                    "city": name, "lat": lat, "lon": lon,
                    "temp": cw.get("temperature"), "wmo": cw.get("weathercode"),
                }
            except Exception:
                return None

        async with httpx.AsyncClient() as client:
            results = await asyncio.gather(*[fetch_city(client, n, la, lo) for n, la, lo in _WORLD_CITIES])
        cities = [c for c in results if c is not None]
        if not cities:
            raise RuntimeError(M("harita.open-meteo-sehir-yok"))
        return {"cities": cities, "count": len(cities)}

    return await resilient("weather", ttl=600, fetcher=_fetch)


@router.get("/api/map/airquality")
async def proxy_airquality() -> dict:
    """PM2.5 hava kalitesi (proxy + 15dk cache + stale).

    OPENAQ_API_KEY varsa OpenAQ v3 (yoğun istasyon ağı); yoksa Open-Meteo
    Air Quality (keyless, dünya şehirleri) — eskiden key yokken katman
    tamamen ölüydü.
    """
    from app.config import OPENAQ_API_KEY

    async def _fetch_openaq() -> dict:
        import httpx
        headers = {"X-API-Key": OPENAQ_API_KEY}
        # v3: parameter ID 2 = PM2.5, /latest endpoint
        url = "https://api.openaq.org/v3/parameters/2/latest?limit=1000"
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.get(url, headers=headers)
            r.raise_for_status()
            data = r.json()
        stations: list[dict] = []
        seen: set = set()
        for m in data.get("results", []):
            try:
                coords = m.get("coordinates") or {}
                lat = coords.get("latitude")
                lon = coords.get("longitude")
                if lat is None or lon is None:
                    continue
                key = (round(lat, 2), round(lon, 2))
                if key in seen:
                    continue
                seen.add(key)
                val = m.get("value")
                if val is None or val < 0:
                    continue
                stations.append({
                    "city":  m.get("locationName") or m.get("location") or "",
                    "lat":   lat,
                    "lon":   lon,
                    "pm25":  round(val, 1),
                })
            except (KeyError, TypeError):
                continue
        if not stations:
            raise RuntimeError(M("harita.openaq-bos"))
        return {"stations": stations, "count": len(stations), "source": "openaq"}

    async def _fetch_openmeteo() -> dict:
        import asyncio
        import httpx

        async def one(client: httpx.AsyncClient, name: str, lat: float, lon: float) -> dict | None:
            try:
                r = await client.get(
                    "https://air-quality-api.open-meteo.com/v1/air-quality",
                    params={"latitude": lat, "longitude": lon, "current": "pm2_5"},
                    timeout=8.0,
                )
                r.raise_for_status()
                val = (r.json().get("current") or {}).get("pm2_5")
                if val is None:
                    return None
                return {"city": name, "lat": lat, "lon": lon, "pm25": round(float(val), 1)}
            except Exception:
                return None

        async with httpx.AsyncClient() as client:
            results = await asyncio.gather(*[one(client, n, la, lo) for n, la, lo in _WORLD_CITIES])
        stations = [s for s in results if s is not None]
        if not stations:
            raise RuntimeError(M("harita.open-meteo-aq-sehir-yok"))
        return {"stations": stations, "count": len(stations), "source": "open-meteo"}

    fetcher = _fetch_openaq if OPENAQ_API_KEY else _fetch_openmeteo
    return await resilient("airquality", ttl=900, fetcher=fetcher)


# ── AISStream ship cache ──────────────────────────────────── #
_ship_cache: dict = {"ships": [], "ts": 0.0}


@router.get("/api/map/ships")
async def proxy_ships() -> dict:
    """AISStream.io gemi trafiği (cached REST endpoint — WebSocket cached state)."""
    global _ship_cache

    # Cache 60 saniye geçerliyse direkt dön
    if time.time() - _ship_cache["ts"] < 60 and _ship_cache["ships"]:
        return {"ships": _ship_cache["ships"], "count": len(_ship_cache["ships"]), "cached": True}

    # AISStream WebSocket bağlantısı kur, 8 saniye mesaj topla
    import json
    import asyncio
    from app.config import AISSTREAM_API_KEY

    if not AISSTREAM_API_KEY:
        return {"ships": [], "error": M("harita.ais-anahtar-yok")}

    ships: dict[str, dict] = {}

    async def _collect() -> None:
        import websockets
        subscribe = json.dumps({
            "APIKey": AISSTREAM_API_KEY,
            "BoundingBoxes": [[[-90, -180], [90, 180]]],
            "FilterMessageTypes": ["PositionReport"],
        })
        try:
            async with websockets.connect("wss://stream.aisstream.io/v0/stream", open_timeout=5) as ws:
                await ws.send(subscribe)
                deadline = asyncio.get_event_loop().time() + 8
                while asyncio.get_event_loop().time() < deadline:
                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=1.0)
                        obj = json.loads(msg)
                        pr = obj.get("Message", {}).get("PositionReport", {})
                        meta = obj.get("MetaData", {})
                        mmsi = meta.get("MMSI", "")
                        lat = pr.get("Latitude")
                        lon = pr.get("Longitude")
                        if mmsi and lat is not None and lon is not None:
                            ships[str(mmsi)] = {
                                "mmsi": mmsi,
                                "name": meta.get("ShipName", "").strip(),
                                "lat":  lat,
                                "lon":  lon,
                                "sog":  round(pr.get("Sog", 0), 1),
                                "cog":  round(pr.get("Cog", 0), 1),
                            }
                            if len(ships) >= 300:
                                break
                    except asyncio.TimeoutError:
                        continue
        except Exception:
            pass

    try:
        await asyncio.wait_for(_collect(), timeout=12)
    except Exception:
        pass

    result = list(ships.values())[:300]
    _ship_cache = {"ships": result, "ts": time.time()}
    return {"ships": result, "count": len(result)}


# ── /api/map/solar ────────────────────────────────────── #

@router.get("/api/map/solar")
async def proxy_solar() -> dict:
    """NASA DONKI güneş patlamaları — son 7 gün (proxy + 30dk cache + stale).

    DEMO_KEY IP başına 30 istek/saat — cache'siz kullanım 429'a çarpıyordu.
    .env'e NASA_API_KEY eklenirse limit 1000/saat'e çıkar.
    """
    async def _fetch() -> dict:
        import os
        import httpx
        from datetime import timedelta
        api_key = os.getenv("NASA_API_KEY", "") or "DEMO_KEY"
        end   = datetime.utcnow().strftime("%Y-%m-%d")
        start = (datetime.utcnow() - timedelta(days=7)).strftime("%Y-%m-%d")
        url = f"https://api.nasa.gov/DONKI/FLR?startDate={start}&endDate={end}&api_key={api_key}"
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get(url)
            r.raise_for_status()
            data = r.json()
        flares: list[dict] = []
        for f in (data if isinstance(data, list) else []):
            flares.append({
                "time": (f.get("beginTime") or "")[:16],
                "cls":  f.get("classType", "?"),
            })
        # 7 günde 0 patlama meşru olabilir — boş liste hata sayılmaz
        return {"flares": flares, "count": len(flares)}

    return await resilient("solar", ttl=1800, fetcher=_fetch)


# ── /api/map/stocks ───────────────────────────────────── #

_stocks_cache: dict = {}
_STOCKS_TTL = 300  # 5 dakika

@router.get("/api/map/stocks")
async def proxy_stocks() -> dict:
    """Yahoo Finance v8 — S&P500, NASDAQ, BIST100 (CORS bypass)."""
    global _stocks_cache
    if _stocks_cache and time.time() - _stocks_cache.get("ts", 0) < _STOCKS_TTL:
        return {k: v for k, v in _stocks_cache.items() if k != "ts"}

    import httpx
    SYMBOLS = {"sp500": "^GSPC", "nasdaq": "^IXIC", "bist": "XU100.IS"}
    result: dict = {}

    async def _fetch_symbol(key: str, sym: str) -> tuple[str, float | None]:
        try:
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval=1d&range=1d"
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
                r.raise_for_status()
                d = r.json()
            price = d["chart"]["result"][0]["meta"]["regularMarketPrice"]
            return key, float(price)
        except Exception:
            return key, None

    import asyncio
    pairs = await asyncio.gather(*[_fetch_symbol(k, s) for k, s in SYMBOLS.items()])
    for k, v in pairs:
        if v is not None:
            result[k] = v

    _stocks_cache = {**result, "ts": time.time()}
    return result


# ── /api/map/news ─────────────────────────────────────── #

import re as _re

_HABER_HAVUZ = 40   # kümeleme geniş havuzdan yapılır; kısaltma kümeden SONRA (`limit`)


@router.get("/api/map/news")
async def proxy_news(limit: int = 6) -> dict:
    """Google News TR RSS — son haberler (proxy + 5dk cache + stale).

    Aynı olayın başlıkları tek satıra toplanır (`services/gundem_kume.py`, `GUNDEM_KUME`):
    öğe {"title", "kaynak_sayisi", "kaynaklar"} olur. Kümeleme düşerse ham liste döner."""
    async def _fetch() -> dict:
        import httpx

        # Google News TR — güvenilir, düz <title> etiketleri (CDATA yok)
        FEED = "https://news.google.com/rss?hl=tr&gl=TR&ceid=TR:tr"

        async with httpx.AsyncClient(timeout=12.0) as client:
            r = await client.get(FEED, headers={
                "User-Agent": "Mozilla/5.0 (compatible; AliceAI/1.0)",
                "Accept": "application/rss+xml, application/xml, text/xml",
            })
            r.raise_for_status()
            xml = r.text

        # Google News başlıkları düz <title> içinde gelir (CDATA yok)
        titles = _re.findall(r"<title>(.*?)</title>", xml, _re.DOTALL)
        items: list[dict] = []
        for t in titles[1:]:          # ilk eleman feed adı
            t = t.strip()
            # HTML entity decode
            t = t.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"')
            if t and len(t) > 10 and len(items) < _HABER_HAVUZ:
                items.append({"title": t})
        if not items:
            raise RuntimeError(M("harita.haber-bos"))
        return {"items": items, "count": len(items)}

    d = await resilient("news", ttl=300, fetcher=_fetch)
    if "items" in d:
        from app.services import gundem_kume
        items = gundem_kume.isle(d["items"])[:limit]
        d = {**d, "items": items, "count": len(items)}
    return d


# ── /api/map/satellites ─────────────────────────────── #

_sat_cache: dict = {}
_SAT_TTL = 3600  # 1 saat (TLE verisi nadiren değişir)

@router.get("/api/map/satellites")
async def proxy_satellites(group: str = "visual") -> dict:
    """CelesTrak TLE uydu takımyıldızı — backend proxy, 1h cache."""
    global _sat_cache
    cached = _sat_cache.get(group)
    if cached and time.time() - cached.get("ts", 0) < _SAT_TTL:
        return {"satellites": cached["satellites"], "count": len(cached["satellites"])}

    import httpx
    import asyncio

    def _parse_tle_txt(txt: str) -> list[dict]:
        lines = [ln.strip() for ln in txt.strip().splitlines() if ln.strip()]
        sats: list[dict] = []
        i = 0
        while i + 2 < len(lines):
            name = lines[i]; tle1 = lines[i + 1]; tle2 = lines[i + 2]
            if tle1.startswith("1 ") and tle2.startswith("2 "):
                sats.append({"name": name, "tle1": tle1, "tle2": tle2})
                i += 3
            else:
                i += 1
        return sats

    satellites: list[dict] = []

    # ── Birincil: CelesTrak gp.php (GET parametreli, 403 yok) ──
    GP_GROUPS = {
        "visual":   "visual",
        "stations": "stations",
        "starlink": "starlink",
        "active":   "active",
    }
    gp_group = GP_GROUPS.get(group, "visual")
    gp_url = f"https://celestrak.org/NORAD/elements/gp.php?GROUP={gp_group}&FORMAT=tle"
    _CELESTRAK_HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "text/plain,*/*",
        "Referer": "https://celestrak.org/",
    }
    try:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            r = await client.get(gp_url, headers=_CELESTRAK_HEADERS)
            r.raise_for_status()
            satellites = _parse_tle_txt(r.text)
        if satellites:
            _sat_cache[group] = {"satellites": satellites, "ts": time.time()}
            return {"satellites": satellites, "count": len(satellites)}
    except Exception:
        pass

    # ── Fallback: tle.ivanstanojevic.me (4 sayfa × 100 = 400 uydu) ──
    IVAN_PAGES = 4
    ivan_url = "https://tle.ivanstanojevic.me/api/tle/"
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            pages = await asyncio.gather(*[
                client.get(ivan_url, params={"page": p, "limit": 100},
                           headers={"User-Agent": "Mozilla/5.0"})
                for p in range(1, IVAN_PAGES + 1)
            ], return_exceptions=True)
        for resp in pages:
            if isinstance(resp, Exception):
                continue
            try:
                resp.raise_for_status()
                for item in (resp.json().get("member") or []):
                    if item.get("line1") and item.get("line2"):
                        satellites.append({
                            "name": item.get("name", "?"),
                            "tle1": item["line1"],
                            "tle2": item["line2"],
                        })
            except Exception:
                continue
    except Exception:
        pass

    if satellites:
        _sat_cache[group] = {"satellites": satellites, "ts": time.time()}
        return {"satellites": satellites, "count": len(satellites)}

    return {"satellites": [], "error": M("harita.tle-basarisiz")}


# ── /api/map/adsb ──────────────────────────────────── #

_adsb_cache: dict = {}
_ADSB_TTL = 15  # 15 saniye (canlı trafik)

@router.get("/api/map/adsb")
async def proxy_adsb() -> dict:
    """airplanes.live ADS-B — tüm dünya uçak trafiği (CORS bypass, 15s cache)."""
    global _adsb_cache
    if _adsb_cache and time.time() - _adsb_cache.get("ts", 0) < _ADSB_TTL:
        return {"aircraft": _adsb_cache["aircraft"], "count": len(_adsb_cache["aircraft"])}

    import httpx

    # airplanes.live /v2/point → 403 olursa adsb.lol → adsb.one sırasıyla dene
    ADSB_SOURCES = [
        "https://api.adsb.lol/v2/point/39.0/35.0/500",
        "https://api.adsb.one/v2/point/39.0/35.0/500",
        "https://api.airplanes.live/v2/point/39.0/35.0/500",
    ]
    _ADSB_HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "application/json",
    }

    last_err: Exception | None = None
    d: dict = {}
    for _url in ADSB_SOURCES:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.get(_url, headers=_ADSB_HEADERS)
                r.raise_for_status()
                d = r.json()
            break
        except Exception as e:
            last_err = e
            continue

    try:
        if not d:
            raise last_err or RuntimeError(M("harita.adsb-basarisiz"))
        aircraft = d.get("ac", [])
        # Sadece gerekli alanları tut
        slim = []
        for ac in aircraft:
            lat = ac.get("lat"); lon = ac.get("lon")
            if lat is None or lon is None:
                continue
            slim.append({
                "hex":     ac.get("hex", ""),
                "flight":  (ac.get("flight") or "").strip(),
                "lat":     lat,
                "lon":     lon,
                "alt_baro": ac.get("alt_baro"),
                "gs":      ac.get("gs"),
                "track":   ac.get("track", 0),
            })
        _adsb_cache = {"aircraft": slim, "ts": time.time()}
        return {"aircraft": slim, "count": len(slim)}
    except Exception as e:
        return {"aircraft": [], "error": str(e)}


# ── /api/map/cctv ──────────────────────────────────── #

@router.get("/api/map/cctv")
async def proxy_cctv() -> dict:
    """Dünya trafik kameraları (proxy + 1sa cache + stale + kaynak izolasyonu).

    2026-07-06 onarımı: 7 kaynaktan 6'sı sessizce ölmüştü (sadece Londra
    dönüyordu). NYC dataset 404 → nyctmc API'ye; Finlandiya 406 →
    Digitraffic-User+gzip header; HK 404 → data.gov.hk yeni XML (lat/lon
    hazır); NV parse-0 + UK webtris 404 → kaldırıldı (yeni kaynak FAZ 1).
    Her kaynak kendi timeout'uyla izole — biri yavaşsa diğerlerini
    öldürmez (eski global wait_for hepsini birden iptal ediyordu).
    Yanıtta "sources" alanı kaynak başına sayıyı verir → ölü kaynak görünür.
    """
    async def _fetch() -> dict:
        import asyncio as _asyncio
        import httpx
        import xml.etree.ElementTree as ET

        async def _nyc(client: httpx.AsyncClient) -> list:
            # NYC TMC resmi API — eski Socrata dataset'i (bugh-k6nf) 404 oldu
            out: list = []
            r = await client.get("https://webcams.nyctmc.org/api/cameras", timeout=12.0)
            r.raise_for_status()
            for cam in r.json():
                try:
                    cid = cam.get("id", "")
                    lat = float(cam.get("latitude", 0))
                    lon = float(cam.get("longitude", 0))
                    if not cid or not lat or not lon or cam.get("isOnline") in (False, "false"):
                        continue
                    out.append({"name": cam.get("name", cid), "city": "New York",
                                "lat": lat, "lon": lon,
                                "img_url": f"https://webcams.nyctmc.org/api/cameras/{cid}/image"})
                except (KeyError, ValueError, TypeError):
                    continue
            return out[:200]

        async def _tfl(client: httpx.AsyncClient) -> list:
            out: list = []
            r = await client.get("https://api.tfl.gov.uk/Place/Type/JamCam", timeout=15.0)
            r.raise_for_status()
            for cam in r.json():
                try:
                    img = next((p["value"] for p in cam.get("additionalProperties", []) if p.get("key") == "imageUrl"), "")
                    if not img:
                        continue
                    out.append({"name": cam.get("commonName", "London Cam"), "city": "London",
                                "lat": float(cam["lat"]), "lon": float(cam["lon"]), "img_url": img})
                except (KeyError, ValueError, TypeError):
                    continue
            return out

        async def _finland(client: httpx.AsyncClient) -> list:
            # Digitraffic: gzip + tanıtıcı header ZORUNLU (406 fix, 2026-07-06)
            out: list = []
            r = await client.get(
                "https://tie.digitraffic.fi/api/weathercam/v1/stations",
                headers={"Digitraffic-User": "AliceAI/1.0", "Accept-Encoding": "gzip"},
                timeout=12.0,
            )
            r.raise_for_status()
            for feat in r.json().get("features", [])[:200]:
                try:
                    coords = feat.get("geometry", {}).get("coordinates", [])
                    if len(coords) < 2:
                        continue
                    lon, lat = float(coords[0]), float(coords[1])
                    props = feat.get("properties", {})
                    sid = props.get("id", "")
                    presets = props.get("presets") or []
                    img = next((p["imageUrl"] for p in presets if p.get("imageUrl")), "")
                    if not img and sid:
                        # stations listesinde preset yoksa ilk preset konvansiyonu: C<id>01
                        img = f"https://weathercam.digitraffic.fi/{sid}01.jpg"
                    if not img:
                        continue
                    out.append({"name": props.get("name", "Finland Road Cam"), "city": "Finland",
                                "lat": lat, "lon": lon, "img_url": img})
                except (KeyError, ValueError, TypeError):
                    continue
            return out

        async def _hongkong(client: httpx.AsyncClient) -> list:
            # Yeni konum: data.gov.hk (eski resource.data.one.gov.hk/td/en/cctv_list.xml 404)
            out: list = []
            r = await client.get(
                "https://static.data.gov.hk/td/traffic-snapshot-images/code/Traffic_Camera_Locations_En.xml",
                timeout=12.0,
            )
            r.raise_for_status()
            root = ET.fromstring(r.text)
            for cam in root.findall(".//image"):
                try:
                    lat = float(cam.findtext("latitude", "0"))
                    lon = float(cam.findtext("longitude", "0"))
                    url = (cam.findtext("url") or "").strip()
                    if not lat or not lon or not url:
                        continue
                    out.append({"name": (cam.findtext("description") or "HK Cam").strip(),
                                "city": "Hong Kong", "lat": lat, "lon": lon, "img_url": url})
                except (ValueError, TypeError, AttributeError):
                    continue
            return out

        async def _california(client: httpx.AsyncClient) -> list:
            out: list = []

            async def _fetch_district(district: int) -> list:
                local: list = []
                try:
                    pad = str(district).zfill(2)
                    r = await client.get(
                        f"https://cwwp2.dot.ca.gov/data/d{district}/cctv/cctvStatusD{pad}.json",
                        timeout=12.0,  # 8s yetmiyordu — D3 tek başına ~6s
                    )
                    if r.status_code != 200:
                        return local
                    raw = r.json().get("data", [])
                    items = raw.get("items", []) if isinstance(raw, dict) else raw  # "data" doğrudan liste
                    for cam in items[:50]:
                        try:
                            c = cam.get("cctv", cam)  # şema: {"cctv": {...}} sarmalı
                            loc = c.get("location", {})
                            lat = float(loc.get("latitude", 0))
                            lon = float(loc.get("longitude", 0))
                            img = (c.get("imageData", {}) or {}).get("static", {}).get("currentImageURL", "") \
                                  or (c.get("imageData", {}) or {}).get("url", "")
                            if not lat or not lon or not img:
                                continue
                            local.append({"name": loc.get("locationName", f"CA-D{district} Cam"),
                                          "city": "California", "lat": lat, "lon": lon, "img_url": img})
                        except (KeyError, ValueError, TypeError):
                            continue
                except Exception:
                    pass
                return local

            results = await _asyncio.gather(*[_fetch_district(d) for d in range(1, 13)])
            for rr in results:
                out.extend(rr)
            return out

        async def _windy_tr(client: httpx.AsyncClient) -> list:
            # Windy Webcams v3 — TR kameraları (WINDY_API_KEY .env'e eklenince aktifleşir)
            # Kayıt: https://api.windy.com/webcams — ücretsiz tier yeterli.
            # NOT: key olmadan canlı doğrulanamadı (403 header testi yapıldı);
            # key gelince alan adları farklıysa burayı uyarla.
            import os as _os
            key = _os.getenv("WINDY_API_KEY", "")
            out: list = []
            r = await client.get(
                "https://api.windy.com/webcams/api/v3/webcams",
                params={"countries": "TR", "limit": 50, "include": "location,images"},
                headers={"x-windy-api-key": key},
                timeout=15.0,
            )
            r.raise_for_status()
            for cam in (r.json().get("webcams") or []):
                try:
                    loc = cam.get("location") or {}
                    lat = float(loc.get("latitude", 0))
                    lon = float(loc.get("longitude", 0))
                    imgs = cam.get("images") or {}
                    img = (imgs.get("current") or {}).get("preview", "")
                    if not lat or not lon or not img:
                        continue
                    out.append({"name": cam.get("title", "TR Cam"), "city": "Türkiye",  # i18n-istisna: veri (kamera konumu, kaynak adı)
                                "lat": lat, "lon": lon, "img_url": img})
                except (KeyError, ValueError, TypeError):
                    continue
            return out

        def _castlerock(city: str, base: str, cap: int = 400):
            # Castle Rock 511 sistemleri (Ontario/Alberta/...) aynı API şeklini paylaşır
            async def _fetch_cr(client: httpx.AsyncClient) -> list:
                out: list = []
                r = await client.get(f"{base}/api/v2/get/cameras?format=json", timeout=15.0)
                r.raise_for_status()
                for cam in r.json():
                    try:
                        lat = float(cam.get("Latitude", 0))
                        lon = float(cam.get("Longitude", 0))
                        views = cam.get("Views") or []
                        img = next((v.get("Url", "") for v in views
                                    if v.get("Url") and v.get("Status") != "Disabled"), "")
                        if not lat or not lon or not img:
                            continue
                        out.append({"name": cam.get("Location") or cam.get("Roadway") or f"{city} Cam",
                                    "city": city, "lat": lat, "lon": lon, "img_url": img})
                        if len(out) >= cap:
                            break
                    except (KeyError, ValueError, TypeError):
                        continue
                return out
            return _fetch_cr

        _HDR = {"User-Agent": "Mozilla/5.0 (compatible; AliceAI/1.0)", "Accept": "application/json"}
        SOURCES = {
            "New York":  _nyc,
            "London":    _tfl,
            "Finland":   _finland,
            "Hong Kong": _hongkong,
            "California": _california,
            "Ontario":   _castlerock("Ontario", "https://511on.ca"),
            "Alberta":   _castlerock("Alberta", "https://511.alberta.ca"),
        }
        import os as _os
        if _os.getenv("WINDY_API_KEY", ""):
            SOURCES["Türkiye"] = _windy_tr  # i18n-istisna: veri (kaynak adı / sözlük anahtarı)

        cameras: list[dict] = []
        per_source: dict[str, int | str] = {}
        async with httpx.AsyncClient(headers=_HDR, follow_redirects=True) as client:
            async def _guard(name: str, fn) -> None:
                # Kaynak izolasyonu: her kaynak kendi hatasını taşır,
                # global "hepsi ya da hiçbiri" timeout YOK
                try:
                    batch = await _asyncio.wait_for(fn(client), timeout=20.0)
                    cameras.extend(batch)
                    per_source[name] = len(batch)
                except Exception as e:
                    per_source[name] = f"hata: {str(e)[:60] or type(e).__name__}"

            await _asyncio.gather(*[_guard(n, f) for n, f in SOURCES.items()])

        if not cameras:
            raise RuntimeError(M("harita.cctv-basarisiz", kaynaklar=per_source))
        return {"cameras": cameras, "count": len(cameras), "sources": per_source}

    return await resilient("cctv", ttl=3600, fetcher=_fetch)

# ── Vekil uçlar (v0.8.1 güvenlik yaması, denetim C1 + H4) ──────────────────── #
# İki vekil de yabancı bir sunucunun yanıtını YUKI'NİN KENDİ ADRESİNDEN sunar. Eski hâli:
#   · upstream `Content-Type`'ı aynen dönüyordu → `text/html` gelirse saldırganın sayfası
#     127.0.0.1:8791 kökeninde çalışıyordu (C1)
#   · SSRF kapısı yalnız İLK adreste, `follow_redirects=True` → 302 ile yerel ağa/kendine (H4)
#   · `Access-Control-Allow-Origin: *` → her site yanıtı okuyabiliyordu
# Şimdi: yönlendirmeyi kendimiz izliyoruz (her adımda `_ozel_adres_mi`), yalnız görüntü/akış
# türleri geçiyor, yanıt `CSP: sandbox` taşıyor, ACAO yok (arayüz aynı kökenden <img> ile yükler).
_VEKIL_TURLER = ("image/jpeg", "image/png", "image/gif", "image/webp", "image/avif", "image/bmp",
                 "multipart/x-mixed-replace", "video/", "application/vnd.apple.mpegurl",
                 "application/x-mpegurl", "audio/mpegurl")
_VEKIL_YONLENDIRME = 5
_VEKIL_UA = {"User-Agent": "Mozilla/5.0 (compatible; AliceAI/1.0)"}
_VEKIL_BASLIK = {
    "Content-Security-Policy": "sandbox; default-src 'none'; img-src 'self' data:; media-src 'self'",
    "X-Content-Type-Options": "nosniff",
}


def _vekil_tur_izinli(ct: str) -> bool:
    """`image/svg+xml` BİLEREK yok: SVG doğrudan açıldığında betik koşturur."""
    t = (ct or "").split(";", 1)[0].strip().lower()
    return bool(t) and any(t == x or (x.endswith("/") and t.startswith(x)) for x in _VEKIL_TURLER)


def _imza_turu(govde: bytes) -> str | None:
    """Tür başlığı göndermeyen/yanlış gönderen kameralar için: baytın kendisinden görüntü türü."""
    if govde[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if govde[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if govde[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if govde[:4] == b"RIFF" and govde[8:12] == b"WEBP":
        return "image/webp"
    return None


async def _vekil_ac(client, url: str, tur_denetimi: bool = True):
    """GET'i yönlendirmeleri ELLE izleyerek aç. (yanıt, None) ya da (None, hata_kodu).
    Yanıt akış modunda açıktır — çağıran kapatır."""
    from urllib.parse import urljoin
    for _ in range(_VEKIL_YONLENDIRME + 1):
        if _ozel_adres_mi(url):
            return None, 400                     # SSRF kapısı — HER adımda (fail-closed)
        istek = client.build_request("GET", url, headers=_VEKIL_UA)
        resp = await client.send(istek, stream=True, follow_redirects=False)
        if resp.is_redirect:
            hedef = resp.headers.get("location", "")
            await resp.aclose()
            if not hedef:
                return None, 502
            url = urljoin(url, hedef)
            continue
        if resp.status_code >= 400:
            await resp.aclose()
            return None, 502
        if tur_denetimi and not _vekil_tur_izinli(resp.headers.get("content-type", "")):
            await resp.aclose()
            return None, 415                     # HTML/JS/SVG… Yuki'nin kökeninde sunulmaz
        return resp, None
    return None, 508                             # yönlendirme döngüsü


@router.get("/api/cctv/img")
async def proxy_cctv_image(url: str) -> Response:
    """CCTV snapshot vekili — tek kare."""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp, kod = await _vekil_ac(client, url, tur_denetimi=False)
            if kod:
                return Response(status_code=kod)
            try:
                govde = await resp.aread()
                ct = resp.headers.get("content-type", "")
            finally:
                await resp.aclose()
        if not _vekil_tur_izinli(ct):
            ct = _imza_turu(govde)               # başlık yok/yanlış → baytın imzası; HTML'in imzası yok
            if not ct:
                return Response(status_code=415)
        return Response(content=govde, media_type=ct,
                        headers={"Cache-Control": "no-cache", **_VEKIL_BASLIK})
    except Exception:
        return Response(status_code=502)


# ── /api/stream/proxy ──────────────────────────────── #

@router.get("/api/stream/proxy")
async def stream_proxy(url: str) -> Response:
    """MJPEG / JPEG akış vekili — gerçek zamanlı.

    MJPEG (multipart/x-mixed-replace) kameralar için tarayıcı <img> içinde
    canlı video olarak oynatır. Snapshot kameralar için tek kare döner.
    """
    from starlette.background import BackgroundTask
    import httpx

    client = httpx.AsyncClient(timeout=httpx.Timeout(connect=8.0, read=60.0, write=8.0, pool=8.0))
    try:
        resp, kod = await _vekil_ac(client, url)
    except Exception:
        await client.aclose()
        return Response(status_code=502)
    if kod:
        await client.aclose()
        return Response(status_code=kod)

    async def _pipe():
        try:
            async for chunk in resp.aiter_bytes(chunk_size=4096):
                yield chunk
        except Exception:
            return

    async def _kapat():
        await resp.aclose()
        await client.aclose()

    return StreamingResponse(
        _pipe(),
        media_type=resp.headers.get("content-type", "image/jpeg"),
        headers={
            "Cache-Control": "no-cache, no-store",
            "X-Accel-Buffering": "no",   # nginx proxy buffering'i kapat
            **_VEKIL_BASLIK,
        },
        background=BackgroundTask(_kapat),
    )


# ── /api/map/asteroids ─────────────────────────────────────────── #

_asteroid_cache: dict = {}
_ASTEROID_TTL = 3600  # 1 saat

@router.get("/api/map/asteroids")
async def map_asteroids() -> dict:
    """NASA NeoWs — Dünya'ya yakın geçen asteroidler (1h cache)."""
    global _asteroid_cache
    if _asteroid_cache and time.time() - _asteroid_cache.get("ts", 0) < _ASTEROID_TTL:
        return {"asteroids": _asteroid_cache["asteroids"], "count": len(_asteroid_cache["asteroids"])}

    import httpx
    from datetime import date, timedelta

    today = date.today().isoformat()
    end   = (date.today() + timedelta(days=7)).isoformat()
    asteroids: list[dict] = []

    import os as _os
    _nasa_key = _os.environ.get("NASA_API_KEY", "DEMO_KEY")

    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            r = await client.get(
                "https://api.nasa.gov/neo/rest/v1/feed",
                params={"start_date": today, "end_date": end, "api_key": _nasa_key},
                headers={"User-Agent": "Mozilla/5.0 (compatible; AliceAI/1.0)"},
            )
            r.raise_for_status()
            data = r.json()
            for day_list in data.get("near_earth_objects", {}).values():
                for neo in day_list:
                    try:
                        approach = neo.get("close_approach_data", [{}])[0]
                        miss_km  = float(approach.get("miss_distance", {}).get("kilometers", 0))
                        vel_kms  = float(approach.get("relative_velocity", {}).get("kilometers_per_second", 0))
                        diam_min = float(neo["estimated_diameter"]["kilometers"]["estimated_diameter_min"])
                        diam_max = float(neo["estimated_diameter"]["kilometers"]["estimated_diameter_max"])
                        asteroids.append({
                            "id":        neo.get("id", ""),
                            "name":      neo.get("name", "Unknown"),
                            "hazardous": neo.get("is_potentially_hazardous_asteroid", False),
                            "diam_min":  round(diam_min, 4),
                            "diam_max":  round(diam_max, 4),
                            "miss_km":   round(miss_km, 0),
                            "vel_kms":   round(vel_kms, 2),
                            "date":      approach.get("close_approach_date", today),
                            "url":       neo.get("nasa_jpl_url", ""),
                        })
                    except (KeyError, ValueError, TypeError, IndexError):
                        continue
    except Exception:
        pass

    # miss_km'ye göre sırala (en yakın önce)
    asteroids.sort(key=lambda x: x["miss_km"])
    _asteroid_cache = {"asteroids": asteroids, "ts": time.time()}
    return {"asteroids": asteroids, "count": len(asteroids)}


# ── /api/map/military ──────────────────────────────────────────── #

@router.get("/api/map/military")
async def map_military() -> dict:
    """GDELT ham 15dk export feed — son ~1 saatin çatışma olayları (30dk cache + stale).

    Eski GDELT geo v2 API tamamen kaldırıldı (404, 2026-07-06 tespiti).
    Yeni kaynak: data.gdeltproject.org/gdeltv2/ 15 dakikalık export CSV.zip
    dosyaları — CAMEO EventRootCode 18/19/20 (saldırı/çatışma/kitlesel şiddet)
    + ActionGeo koordinatlı satırlar olay noktasına dönüşür.
    """
    async def _fetch() -> dict:
        import asyncio as _asyncio
        import csv
        import io
        import zipfile
        from datetime import timedelta

        import httpx

        # CAMEO EventCode → harita kategorisi
        def _category(code: str) -> str:
            if code.startswith("195"):
                return "airstrike"   # aerial weapons
            if code.startswith("194"):
                return "missile"     # artillery/tank
            if code.startswith("20"):
                return "ground"      # mass violence
            return "ground"

        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get("http://data.gdeltproject.org/gdeltv2/lastupdate.txt")
            r.raise_for_status()
            latest_url = r.text.split("\n")[0].split()[-1]
            if not latest_url.endswith(".export.CSV.zip"):
                raise RuntimeError(M("harita.gdelt-format"))
            # Son 4 export (1 saatlik pencere) — dosya adları 15dk gridinde
            base = latest_url.rsplit("/", 1)[0]
            stamp = latest_url.rsplit("/", 1)[1].split(".")[0]  # YYYYMMDDHHMMSS
            t0 = datetime.strptime(stamp, "%Y%m%d%H%M%S")
            urls = [f"{base}/{(t0 - timedelta(minutes=15 * i)).strftime('%Y%m%d%H%M%S')}.export.CSV.zip"
                    for i in range(4)]

            async def _one(u: str) -> list[list[str]]:
                try:
                    rr = await client.get(u)
                    rr.raise_for_status()
                    zf = zipfile.ZipFile(io.BytesIO(rr.content))
                    name = zf.namelist()[0]
                    text = zf.read(name).decode("latin-1", errors="replace")
                    return list(csv.reader(io.StringIO(text), delimiter="\t"))
                except Exception:
                    return []

            batches = await _asyncio.gather(*[_one(u) for u in urls])

        got_any = any(batches)
        events: list[dict] = []
        seen: set = set()
        for rows in batches:
            for row in rows:
                try:
                    if len(row) < 61 or row[28] not in ("18", "19", "20"):
                        continue  # 28 = EventRootCode
                    lat, lon = row[56], row[57]  # ActionGeo_Lat/Long
                    if not lat or not lon:
                        continue
                    key = (round(float(lat), 1), round(float(lon), 1))
                    if key in seen:
                        continue
                    seen.add(key)
                    place = row[52] or "Unknown"   # ActionGeo_Fullname
                    events.append({
                        "name":     place.split(",")[0][:60],
                        "lat":      float(lat),
                        "lon":      float(lon),
                        "category": _category(row[26]),
                        "mentions": int(row[31] or 1),   # NumMentions
                        "snippet":  f"{place} — kaynak: {row[60][:120]}",
                    })
                    if len(events) >= 250:
                        break
                except (ValueError, IndexError):
                    continue

        if not got_any:
            raise RuntimeError(M("harita.gdelt-indirilemedi"))
        return {"events": events, "count": len(events)}

    return await resilient("military", ttl=1800, fetcher=_fetch)


# ── /api/map/livestreams — Dünya canlı yayın kameraları ──────── #
# Küratörlü 24/7 şehir webcam listesi (YouTube embed ID'leri)

_LIVESTREAMS: list[dict] = [
    # Kuzey Amerika
    {"name": "Times Square NYC",        "city": "New York, USA",       "lat":  40.7580, "lon":  -73.9855, "video_id": "VTFmFpiqRCQ", "category": "city"},
    {"name": "Hollywood Walk of Fame",  "city": "Los Angeles, USA",    "lat":  34.1016, "lon": -118.3267, "video_id": "1EiC9bvVGnk", "category": "city"},
    {"name": "Fremont Street",          "city": "Las Vegas, USA",      "lat":  36.1699, "lon": -115.1398, "video_id": "SBmBBCxHQCE", "category": "city"},
    {"name": "Chicago Riverwalk",       "city": "Chicago, USA",        "lat":  41.8858, "lon":  -87.6255, "video_id": "nx_RxC6YZdI", "category": "city"},
    {"name": "Niagara Falls",           "city": "Niagara Falls, CA",   "lat":  43.0799, "lon":  -79.0747, "video_id": "F5xE9DhLmXE", "category": "nature"},
    # Avrupa
    {"name": "Eiffel Tower",            "city": "Paris, France",       "lat":  48.8584, "lon":    2.2945, "video_id": "ByXs5CHAMQU", "category": "landmark"},
    {"name": "Trafalgar Square",        "city": "London, UK",          "lat":  51.5080, "lon":   -0.1281, "video_id": "AdUw5RdyZxI", "category": "city"},
    {"name": "Colosseum",               "city": "Rome, Italy",         "lat":  41.8902, "lon":   12.4922, "video_id": "YhbDFp2KTCA", "category": "landmark"},
    {"name": "Sagrada Familia",         "city": "Barcelona, Spain",    "lat":  41.4036, "lon":    2.1744, "video_id": "JEOgGhQiSnc", "category": "landmark"},
    {"name": "Brandenburg Gate",        "city": "Berlin, Germany",     "lat":  52.5163, "lon":   13.3777, "video_id": "X60E_MEiG9g", "category": "landmark"},
    {"name": "Rijksmuseum",             "city": "Amsterdam, NL",       "lat":  52.3600, "lon":    4.8852, "video_id": "GCbf0VMdBT4", "category": "city"},
    {"name": "Bergen Bryggen Wharf",    "city": "Bergen, Norway",      "lat":  60.3975, "lon":    5.3244, "video_id": "T4ByWIHmN1A", "category": "harbor"},
    {"name": "Helsinki Senate Square",  "city": "Helsinki, Finland",   "lat":  60.1699, "lon":   24.9520, "video_id": "H_1oqPvMBLs", "category": "city"},
    {"name": "Prague Old Town Square",  "city": "Prague, Czechia",     "lat":  50.0875, "lon":   14.4214, "video_id": "BNmqCXLrGxY", "category": "city"},
    # Asya & Pasifik
    {"name": "Shibuya Crossing",        "city": "Tokyo, Japan",        "lat":  35.6598, "lon":  139.7006, "video_id": "ZHedqVGfyNI", "category": "city"},
    {"name": "Marina Bay",              "city": "Singapore",           "lat":   1.2842, "lon":  103.8606, "video_id": "8OiABVlI9dU", "category": "city"},
    {"name": "Victoria Harbour",        "city": "Hong Kong",           "lat":  22.2855, "lon":  114.1577, "video_id": "Kxm5RAD_Zzo", "category": "harbor"},
    {"name": "Sydney Opera House",      "city": "Sydney, Australia",   "lat": -33.8568, "lon":  151.2153, "video_id": "uo3N9oHfp38", "category": "landmark"},
    {"name": "Bali Rice Terraces",      "city": "Bali, Indonesia",     "lat":  -8.4095, "lon":  115.1888, "video_id": "1X1hMIqxjiM", "category": "nature"},
    # Orta Doğu & Afrika
    {"name": "Dubai Marina Skyline",    "city": "Dubai, UAE",          "lat":  25.0805, "lon":   55.1403, "video_id": "t8ZXlMCJwwY", "category": "city"},
    {"name": "Petra Treasury",          "city": "Petra, Jordan",       "lat":  30.3285, "lon":   35.4444, "video_id": "4TvBHk5KLSU", "category": "landmark"},
    # Güney Amerika
    {"name": "Christ the Redeemer",     "city": "Rio de Janeiro, BR",  "lat": -22.9519, "lon":  -43.2105, "video_id": "gxN0Yx_BOVA", "category": "landmark"},
    {"name": "Buenos Aires Obelisco",   "city": "Buenos Aires, AR",    "lat": -34.6037, "lon":  -58.3816, "video_id": "QFhIzORlFTQ", "category": "city"},
    # Türkiye
    {"name": "Galata Tower",            "city": "Istanbul, TR",        "lat":  41.0256, "lon":   28.9744, "video_id": "z35OtqAb994", "category": "landmark"},
]

_CATEGORY_LABEL = {
    "city":     "🌆 ŞEHİR",  # i18n-istisna: ölü sabit — hiçbir yerde okunmuyor
    "landmark": "🏛 ANIT",
    "harbor":   "⚓ LİMAN",  # i18n-istisna: ölü sabit — hiçbir yerde okunmuyor
    "nature":   "🌿 DOĞA",  # i18n-istisna: ölü sabit — hiçbir yerde okunmuyor
}


@router.get("/api/map/livestreams")
async def map_livestreams() -> dict:
    """Dünya genelinde küratörlü 24/7 canlı yayın kameraları."""
    return {"streams": _LIVESTREAMS, "count": len(_LIVESTREAMS)}


# ── /api/intel/agents/run — Mission Control AI Agents ─────────── #

@router.get("/api/map/earthquakes")
async def map_earthquakes(min_mag: float = 2.5, period: str = "day"):
    """USGS + AFAD + Sismik Harita birleşik deprem katmanı (cache + stale-on-error).

    USGS: global kapsam (statik CDN feed, çok güvenilir). AFAD: Türkiye'nin
    küçük depremleri dahil resmi kaynak (2026-07-06 keşfi: apiv2 302 ile
    servisnet.afad.gov.tr'ye yönleniyor — follow_redirects şart). Sismik Harita
    (2026-08-23 eklendi): kendisi bir toplayıcı — Kandilli · EMSC · TURHEC ·
    AFAD · USGS'i birleştirir, bize kattığı asıl değer **Kandilli/EMSC** (bizde
    hiç yoktu). Üç kaynak bağımsız resilient — biri düşse diğerleri yaşar.

    Öncelik AFAD > USGS > Sismik Harita: yakın (zaman+konum) kayıt sonrakinden
    düşülür, çift marker çıkmaz. Sismik Harita zaten AFAD+USGS içerdiği için
    eleme onun kayıtlarının çoğunu yer — geriye gerçek boşluk doldurma kalır.

    ⚠️ Sismik Harita zaman damgası UTC'dir (2026-08-23'te USGS'e karşı ölçüldü,
    fark ≤3 sn) — AFAD'ın aksine +3 saat düzeltmesi UYGULANMAZ.
    """
    allowed_periods = {"hour", "day", "week", "month"}
    if period not in allowed_periods:
        period = "day"
    min_mag = max(0.0, min(10.0, min_mag))

    async def _fetch_usgs() -> dict:
        import httpx
        url = f"https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_{period}.geojson"
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(url)
            r.raise_for_status()
            raw = r.json()
        features = raw.get("features")
        if features is None:
            raise RuntimeError(M("harita.usgs-format"))
        return {"features": features}

    async def _fetch_afad() -> dict:
        import httpx
        from datetime import timedelta, timezone as _tz
        days = {"hour": 1, "day": 1, "week": 7, "month": 30}[period]
        # Sorgu parametreleri UTC yorumlanıyor (2026-08-23 ölçümü: end'i +6 saat
        # ileri almak tek bir ek kayıt getirmedi → yerel saat değil)
        end_d = datetime.now(_tz.utc)
        start_d = end_d - timedelta(days=days)
        # 🔴 limit KIRPARSA en YENİ kayıtları atar — 'timedesc' istenmesine rağmen
        # (2026-08-23 ölçümü: 7 günlük pencerede gerçek sayı 789; limit=500 ile
        # dönen en yeni kayıt 3 gün eskiydi, limit=2000 ile anlık). 30 günde
        # gerçek sayı 2677 → limit=2000 bile 5 günlük tazeliği yutuyordu.
        # Deprem fırtınasına pay bırakacak şekilde dönem başına ölçekli:
        _limit = {"hour": 2000, "day": 2000, "week": 4000, "month": 10000}[period]
        async with httpx.AsyncClient(timeout=25, follow_redirects=True) as client:
            r = await client.get(
                "https://deprem.afad.gov.tr/apiv2/event/filter",
                params={"start": start_d.strftime("%Y-%m-%d %H:%M:%S"),
                        "end":   end_d.strftime("%Y-%m-%d %H:%M:%S"),
                        "minmag": 0, "limit": _limit, "orderby": "timedesc"},
                headers={"User-Agent": "Mozilla/5.0 (compatible; AliceAI/1.0)",
                         "Accept": "application/json"},
            )
            r.raise_for_status()
            rows = r.json()
        if not isinstance(rows, list):
            raise RuntimeError(M("harita.afad-format"))
        # Tavana dayandıysak yine en tazesini kaybediyoruz olabilir — sessiz
        # kırpma "her şey kapsandı" gibi okunur, o yüzden dışarı bildiriliyor
        kirpildi = len(rows) >= _limit
        feats = []
        for e in rows:
            try:
                lat = float(e["latitude"]); lon = float(e["longitude"])
                mag = float(e.get("magnitude") or 0)
                depth = float(e.get("depth") or 0)
                # 🔴 AFAD 'date' alanı UTC'dir — TR yereli DEĞİL (2026-08-23'te
                # sismikharita/USGS'e karşı 5 ortak olayda ölçüldü: fark 0 sn).
                # Eski kod iki kez kaydırıyordu: naive .timestamp() metni TR
                # yereli sayıp -3s, üstüne elle -3*3600 → her AFAD markeri
                # 6 SAAT geriye damgalanıyordu. Sonucu: USGS elemesi 180 sn
                # toleransla çalıştığı için hiç tutmuyor, aynı deprem iki kez
                # çiziliyordu. tz-aware ayrıştırma şart.
                ts = 0
                try:
                    dt = datetime.strptime(e.get("date", "")[:19], "%Y-%m-%dT%H:%M:%S")
                    ts = int(dt.replace(tzinfo=_tz.utc).timestamp() * 1000)
                except (ValueError, TypeError):
                    pass
                feats.append({
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [lon, lat, depth]},
                    "properties": {"mag": mag, "place": f"{e.get('location', 'Türkiye')} (AFAD)",  # i18n-istisna: veri (deprem yeri, kaynak içeriği)
                                    "time": ts, "src": "afad"},
                })
            except (KeyError, ValueError, TypeError):
                continue
        if not feats:
            raise RuntimeError(M("harita.afad-bos"))

        # '1 saat' dönemi yukarıda 1 GÜN olarak isteniyor (tabloda hour→1), yani
        # kullanıcı "son 1 saat" seçerken 24 saatlik veri görüyordu. USGS'in
        # all_hour beslemesiyle aynı hizaya gelsin diye kesiliyor.
        if period == "hour":
            _sinir = int((end_d - timedelta(hours=1)).timestamp() * 1000)
            feats = [f for f in feats if (f["properties"].get("time") or 0) >= _sinir]
        return {"features": feats, "kirpildi": kirpildi}

    async def _fetch_sismik() -> dict:
        """sismikharita.com /api.php — Kandilli/EMSC/TURHEC toplayıcısı.

        Anahtar OPSİYONEL: yoksa 100 istek/gün ücretsiz. Geçersiz anahtar ise
        429 + x-block-reason döner; o durumda resilient stale-on-error devreye
        girer ve katman AFAD+USGS ile yaşamaya devam eder.
        """
        import httpx
        from datetime import timedelta, timezone as _tz
        from app.config import SISMIKHARITA_API_KEY

        days = {"hour": 1, "day": 1, "week": 7, "month": 30}[period]
        # tz-aware şart: naive datetime'ın .timestamp()'i YEREL saat varsayar
        # (TR'de 3 saat kayardı) — aşağıdaki epoch hesapları buna bağlı
        now = datetime.now(_tz.utc)
        headers = {"Accept": "application/json",
                   "User-Agent": "Mozilla/5.0 (compatible; AliceAI/1.0)"}
        if SISMIKHARITA_API_KEY:
            headers["Authorization"] = f"Bearer {SISMIKHARITA_API_KEY}"

        # +1 gün: tarih filtresi gün çözünürlüklü, bugünün olayları kesilmesin
        date_to = now + timedelta(days=1)
        date_from = now - timedelta(days=days)
        # 🔴 31+ günlük aralık anahtarsız 401 AUTH_REQUIRED veriyor (2026-08-23'te
        # gün gün ölçüldü: 30 gün ✅ / 31 gün ❌). 'month' dönemi 31 güne denk
        # geldiği için kırpılıyor — kaybedilen 1 günü AFAD+USGS zaten kapsıyor.
        if not SISMIKHARITA_API_KEY and (date_to - date_from).days > 30:
            date_from = date_to - timedelta(days=30)

        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            r = await client.get(
                "https://sismikharita.com/api.php",
                params={"date_from": date_from.strftime("%Y-%m-%d"),
                        "date_to": date_to.strftime("%Y-%m-%d"),
                        "min_magnitude": min_mag, "limit": 1000},
                headers=headers,
            )
            r.raise_for_status()
            raw = r.json()

        rows = raw.get("earthquakes")
        if not isinstance(rows, list):
            raise RuntimeError(M("harita.sismik-format", ham=str(raw)[:120]))

        # Belgelenen 5 kaynağa ek olarak canlıda `noa` (Atina Rasathanesi) de
        # geliyor (2026-08-23 ölçümü) — liste eksikse etiket "Sismik Harita"ya düşer
        _ad = {"kandilli": "Kandilli", "afad": "AFAD", "usgs": "USGS",
               "emsc": "EMSC", "turhec": "TURHEC", "historical": "Tarihsel",
               "noa": "NOA"}
        feats = []
        for e in rows:
            try:
                lat = float(e["latitude"]); lon = float(e["longitude"])
                mag = float(e.get("magnitude") or 0)
                depth = float(e.get("depth_km") or 0)
                # occurred_at UTC — AFAD'daki gibi kaydırma YOK (ölçüldü)
                ts = 0
                try:
                    dt = datetime.strptime(e.get("occurred_at", "")[:19], "%Y-%m-%d %H:%M:%S")
                    ts = int(dt.replace(tzinfo=_tz.utc).timestamp() * 1000)
                except (ValueError, TypeError):
                    pass
                # location alanı hizalama boşluğu + kalite eki taşıyor ("AKDENIZ      İlksel")
                loc = (e.get("display_location") or e.get("location") or "Türkiye")  # i18n-istisna: veri (deprem yeri yedeği)
                loc = " ".join(str(loc).split())
                src = str(e.get("source") or "").lower()
                feats.append({
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [lon, lat, depth]},
                    "properties": {"mag": mag, "time": ts, "src": "sismik",
                                   "src_detail": src,
                                   "place": f"{loc} ({_ad.get(src, 'Sismik Harita')})"},
                })
            except (KeyError, ValueError, TypeError):
                continue
        if not feats and raw.get("count"):
            raise RuntimeError(M("harita.sismik-ayrisamadi"))

        # Uçun tarih filtresi GÜN çözünürlüklü: date_from gün BAŞINI kastettiği
        # için '1g' seçiminde 43 saatlik, '1s' seçiminde 24 saatlik veri dönüyordu
        # (2026-08-23 ölçümü). Dönem etiketi kullanıcıya verilen bir iddiadır —
        # USGS/AFAD'ın kayan penceresiyle aynı hizaya gelsin diye yerel damgayla
        # kesiliyor. (Zamanı çözülemeyen kayıt gösterilmez: doğrulanamıyor.)
        _pencere = timedelta(hours=1) if period == "hour" else timedelta(days=days)
        _sinir = int((now - _pencere).timestamp() * 1000)
        feats = [f for f in feats if (f["properties"].get("time") or 0) >= _sinir]
        return {"features": feats}

    import asyncio as _asyncio
    usgs, afad, sismik = await _asyncio.gather(
        resilient(f"earthquakes:{period}", ttl=120, fetcher=_fetch_usgs),
        resilient(f"earthquakes_afad:{period}", ttl=120, fetcher=_fetch_afad),
        # 300s: anahtarsız kota 100 istek/gün — 120s'lik tur bütçeyi yakabilir
        resilient(f"earthquakes_sismik:{period}:{min_mag}", ttl=300, fetcher=_fetch_sismik),
    )

    if "features" not in usgs and "features" not in afad and "features" not in sismik:
        return {"error": usgs.get("error") or afad.get("error") or sismik.get("error"),
                "features": [], "count": 0}

    afad_feats = [f for f in afad.get("features", [])
                  if (f["properties"].get("mag") or 0) >= min_mag]
    usgs_feats = [f for f in usgs.get("features", [])
                  if (f.get("properties") or {}).get("mag") is not None
                  and f["properties"]["mag"] >= min_mag]
    sismik_feats = [f for f in sismik.get("features", [])
                    if (f["properties"].get("mag") or 0) >= min_mag]

    # TR bbox'ında AFAD ile çakışan USGS kaydını düş (aynı deprem, çift marker)
    def _close(uf, af) -> bool:
        try:
            ulon, ulat = uf["geometry"]["coordinates"][:2]
            alon, alat = af["geometry"]["coordinates"][:2]
            return abs(ulat - alat) < 0.3 and abs(ulon - alon) < 0.3 and                    abs((uf["properties"].get("time") or 0) - (af["properties"].get("time") or 0)) < 180_000
        except (KeyError, IndexError, TypeError):
            return False

    if afad_feats:
        def _in_tr(f):
            try:
                lon, lat = f["geometry"]["coordinates"][:2]
                return 25 <= lon <= 45.5 and 35 <= lat <= 42.5
            except (KeyError, IndexError, TypeError):
                return False
        usgs_feats = [uf for uf in usgs_feats
                      if not (_in_tr(uf) and any(_close(uf, af) for af in afad_feats))]

    # Sismik Harita AFAD ve USGS'i de topladığı için elemesi TR bbox'ıyla sınırlı
    # DEĞİL, global. Naif karşılaştırma 1000×3500'e çıkabilirdi → konum+zaman
    # kovası indeksi. Ölçüt _close ile birebir aynı; kova 0.3°/180sn olduğu için
    # ±1 komşuluk taraması eşiğin altındaki her çifti kapsar.
    if sismik_feats and (afad_feats or usgs_feats):
        _HUCRE, _ZAMAN = 0.3, 180_000

        def _kova(f):
            lon, lat = f["geometry"]["coordinates"][:2]
            return (int(lat // _HUCRE), int(lon // _HUCRE),
                    int((f["properties"].get("time") or 0) // _ZAMAN))

        kovalar: dict[tuple, list] = {}
        for f in afad_feats + usgs_feats:
            try:
                kovalar.setdefault(_kova(f), []).append(f)
            except (KeyError, IndexError, TypeError):
                continue

        def _zaten_var(sf) -> bool:
            try:
                ci, cj, ck = _kova(sf)
            except (KeyError, IndexError, TypeError):
                return False
            for di in (-1, 0, 1):
                for dj in (-1, 0, 1):
                    for dk in (-1, 0, 1):
                        for mevcut in kovalar.get((ci + di, cj + dj, ck + dk), ()):
                            if _close(sf, mevcut):
                                return True
            return False

        sismik_feats = [sf for sf in sismik_feats if not _zaten_var(sf)]

    feats = afad_feats + usgs_feats + sismik_feats
    out = {"type": "FeatureCollection", "features": feats, "count": len(feats),
           "afad": len(afad_feats), "usgs": len(usgs_feats),
           "sismik": len(sismik_feats)}
    if afad.get("kirpildi"):
        out["afad_kirpildi"] = True
    if usgs.get("stale") or afad.get("stale") or sismik.get("stale"):
        out["stale"] = True
        out["age_s"] = max(usgs.get("age_s", 0), afad.get("age_s", 0),
                           sismik.get("age_s", 0))
    return out


# ── Custom POI CRUD (/api/map/pois) ───────────────────────────── #
import json as _json_mod
import os as _os_mod
from fastapi import Body

_POI_FILE = _os_mod.path.join(
    _os_mod.path.dirname(_os_mod.path.dirname(_os_mod.path.dirname(__file__))),
    "data", "map_pois.json"
)

def _load_pois() -> list:
    if not _os_mod.path.exists(_POI_FILE):
        return []
    try:
        with open(_POI_FILE, "r", encoding="utf-8") as f:
            return _json_mod.load(f)
    except Exception:
        return []

def _save_pois(pois: list) -> None:
    _os_mod.makedirs(_os_mod.path.dirname(_POI_FILE), exist_ok=True)
    with open(_POI_FILE, "w", encoding="utf-8") as f:
        _json_mod.dump(pois, f, ensure_ascii=False, indent=2)

@router.get("/api/map/pois")
async def get_pois():
    return {"pois": _load_pois()}

@router.post("/api/map/pois")
async def add_poi(payload: dict = Body(...)):
    import uuid as _uuid
    required = {"name", "lat", "lng"}
    if not required.issubset(payload.keys()):
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail=M("harita.poi-alan-zorunlu"))
    poi = {
        "id":          str(_uuid.uuid4()),
        "name":        str(payload["name"])[:120],
        "lat":         float(payload["lat"]),
        "lng":         float(payload["lng"]),
        "icon":        str(payload.get("icon", "📍"))[:8],
        "color":       str(payload.get("color", "#ff4444"))[:20],
        "description": str(payload.get("description", ""))[:500],
        "category":    str(payload.get("category", "custom"))[:40],
        "created_at":  datetime.now().isoformat(),
    }
    pois = _load_pois()
    pois.append(poi)
    _save_pois(pois)
    log_event("MAP:POI", f"eklendi: {poi['name']}")
    return {"ok": True, "poi": poi}

@router.delete("/api/map/pois/{poi_id}")
async def delete_poi(poi_id: str):
    pois = _load_pois()
    new_pois = [p for p in pois if p.get("id") != poi_id]
    if len(new_pois) == len(pois):
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=M("harita.poi-bulunamadi"))
    _save_pois(new_pois)
    log_event("MAP:POI", f"silindi: {poi_id[:8]}")
    return {"ok": True, "deleted": poi_id}


# ── Kp Index proxy (/api/map/kpindex) ────────────────────────── #
@router.get("/api/map/kpindex")
async def map_kpindex():
    """NOAA SWPC planetary K-index (proxy + 5dk cache + stale).

    NOAA format değiştirdi: eski [["time","Kp",...],...] liste-listesi →
    yeni [{"time_tag":..., "Kp":1.0, ...}] dict listesi. Eski kod
    `latest[1]` ile KeyError(1) alıp katmanı öldürüyordu ("ERROR: 1").
    İki format da desteklenir.
    """
    async def _fetch() -> dict:
        import httpx
        url = "https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json"
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(url)
            r.raise_for_status()
            raw = r.json()

        def parse(entry) -> tuple[str, float] | None:
            try:
                if isinstance(entry, dict):          # yeni format
                    return str(entry.get("time_tag", "")), float(entry.get("Kp"))
                if isinstance(entry, (list, tuple)) and len(entry) > 1:  # eski format
                    return str(entry[0]), float(entry[1])
            except (TypeError, ValueError):
                return None
            return None

        entries = raw[1:] if raw and isinstance(raw[0], (list, tuple)) else raw  # eski formatta ilk satır başlık
        parsed = [p for p in (parse(e) for e in entries) if p is not None]
        if not parsed:
            raise RuntimeError(M("harita.kp-parse"))
        t, kp_val = parsed[-1]
        level = (
            "extreme" if kp_val >= 8 else
            "severe"  if kp_val >= 7 else
            "strong"  if kp_val >= 6 else
            "moderate" if kp_val >= 5 else
            "minor"   if kp_val >= 4 else
            "calm"
        )
        return {
            "kp":      kp_val,
            "level":   level,
            "time":    t,
            "history": [[pt, pv] for pt, pv in parsed[-24:]],
        }

    d = await resilient("kpindex", ttl=300, fetcher=_fetch)
    if "kp" not in d:
        return {**d, "kp": 0.0, "level": "unknown", "history": []}
    return d
