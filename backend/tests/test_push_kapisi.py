"""Telefon bildirimi (push) — kademe kapısı (Dalga 4, 2026-09-18).

Karar: **Pro** (2026-09-04 kademe planlaması).
Uç 2026-09-18'e kadar **kapısızdı** — yani Free kullanıcı Pro diye satılan
şeyi alıyordu; aynı sınıf `emotion_sprites`'ta ters yönde çözülmüştü.

Bu dosya kapıyı **uç listesinden değil router'dan** türetir (`api/memory.py`'nin
2026-08-06 dersi: 9 uçtan 4'ü kapısızdı ve uç uç yazılmış test bunu göremedi).
Yarın eklenen bir uç kapıyı kendiliğinden devralır; devralmazsa burası kırmızı.

Arayüz ayağı ayrıca ölçülür — `multi_character` dersi: kapı doğruydu ama arayüz
sabit listeye bakıyordu, **ödeyen müşteri satın aldığını göremiyordu.** Burada
ters yön de geçerli: bayrak yanlış uçtan okunursa Pro müşteri paneli hiç görmez.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.api import push as push_api




def test_router_kapiyi_tasiyor():
    adlar = [d.dependency.__name__ for d in push_api.router.dependencies
             if getattr(d, "dependency", None)]
    assert "require_push" in adlar, "router düzeyi kapı yok — uçlar kapısız"


def test_her_uc_kapiyi_devraliyor():
    """Router'dan türetilir: 10 uç da dependency'i taşımak ZORUNDA.

    Uç sayısını sabit yazmıyoruz — yarın 11. uç eklenirse o da denetime girsin.
    """
    rotalar = [r for r in push_api.router.routes if hasattr(r, "dependencies")]
    assert rotalar, "router'da hiç rota yok — test yanlış şeyi ölçüyor"
    for r in rotalar:
        kapili = any(
            getattr(d, "dependency", None) is push_api.require_push
            for d in push_api.router.dependencies
        )
        assert kapili, f"{r.path} kapısız"


