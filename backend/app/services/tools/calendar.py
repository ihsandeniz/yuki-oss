"""Google Calendar araçları — OAuth2 token'ı `services/google_token_store`'dan.

⚠️ Token dosyasının yolunu burada hesaplama: `api/planner.py` ile ortak olmak
zorunda (2026-09-14'e kadar değildi ve kullanıcı AYAR'dan bağlanıp sohbette
*"bağlı değilsin"* cevabını alıyordu).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

logger = logging.getLogger(__name__)

# 🐞 2026-07-31: token dosyası `backend/`e sabitti → satılan pakette SALT OKUNUR,
# yani Google Takvim'e bağlanan kullanıcının oturumu hiç kaydedilemiyordu (Pro
# özelliği). config_manager / routines / monitoring ile aynı hata sınıfı.
# 🔵 2026-09-14: yol buradan SÖKÜLDÜ → `services/google_token_store`. Sebebi o
#    dosyada yazılı: `api/planner.py` aynı adı BAŞKA bir dizinde arıyordu, yani
#    AYAR'dan bağlanan kullanıcıya sohbette "bağlı değilsin" deniyordu.
from app.services import google_token_store as _tok_deposu

_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
_GOOGLE_EVENTS_URL = "https://www.googleapis.com/calendar/v3/calendars/{cal_id}/events"


def _load_google_tok() -> dict | None:
    return _tok_deposu.google_al()


def _save_google_tok(tok: dict):
    _tok_deposu.google_yaz(tok)


async def _get_access_token() -> str:
    """Geçerli erişim tokeni; yoksa **boş string** (bu modülün sözleşmesi).

    🔵 2026-09-14 (FAZ 4): yenileme gövdesi `services/google_client`'a devredildi.
    Buradaki kopya ile `api/planner.py`'deki kopya aynı işi yapıyor ama hatayı
    farklı yutuyordu; Drive üçüncüsünü yazacaktı. Boş-string sözleşmesi korundu —
    araç yolu sohbetin içinde koşar, orada istisna fırlatmak cevabı öldürür.
    """
    return (await _erisim())[0]


async def _erisim() -> tuple[str, str]:
    """(erişim tokeni, token yoksa SEBEP cümlesi).

    🔴 2026-09-28: araç her durumda sabit *"Planner sayfasından bağlan"* diyordu —
    Türkçe, yanlış yer (bağlantı AYAR → Google'da kurulur) ve yanlış teşhis: izni
    düşmüş bağlantıya da "bağlı değil" deniyordu, kullanıcı kimliği değiştirmesi
    gerekirken boşuna yeniden bağlanıyordu. Sebep artık `google_client`'ın
    kopukluk cümlesidir (aktif dilde, ne yapılacağını söyler).
    """
    from app.mesajlar import M
    from app.services import google_client as _gc
    try:
        return await _gc.erisim_tokeni(), ""
    except _gc.GoogleBagliDegil:
        return "", M("takvim.arac-bagli-degil")
    except _gc.GoogleYetkiDustu as e:
        return "", str(e)
    except Exception as e:  # noqa: BLE001  (ağ/5xx — geçici)
        logger.warning("Google erişim tokeni alınamadı: %s", e)
        return "", M("takvim.arac-ulasilamadi")


def _takvim_hatasi(r) -> str:
    """Takvim API reddi → ne yapılacağını söyleyen cümle (403 = izin, 401 = bağlantı)."""
    from app.mesajlar import M
    if r.status_code == 403 and "rateLimit" not in (r.text or ""):
        return M("planlayici.takvim-izni-yok")
    if r.status_code == 401:
        return M("google.yetki-dustu")
    return M("takvim.arac-hata", kod=r.status_code)


async def get_calendar_events(
    max_results: int = 10,
    calendar_id: str = "primary",
    time_min: str | None = None,
) -> str:
    """Yaklaşan takvim etkinliklerini listeler.

    Args:
        max_results: Döndürülecek maksimum etkinlik sayısı (varsayılan 10).
        calendar_id: Takvim ID'si (varsayılan "primary").
        time_min: Bu tarihten itibaren etkinlikler (ISO 8601). Belirtilmezse şu an kullanılır.
    """
    token, sebep = await _erisim()
    if not token:
        return sebep

    now = time_min or datetime.now(timezone.utc).isoformat()
    # URL-encode calendar_id to prevent path injection
    safe_cal_id = quote(calendar_id, safe='')
    url = _GOOGLE_EVENTS_URL.format(cal_id=safe_cal_id)
    async with httpx.AsyncClient() as c:
        r = await c.get(url, headers={"Authorization": f"Bearer {token}"}, params={
            "timeMin": now,
            "maxResults": max_results,
            "singleEvents": "true",
            "orderBy": "startTime",
        })
        if not r.is_success:
            return _takvim_hatasi(r)
        items = r.json().get("items", [])

    if not items:
        return "Takvimde yaklaşan etkinlik yok."
    lines = []
    for e in items:
        start = e["start"].get("dateTime", e["start"].get("date", "?"))
        lines.append(f"• [{start}] {e.get('summary', '(başlıksız)')} — ID: {e['id']}")
    return "\n".join(lines)


async def create_calendar_event(
    summary: str,
    start: str,
    end: str,
    description: str = "",
    calendar_id: str = "primary",
) -> str:
    """Google Takvim'de yeni bir etkinlik oluşturur.

    Args:
        summary: Etkinlik başlığı.
        start: Başlangıç zamanı (ISO 8601, örn. "2026-05-18T10:00:00+03:00").
        end: Bitiş zamanı (ISO 8601, örn. "2026-05-18T11:00:00+03:00").
        description: Etkinlik açıklaması (opsiyonel).
        calendar_id: Takvim ID'si (varsayılan "primary").
    """
    token, sebep = await _erisim()
    if not token:
        return sebep

    event_body: dict[str, Any] = {
        "summary": summary,
        "start": {"dateTime": start, "timeZone": "Europe/Istanbul"},
        "end": {"dateTime": end, "timeZone": "Europe/Istanbul"},
    }
    if description:
        event_body["description"] = description

    # URL-encode calendar_id to prevent path injection
    safe_cal_id = quote(calendar_id, safe='')
    url = _GOOGLE_EVENTS_URL.format(cal_id=safe_cal_id)
    async with httpx.AsyncClient() as c:
        r = await c.post(url, headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }, json=event_body)
        if not r.is_success:
            return _takvim_hatasi(r)
        created = r.json()
    return f"Etkinlik oluşturuldu: {created.get('summary')} — ID: {created['id']}"


async def delete_calendar_event(
    event_id: str,
    calendar_id: str = "primary",
) -> str:
    """Google Takvim'den bir etkinliği siler.

    Args:
        event_id: Silinecek etkinliğin ID'si.
        calendar_id: Takvim ID'si (varsayılan "primary").
    """
    token, sebep = await _erisim()
    if not token:
        return sebep

    # URL-encode both calendar_id and event_id to prevent path injection
    safe_cal_id = quote(calendar_id, safe='')
    safe_event_id = quote(event_id, safe='')
    url = _GOOGLE_EVENTS_URL.format(cal_id=safe_cal_id) + f"/{safe_event_id}"
    async with httpx.AsyncClient() as c:
        r = await c.delete(url, headers={"Authorization": f"Bearer {token}"})
        if r.status_code not in (200, 204):
            return f"Etkinlik silinemedi: {r.status_code} — {r.text[:200]}"
    return f"Etkinlik silindi: {event_id}"


async def silme_sunumu(args: dict[str, Any]) -> dict[str, Any]:
    """Silme onay kutusunun insan dilindeki hali: {baslik, mesaj, etiket, satirlar}.

    Ham `event_id` kullanıcıya bir şey söylemez — etkinliğin adı ve zamanı okunur.
    Okuma best-effort: Google'a ulaşılamazsa kutu yine çıkar, satırda kimlik kalır
    (kapı açılmamalı, yalnız daha az bilgi verir).
    """
    from app.mesajlar import M
    event_id = str(args.get("event_id", ""))
    calendar_id = str(args.get("calendar_id", "primary"))
    satir = event_id
    try:
        token, _ = await _erisim()
        if token and event_id:
            url = (_GOOGLE_EVENTS_URL.format(cal_id=quote(calendar_id, safe=''))
                   + f"/{quote(event_id, safe='')}")
            async with httpx.AsyncClient(timeout=5) as c:
                r = await c.get(url, headers={"Authorization": f"Bearer {token}"})
            if r.is_success:
                ev = r.json()
                bas = ev.get("start", {})
                zaman = bas.get("dateTime") or bas.get("date") or ""
                ad = ev.get("summary") or M("takvim.sil-adsiz")
                satir = f"{ad} · {zaman.replace('T', ' ')[:16]}" if zaman else ad
    except Exception as e:  # noqa: BLE001
        logger.warning("Silinecek etkinlik okunamadı: %s", e)
    return {
        "baslik": M("takvim.sil-onay-baslik"),
        "mesaj": M("takvim.sil-onay-mesaj"),
        "etiket": M("takvim.sil-onay-etiket"),
        "satirlar": [satir],
        "yikici": True,   # arayüz onay düğmesini kırmızı çizer
    }
