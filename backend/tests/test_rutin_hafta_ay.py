"""Tekrarlı alarmda hafta/ay/yıl tek harfli birime düşmez.

Birim eşlemesi önekle yapılıyor ve "hafta" → "h" (saat), "months" → "m" (dakika)
eşleşiyordu: "her 2 hafta" alarmı her 2 saatte, "every 2 months" her 2 dakikada çalıyordu.
Kişisel Yuki'deki düzeltmenin yeniden yazımı: hafta gün katına çevrilir (insan metni ve dil
kataloğu değişmez), ay/yıl aralık tetikleyicisiyle doğru kurulamadığı için reddedilir.
"""
import pytest

from app.services.scheduler import parse_recurring


@pytest.mark.parametrize("ifade, beklenen", [
    ("her 2 hafta", {"days": 14}),
    ("2 haftada bir", {"days": 14}),
    ("every 2 weeks", {"days": 14}),
    ("her hafta", {"days": 7}),
    ("haftada bir", {"days": 7}),
    ("every week", {"days": 7}),
])
def test_hafta_gun_katina_cevrilir(ifade, beklenen):
    sonuc = parse_recurring(ifade)
    assert sonuc is not None and sonuc[0] == beklenen


@pytest.mark.parametrize("ifade", [
    "every 2 months", "her 3 ay", "3 ayda bir", "her yıl", "every 2 years", "her 2 yil",
])
def test_ay_yil_reddedilir_dakika_saat_olmaz(ifade):
    assert parse_recurring(ifade) is None


@pytest.mark.parametrize("ifade, beklenen", [
    ("her 2 saat", {"hours": 2}), ("her 10 dakika", {"minutes": 10}),
    ("every 5 min", {"minutes": 5}), ("every 20m", {"minutes": 20}),
    ("her gün", {"days": 1}), ("every 3h", {"hours": 3}),
])
def test_eski_birimler_degismez(ifade, beklenen):
    assert parse_recurring(ifade)[0] == beklenen
