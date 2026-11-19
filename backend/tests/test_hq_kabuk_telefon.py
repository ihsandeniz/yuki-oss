"""HQ KABUK · telefon sekme şeridi + üst bant bekçisi (2026-10-01).

Ölçülen iki kusur (telefon 390, bütün HQ panellerinde ortak):
  ① yatay sekme şeridinin son görünen etiketi ✕ payında YARIM kesik duruyordu ("Sağlı"/"Heal") ve
     etkin sekme şeridin dışında kalabiliyordu;
  ② oda başlığı (ad + açıklama + eylem) kaymadığı için şerit + başlık ekranın %20-32'sini tutuyordu.
Piksel ölçümü `reports/…/olcum/kabuk_cek.py`; burada kuralın KAYNAKTA durduğu kilitlenir (mutasyonla kırmızı).
"""
from __future__ import annotations

import re
from pathlib import Path

from yardim import yorumsuz

KOK = Path(__file__).resolve().parents[2]
CSS = yorumsuz((KOK / "frontend" / "css" / "hq.css").read_text(encoding="utf-8"))
JS = yorumsuz((KOK / "frontend" / "js" / "intro-sequences.js").read_text(encoding="utf-8"))
INDEX = (KOK / "frontend" / "index.html").read_text(encoding="utf-8")
SW = (KOK / "frontend" / "sw.js").read_text(encoding="utf-8")


def _dar_bloklar() -> str:
    """`@media (max-width: 720px) { … }` bloklarının gövdeleri (iç içe süslüyü sayarak)."""
    out = []
    for m in re.finditer(r"@media \(max-width: 720px\) \{", CSS):
        i, d = m.end(), 1
        while d and i < len(CSS):
            d += {"{": 1, "}": -1}.get(CSS[i], 0)
            i += 1
        out.append(CSS[m.end():i - 1])
    return "\n".join(out)


DAR = _dar_bloklar()


def test_serit_iki_kenarda_solar_kaydirilabilir_kalir():
    m = re.search(r"(?<!-webkit-)mask-image:([^;]+);", DAR)
    assert m, "şerit maskesi dar-pencere bloğunda olmalı (masaüstüne sızmasın)"
    assert "transparent" in m.group(1) and "calc(100% - " in m.group(1) and "scroll-snap-type: x" in DAR, "sağ kenar solmalı"
    assert "overflow-x: auto" in DAR, "şerit kaydırılabilir kalmalı (maske kaydırmayı kapatmasın)"
    assert CSS.count("mask-image") == DAR.count("mask-image"), "maske yalnız ≤720px'te"


def test_oda_basligi_telefonda_icerikle_kayar():
    assert re.search(r"#tab-hq \.oda \{ overflow-y: auto;", DAR)
    assert re.search(r"#tab-hq \.oda > \.oda-bas, #tab-hq \.oda > \.oda-govde[^{]*\{ flex: none; overflow: visible;", DAR), \
        "başlık + gövde tek kaydırıcıya (oda) bağlı olmalı"


def test_etkin_sekme_serit_icinde_gorunur_alana_kayar():
    m = re.search(r"window\.hqMenuIsaretle = function\(\)\{.*?\n  \};", JS, re.S)
    assert m
    g = m.group(0)
    assert "nav.scrollLeft" in g and ".hq-nav-btn.active" in g
    assert "scrollIntoView" not in g, "ata kaydırıcıları (sayfa/oda) oynatmamalı"


def test_surum_uclusu_birlikte_artti():
    assert re.search(r"css/hq\.css\?v=(\d+)", INDEX) and int(re.search(r"css/hq\.css\?v=(\d+)", INDEX).group(1)) >= 27
    assert int(re.search(r"intro-sequences\.js\?v=(\d+)", INDEX).group(1)) >= 68
    assert int(re.search(r"CACHE_VERSION = 'yuki-v(\d+)'", SW).group(1)) >= 318


def test_solma_seridin_kendi_zeminine_iner():
    """goz: maske şeridin zeminini de siliyordu → sayfa zemini görünüp x≈322'de sert bant. Zemin şeritten ayrıldı."""
    assert re.search(r"#hq-subnav \{[^}]*background: transparent", DAR), "şerit şeffaf: maske yalnız etiketi siler"
    assert re.search(r"#tab-hq\.active::before \{ inset-inline-start: 0; inline-size: 100%; \}", DAR), \
        "şeridin zemini tam genişlikte, maskeden bağımsız"
    assert "scroll-snap-align: start" in DAR, "sol uçta yarım harf kalmasın: etiket sınırına otur"
