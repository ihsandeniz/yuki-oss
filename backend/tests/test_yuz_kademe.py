"""Yüz tanıma kademe kaydı — SEKME mi ARAÇ mı.

ipek kararı (2026-09-05): üründe yüz tanıma **sekmedir**, LLM aracı değildir.
Yani Yuki kendi başına "şu kim" diye kamera açamaz.

Bu dosya o kararı **mekanik** hâle getirir. Karar bir yorum satırında kalırsa
bir sonraki tur onu bilmeden `STEP_TOOLS`'a bir yüz aracı ekleyebilir; kademe
sayıları da beraberinde değişir ve kimse fark etmez.

Ayrıca arayüz kapısının **doğru alana** baktığını da ölçer — karakter kilidi
dersinin bu özellikteki karşılığı ters yönde: `features` sözlüğü free özellikleri
BİLEREK taşımaz, dolayısıyla naif bir `features.face_recognition` kontrolü
sekmeyi herkeste gizlerdi.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.services.tools import dispatcher

KOK = Path(__file__).resolve().parents[2]
TAB_NAV = KOK / "frontend" / "js" / "tab-nav.js"


# ── kademe tablosu ──────────────────────────────────────────────────────────
def test_yuz_tanima_LLM_ARACI_DEGIL():
    """🔑 Kararın asıl mekanik karşılığı: araç kaydında yüz aracı olmamalı.

    Bu test kırmızı yanıyorsa ya bilerek araçlaştırma yapıldı (o zaman ipek'ın
    kararı değişmiş demektir ve burası güncellenmeli) ya da kazara bir araç
    sızdı — ikincisi kameraya model erişimi açar, sessiz geçilemez.
    """
    yuz_desenleri = re.compile(r"face|yuz|yüz", re.IGNORECASE)
    araclar = [t["function"]["name"] for t in dispatcher.TOOLS]
    sizanlar = [t for t in araclar if yuz_desenleri.search(t)]
    assert not sizanlar, f"araç kaydında yüz aracı var: {sizanlar}"


# ── arayüz kapısı ───────────────────────────────────────────────────────────
@pytest.mark.skipif(not TAB_NAV.exists(), reason="tab-nav.js yok")
def test_yuz_paneline_ayarlardan_ULASILABILIYOR():
    """YÜZ artık sekme DEĞİL — Ayarlar → Güvenlik odasının içinde (2026-09-06).

    🔴 Bu test eskiden "sekme 5 kayıt noktasının hepsinde var mı" diye soruyordu.
    Sekme kaldırılınca o soru **anlamını yitirdi**, ama sorunun ARDINDAKİ kural
    hâlâ geçerli ve aynı kural: *bir yüzeyin kodu olması, ona ulaşılabildiğini
    göstermez* (TAM BOY modu tam bu yüzden ölmüştü — CSS'i, markup'ı, uygulayıcısı
    vardı, mod listesinde yoktu).

    O yüzden test silinmedi, **yeni ulaşım yoluna çevrildi**. Zincirin her halkası
    ayrı ayrı ölçülüyor; biri koparsa panel yine sessizce erişilemez olur.
    """
    kaynak = TAB_NAV.read_text(encoding="utf-8")
    index_html = (KOK / "frontend" / "index.html").read_text(encoding="utf-8")
    intro = (KOK / "frontend" / "js" / "intro-sequences.js").read_text(encoding="utf-8")

    # ① Panelin kabuğu duruyor (faces.js içeriği buraya çiziyor)
    assert 'id="faces-root"' in index_html, "panel kökü HTML'de yok"

    # ② Backend Güvenlik odasını ilan ediyor + frontend onu çiziyor
    assert "render==='guvenlik'" in intro.replace(" ", ""), \
        "Güvenlik odası çizim dalı yok"
    assert "function renderGuvenlikBolumu" in intro, "oda çizici fonksiyonu yok"

    # ③ Oda paneli GERÇEKTEN gövdesine gömüyor — dal olup gömme olmazsa
    #    kullanıcı boş bir 'Yüz Tanıma' başlığı görür
    assert "hq-guvenlik-yuz" in intro, "yüz kutusu odaya gömülmüyor"
    assert "YuzSekmesi" in intro, "oda faces.js'i hiç çağırmıyor"

    # ④ Menüde yeri var — yoksa odaya tıklanacak bir yer kalmaz
    assert "id:'guvenlik'" in intro.replace(" ", ""), "Güvenlik menüde yok"

    # ⑥ Eski yol kırılmadı: switchTab('faces') kullanıcıyı sohbete atmamalı
    assert "return 'guvenlik'" in kaynak, \
        "eski 'faces' adı Güvenlik odasına yönlendirilmiyor"

    # ⑦ Kaldırılan sekmenin artıkları GERÇEKTEN gitti — yarım kaldırma,
    #    var olmayan düğmeye bağlı ölü DOM kancası bırakır
    assert 'id="tab-btn-faces"' not in index_html, "sekme düğmesi hâlâ HTML'de"
    assert "{ ad: 'faces'" not in kaynak, "sekme listesinde ölü kayıt kalmış"
