"""Takvimden silme her zaman onay ister ( yayın şartı, 2026-10-04).

Ürünün TOOL_APPROVAL_ENABLED varsayılanı false — delete_calendar_event yalnız
CRITICAL_TOOLS'ta dururken hiç onay sorulmadan müşterinin takviminden siliyordu.
"""
from __future__ import annotations

import asyncio

from app.services.tools import approval_gate, calendar, dispatcher


def test_silme_kapatilamaz_onayda_ekleme_degil():
    assert "delete_calendar_event" in approval_gate.ALWAYS_APPROVE
    assert "create_calendar_event" not in approval_gate.ALWAYS_APPROVE
    assert "get_calendar_events" not in approval_gate.ALWAYS_APPROVE


def test_onay_ayari_kapaliyken_bile_silmeden_once_sorar(monkeypatch):
    import app.config as cfg
    monkeypatch.setattr(cfg, "TOOL_APPROVAL_ENABLED", False)
    monkeypatch.setattr(dispatcher, "_is_tool_allowed", lambda n: True)

    async def erisim_yok():
        return "", "bağlı değil"
    monkeypatch.setattr(calendar, "_erisim", erisim_yok)

    sorulan = {}

    async def reddet(name, args, sunum=None):
        sorulan.update(name=name, sunum=sunum)
        return False
    monkeypatch.setattr(approval_gate, "request_approval", reddet)

    silindi = []

    async def sahte_sil(*a, **k):
        silindi.append(a)
        return "silindi"
    monkeypatch.setattr(dispatcher, "delete_calendar_event", sahte_sil)

    sonuc = asyncio.run(dispatcher.call_tool("delete_calendar_event", {"event_id": "abc123"}))
    assert "ONAY REDDEDİLDİ" in sonuc
    assert silindi == [], "onay verilmeden silme çağrılmamalı"
    assert sorulan["name"] == "delete_calendar_event"
    s = sorulan["sunum"]
    assert s["baslik"] and s["mesaj"] and s["etiket"]
    # Google'a ulaşılamadığında kutu yine çıkar, satırda kimlik kalır
    assert s["satirlar"] == ["abc123"]
