"""Lisans yüzeyi (denetim 2026-11-16, MIM): uyarlanan MIT kodun telif + izin metni NOTICE'ta olmalı; kullanılmayan
NVIDIA lisanslı CUDA paketleri bağımlılık listelerine ve kutu kilitlerine girmemeli.

MIT tek şart koyar: "The above copyright notice and this permission notice shall be included in all copies".
NOTICE'ta yalnız tek satır atıf vardı; threat_patterns.py başlığı "telif metni NOTICE'ta" diyordu.
`cuda-bindings` (NVIDIA Software License) hiçbir paketin bağımlılığı değildi, kodda kullanımı yoktu.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[2]


def test_notice_hermes_agent_mit_telif_ve_izin_metni():
    metin = (KOK / "NOTICE").read_text(encoding="utf-8")
    assert "Copyright (c) 2025 Nous Research" in metin
    assert "Permission is hereby granted, free of charge" in metin
    assert "The above copyright notice and this permission notice shall be included" in metin
    assert 'THE SOFTWARE IS PROVIDED "AS IS"' in metin
    assert "github.com/NousResearch/hermes-agent" in metin


def test_uyarlanan_dosya_notice_a_isaret_ediyor():
    bas = (KOK / "backend/app/services/security/threat_patterns.py").read_text(encoding="utf-8")[:600]
    assert "NOTICE" in bas


@pytest.mark.parametrize("dosya", ["backend/requirements-product.txt", "backend/pybundle-kilit.txt",
                                   "backend/pybundle-win-kilit.txt"])
def test_kullanilmayan_cuda_paketleri_listede_yok(dosya):
    satirlar = (KOK / dosya).read_text(encoding="utf-8").splitlines()
    cuda = [s for s in satirlar if re.match(r"^\s*cuda[-_]", s, flags=re.I)]
    assert not cuda, f"{dosya}: {cuda} — kodda kullanımı yok, NVIDIA lisanslı; THIRD_PARTY'ye yazmadan ekleme"
