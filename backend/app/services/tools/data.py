"""Veri araçları: hava durumu, deprem, borsa, kripto, döviz, batarya, git."""
import asyncio
import os
import re
import subprocess
from pathlib import Path


# ── HAVA DURUMU ──────────────────────────────────────────────────────────────

async def get_weather(city: str = "Istanbul") -> str:
    """Open-Meteo + Geocoding API ile hava durumu. API key gereksiz, CORS-safe."""
    import httpx
    city = city.strip()[:80]
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            # Koordinat bul
            geo = await client.get(
                "https://geocoding-api.open-meteo.com/v1/search",
                params={"name": city, "count": 1, "language": "tr"}
            )
            geo.raise_for_status()
            gdata = geo.json()
            results = gdata.get("results")
            if not results:
                return f"Hata: '{city}' için konum bulunamadı."
            loc = results[0]
            lat, lon = loc["latitude"], loc["longitude"]
            loc_name = loc.get("name", city)
            country = loc.get("country", "")

            # Hava durumu
            wx = await client.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "current": "temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m,precipitation",
                    "daily": "temperature_2m_max,temperature_2m_min,weather_code,precipitation_sum",
                    "forecast_days": 3,
                    "timezone": "auto",
                    "wind_speed_unit": "kmh",
                }
            )
            wx.raise_for_status()
            d = wx.json()

        cur = d.get("current", {})
        daily = d.get("daily", {})

        wmo_desc = {
            0: "Açık", 1: "Çoğunlukla açık", 2: "Parçalı bulutlu", 3: "Bulutlu",
            45: "Sisli", 48: "Kırağı sisi",
            51: "Hafif çisenti", 53: "Orta çisenti", 55: "Yoğun çisenti",
            61: "Hafif yağmur", 63: "Orta yağmur", 65: "Şiddetli yağmur",
            71: "Hafif kar", 73: "Orta kar", 75: "Yoğun kar",
            80: "Hafif sağanak", 81: "Orta sağanak", 82: "Şiddetli sağanak",
            95: "Fırtına", 96: "Dolulu fırtına",
        }

        def wmo(code):
            return wmo_desc.get(int(code) if code is not None else 0, f"Kod {code}")

        temp = cur.get("temperature_2m", "?")
        feels = cur.get("apparent_temperature", "?")
        hum = cur.get("relative_humidity_2m", "?")
        wind = cur.get("wind_speed_10m", "?")
        prec = cur.get("precipitation", 0)
        desc = wmo(cur.get("weather_code"))

        lines = [f"🌡 {loc_name}, {country} — Anlık Hava Durumu"]
        lines.append(f"  {desc} | {temp}°C (hissedilen {feels}°C)")
        lines.append(f"  Nem: %{hum} | Rüzgar: {wind} km/h | Yağış: {prec}mm")

        dates = daily.get("time", [])
        maxT = daily.get("temperature_2m_max", [])
        minT = daily.get("temperature_2m_min", [])
        codes = daily.get("weather_code", [])
        precs = daily.get("precipitation_sum", [])
        lines.append("  3 Günlük Tahmin:")
        for i in range(min(3, len(dates))):
            label = ["Bugün", "Yarın", "Öbür gün"][i]
            lines.append(f"    {label} ({dates[i]}): {wmo(codes[i])} | {minT[i]}–{maxT[i]}°C | ☂ {precs[i]}mm")

        return "\n".join(lines)

    except Exception as e:
        return f"Hata: Hava durumu alınamadı. {e}"


# ── DEPREM ───────────────────────────────────────────────────────────────────

async def get_earthquake_alerts(
    min_magnitude: float = 4.0,
    limit: int = 5,
    region: str = "global",
) -> str:
    """
    USGS Earthquake Hazards API — son depremler.
    region: 'global' | 'turkey' (Türkiye bölgesi: 36-42°N, 26-45°E)
    """
    import httpx
    from datetime import datetime, timedelta, timezone

    # USGS'in varsayılanı da 30 gün; açıkça yazılınca cevaptaki süre iddiası sorguya bağlı kalır
    # (eskiden boş sonuç "son 24 saatte" diyordu).
    baslangic = datetime.now(timezone.utc) - timedelta(days=30)
    base_params: dict = {
        "format": "geojson",
        "limit": min(limit, 20),
        "minmagnitude": min_magnitude,
        "orderby": "time",
        "starttime": baslangic.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    if region.lower() in ("turkey", "türkiye", "tr"):
        base_params.update({"minlatitude": 36, "maxlatitude": 42,
                             "minlongitude": 26, "maxlongitude": 45})

    url = "https://earthquake.usgs.gov/fdsnws/event/1/query"
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.get(url, params=base_params)
            r.raise_for_status()
            data = r.json()

        features = data.get("features", [])
        if not features:
            label = "Türkiye" if region.lower() in ("turkey", "türkiye", "tr") else "dünya geneli"
            return f"Son 30 günde M{min_magnitude}+ deprem yok ({label})."

        lines = [f"🌍 Son Depremler (M{min_magnitude}+, {region}):"]
        for f in features[:limit]:
            p = f["properties"]
            mag = p.get("mag", "?")
            place = p.get("place", "Bilinmiyor")
            ts = p.get("time", 0)
            dt = datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%d.%m %H:%M UTC")
            depth_km = f["geometry"]["coordinates"][2] if f.get("geometry") else "?"
            lines.append(f"  M{mag} — {place} | Derinlik: {depth_km}km | {dt}")

        return "\n".join(lines)

    except Exception as e:
        return f"Hata: Deprem verisi alınamadı. {e}"


# ── DÖVİZ KURU ───────────────────────────────────────────────────────────────

async def get_exchange_rate(
    base: str = "USD",
    currencies: str = "TRY,EUR,GBP",
) -> str:
    """Frankfurter.app — günlük döviz kurları. Ücretsiz, CORS-safe, no auth."""
    import httpx

    base = base.strip().upper()[:3]
    quotes = [c.strip().upper()[:3] for c in currencies.split(",") if c.strip()][:10]
    if not quotes:
        quotes = ["TRY", "EUR", "GBP"]

    url = "https://api.frankfurter.dev/v2/rates"
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.get(url, params={"base": base, "quotes": ",".join(quotes)})
            r.raise_for_status()
            data = r.json()

        # 🔴 Frankfurter v2 (/v2/rates) LİSTE döndürür: [{date, base, quote, rate}, …]
        # v1 (/latest) sözlük döndürüyordu: {date, rates: {CUR: val}}. Kod v1 şemasını
        # okuduğu için v2'de `'list' object has no attribute 'get'` ile ölüyordu —
        # "dolar kaç TL" cevapsız kalıyordu (Free'nin 20 aracından biri). v1 hâlâ ayakta
        # ama bir gün bayat veri veriyor (ölçüldü 2026-08-09: v1 08-07, v2 08-08),
        # o yüzden URL v2'de kalıyor ve İKİ şekil de kabul ediliyor.
        if isinstance(data, list):
            rates = {
                str(row.get("quote", "")).upper(): row.get("rate")
                for row in data if isinstance(row, dict)
            }
            date = next(
                (row.get("date") for row in data
                 if isinstance(row, dict) and row.get("date")),
                "?",
            )
        elif isinstance(data, dict):
            rates = {str(k).upper(): v for k, v in (data.get("rates") or {}).items()}
            date = data.get("date", "?")
        else:
            return "Hata: Döviz kuru alınamadı. Beklenmeyen cevap biçimi."

        if not rates:
            return "Hata: Döviz kuru alınamadı. Sağlayıcı hiç kur döndürmedi."

        lines = [f"💱 Döviz Kurları ({base} bazlı, {date}):"]
        for cur in quotes:  # istenen sıra korunur — "dolar kaç TL" sorusunda TRY başta
            try:
                lines.append(f"  1 {base} = {float(rates[cur]):.4f} {cur}")
            except (KeyError, TypeError, ValueError):
                lines.append(f"  {cur}: veri yok")

        return "\n".join(lines)

    except Exception as e:
        return f"Hata: Döviz kuru alınamadı. {e}"


# ── KRİPTO ───────────────────────────────────────────────────────────────────

async def get_crypto_price(
    coins: str = "bitcoin,ethereum",
    currency: str = "usd",
) -> str:
    """CoinGecko API — anlık kripto fiyatları. Ücretsiz, CORS-safe, no auth."""
    import httpx

    currency = currency.strip().lower()[:5]
    coin_list = [c.strip().lower() for c in coins.split(",") if c.strip()][:10]
    if not coin_list:
        coin_list = ["bitcoin", "ethereum"]

    url = "https://api.coingecko.com/api/v3/simple/price"
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.get(url, params={
                "ids": ",".join(coin_list),
                "vs_currencies": currency,
                "include_24hr_change": "true",
                "include_market_cap": "true",
            })
            r.raise_for_status()
            data = r.json()

        if not data:
            return "Hata: CoinGecko'dan veri alınamadı."

        # Geçersiz para biriminde CoinGecko coin'i boş sözlükle döner; "veri yok" yanlış yöne götürür.
        if any(c in data for c in coin_list) and not any(currency in (data.get(c) or {}) for c in coin_list):
            return f"Hata: '{currency.upper()}' için fiyat yok, para birimi geçersiz olabilir (ör. usd, try, eur)."

        lines = [f"₿ Kripto Fiyatları ({currency.upper()}):"]
        for coin in coin_list:
            info = data.get(coin)
            if not info:
                lines.append(f"  {coin}: veri yok")
                continue
            price = info.get(currency, "?")
            change = info.get(f"{currency}_24h_change")
            change_str = f" ({change:+.2f}%)" if change is not None else ""
            lines.append(f"  {coin.capitalize()}: {price:,.2f} {currency.upper()}{change_str}")

        return "\n".join(lines)

    except Exception as e:
        return f"Hata: Kripto fiyatı alınamadı. {e}"


# ── BATARYA ───────────────────────────────────────────────────────────────────

def get_battery() -> str:
    """Batarya durumunu okur (sysfs — herhangi bir bağımlılık gerektirmez)."""
    try:
        base = Path("/sys/class/power_supply")
        batteries = sorted(p for p in base.iterdir() if p.name.startswith("BAT"))
        if not batteries:
            return "Batarya bulunamadı (masaüstü veya sysfs erişimi yok)."

        lines = []
        for bat in batteries:
            def _r(fname: str) -> str:
                try:
                    return (bat / fname).read_text().strip()
                except Exception:
                    return ""

            name = bat.name
            status = _r("status") or "?"
            capacity = _r("capacity")
            cap_str = f"%{capacity}" if capacity else "?"

            # Enerji veya şarj bilgisi
            energy_now = _r("energy_now") or _r("charge_now")
            energy_full = _r("energy_full") or _r("charge_full")
            power_now = _r("power_now") or _r("current_now")

            time_str = ""
            if energy_now and energy_full and power_now:
                try:
                    e_now = int(energy_now)
                    e_full = int(energy_full)
                    p = int(power_now)
                    if p > 0:
                        if status.lower() == "discharging":
                            h = e_now / p
                        else:
                            h = (e_full - e_now) / p
                        hours = int(h)
                        mins = int((h - hours) * 60)
                        verb = "kalan" if status.lower() == "discharging" else "şarj süresi"
                        time_str = f" — ~{hours}s {mins}dk {verb}"
                except Exception:
                    pass

            status_emoji = {"Charging": "⚡", "Discharging": "🔋", "Full": "✅"}.get(status, "🔋")
            lines.append(f"{status_emoji} {name}: {cap_str} ({status}){time_str}")

        return "\n".join(lines)
    except Exception as e:
        return f"Hata: Batarya bilgisi alınamadı. {e}"


# ── GIT ──────────────────────────────────────────────────────────────────────

def git_status(path: str = ".") -> str:
    """Git repo durumu: branch, staged/unstaged değişiklikler, untracked dosyalar."""
    p = Path(os.path.expanduser(path)).resolve()
    if not p.exists():
        return f"Hata: Dizin bulunamadı: {path}"

    def _run(*args: str) -> tuple[int, str]:
        try:
            r = subprocess.run(
                ["git", "-C", str(p), *args],
                capture_output=True, text=True, timeout=10
            )
            # Yalnız sondan kırp: `status --short` ilk satırındaki baştaki boşluk durum sütunudur.
            return r.returncode, (r.stdout + r.stderr).rstrip()
        except Exception as e:
            return 1, str(e)

    # Repo kontrolü
    rc, _ = _run("rev-parse", "--is-inside-work-tree")
    if rc != 0:
        return f"Hata: '{path}' bir git reposu değil."

    lines = [f"📦 Git Status — {p}"]

    # Branch
    _, branch = _run("rev-parse", "--abbrev-ref", "HEAD")
    lines.append(f"  Branch: {branch}")

    # Uzak dal farkı
    _, remote_info = _run("status", "-sb", "--porcelain=v1")
    if remote_info:
        first = remote_info.split("\n")[0]
        if "[" in first:
            bracket = first[first.find("["):first.find("]")+1]
            lines.append(f"  Uzak: {bracket}")

    # Değişiklikler
    _, diff_stat = _run("status", "--short")
    if diff_stat:
        staged = [l for l in diff_stat.splitlines() if l and l[0] not in (" ", "?")]
        unstaged = [l for l in diff_stat.splitlines() if len(l) > 1 and l[1] not in (" ", "?")]
        untracked = [l for l in diff_stat.splitlines() if l.startswith("??")]
        if staged:
            lines.append(f"  Staged ({len(staged)}): " + ", ".join(l[3:] for l in staged[:5]))
        if unstaged:
            lines.append(f"  Unstaged ({len(unstaged)}): " + ", ".join(l[3:] for l in unstaged[:5]))
        if untracked:
            lines.append(f"  Untracked ({len(untracked)}): " + ", ".join(l[3:] for l in untracked[:5]))
    else:
        lines.append("  ✓ Çalışma ağacı temiz")

    # Son 3 commit
    _, log = _run("log", "--oneline", "-3")
    if log:
        lines.append("  Son commitler:")
        for l in log.splitlines()[:3]:
            lines.append(f"    {l}")

    return "\n".join(lines)


def git_log(path: str = ".", n: int = 10) -> str:
    """Git commit geçmişi — son N commit."""
    p = Path(os.path.expanduser(path)).resolve()
    if not p.exists():
        return f"Hata: Dizin bulunamadı: {path}"
    n = max(1, min(int(n), 50))
    try:
        r = subprocess.run(
            ["git", "-C", str(p), "log", f"-{n}",
             "--pretty=format:%h %ad %s", "--date=short"],
            capture_output=True, text=True, timeout=10
        )
        if r.returncode != 0:
            return f"Hata: git log başarısız. {r.stderr.strip()}"
        lines = r.stdout.strip().splitlines()
        if not lines:
            return "Henüz commit yok."
        return f"📜 Son {n} commit ({p}):\n" + "\n".join(f"  {l}" for l in lines)
    except Exception as e:
        return f"Hata: {e}"
