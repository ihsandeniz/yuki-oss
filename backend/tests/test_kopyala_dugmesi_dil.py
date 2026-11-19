"""Sohbet balonundaki kopyala düğmesi arayüz diline uyar.

Kusur: düğme yazısı `core.js` içinde sabit 'COPY' / 'OK ✓' idi; Türkçe arayüzde de
İngilizce görünüyordu. Şimdi `_t('sohbet.kopyala')` ve `_t('sohbet.kopyalandi')`.

Ölçülen: düğmeyi kuran blokta sabit İngilizce metin yok, üç atamanın üçü de sözlükten;
iki anahtar tr ve en sözlüğünde var, Türkçe metin İngilizceyle aynı değil.
"""
from __future__ import annotations

import re
from pathlib import Path

from yardim import sozluk, yorumsuz

CORE = Path(__file__).resolve().parents[2] / "frontend" / "js" / "core.js"


def _kopyala_blogu() -> str:
    js = yorumsuz(CORE.read_text(encoding="utf-8"))
    bas = js.index("copyBtn.className = 'msg-copy-btn'")
    son = js.index("};", js.index("copyBtn.onclick", bas))
    return js[bas:son]


def test_kopyala_dugmesinde_sabit_ingilizce_yok():
    blok = _kopyala_blogu()
    assert "'COPY'" not in blok and '"COPY"' not in blok
    assert "'OK ✓'" not in blok and '"OK ✓"' not in blok


def test_kopyala_dugmesi_yazilari_sozlukten():
    blok = _kopyala_blogu()
    atamalar = re.findall(r"copyBtn\.textContent\s*=\s*([^;]+);", blok)
    assert len(atamalar) == 3, atamalar
    assert atamalar.count("_t('sohbet.kopyala')") == 2
    assert atamalar.count("_t('sohbet.kopyalandi')") == 1


def test_anahtarlar_tr_ve_en_sozlugunde():
    tr, en = sozluk("tr"), sozluk("en")
    for k in ("sohbet.kopyala", "sohbet.kopyalandi"):
        assert tr.get(k) and en.get(k), k
    assert tr["sohbet.kopyala"] != en["sohbet.kopyala"]
    assert en["sohbet.kopyala"] == "COPY"
