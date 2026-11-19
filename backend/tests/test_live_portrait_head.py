"""`/api/live-portrait/clip` HEAD desteği.

Frontend (`core.js` → `playFalAnimation`) videoyu `<video>`'ya vermeden önce HEAD ile
servisin ayakta olup olmadığını yokluyor. Uç yalnız GET kabul ettiği için her sayfa
açılışında konsola 405 düşüyordu (2026-08-01'de ölçüldü).
"""

import pytest


@pytest.mark.asyncio
async def test_head_405_donmuyor(client):
    r = await client.head("/api/live-portrait/clip?action=breath")
    assert r.status_code != 405, "HEAD hâlâ reddediliyor — konsoldaki 405 geri geldi"


@pytest.mark.asyncio
async def test_head_gecersiz_aksiyonu_reddeder(client):
    r = await client.head("/api/live-portrait/clip?action=olmayan_aksiyon")
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_head_govde_dondurmez(client):
    r = await client.head("/api/live-portrait/clip?action=breath")
    assert r.content == b""


@pytest.mark.asyncio
async def test_get_hala_calisiyor(client):
    """HEAD eklerken GET yolu bozulmamalı (FAL_KEY yokken 503 beklenir)."""
    r = await client.get("/api/live-portrait/clip?action=breath")
    assert r.status_code in (200, 503, 502)
    assert r.status_code != 405


@pytest.mark.asyncio
async def test_head_pahali_uretimi_tetiklemez(client, mocker):
    """HEAD, fal.ai klip üretimini ÇAĞIRMAMALI — yoksa yoklama para harcar."""
    uret = mocker.patch(
        "app.api.live_portrait._generate_clip",
        side_effect=AssertionError("HEAD üretimi tetikledi"),
    )
    mocker.patch.dict("os.environ", {"FAL_KEY": "sahte-anahtar"}, clear=False)
    await client.head("/api/live-portrait/clip?action=head_nod")
    uret.assert_not_called()


# ──  (2026-08-28): aynı kusur sınıfı İKİNCİ kez ────────────────────────
# Bu dosya 2026-08-01'de "her sayfa açılışında konsola 405 düşüyordu" diye açıldı.
# Çözüm HEAD desteği eklemekti — ve HEAD, FAL_KEY yokken **503** döndü. Tarayıcı
# 405 için de 503 için de aynı "Failed to load resource" **error** satırını yazar:
# durum kodu değişti, konsoldaki hata değişmedi. 2026-08-28'de ölçüldü, `/ui/`
# açılışında 4xx/5xx dönen TEK istek buydu ve C1 kapısı her müşteride düşüyordu.
#
# 📏 Ders: bir yoklamanın cevabı hata kodu olduğu sürece konsol kirlenir.
# Yetenek sorusu 200 dönen bir uçtan, VERİ olarak sorulur.


@pytest.mark.asyncio
async def test_status_yetenegi_veri_olarak_bildiriyor(client):
    """Arayüz "bu özellik var mı"yı 200 dönen bir uçtan öğrenebilmeli."""
    r = await client.get("/api/live-portrait/status")
    assert r.status_code == 200, "durum ucu hata koduyla cevap veriyor — yine konsol kirlenir"
    d = r.json()
    assert "available" in d, "yetenek alanı yok — arayüz tekrar 503 üreten HEAD'e döner"
    assert isinstance(d["available"], bool)
    assert "unavailable_reason" in d
    if not d["available"]:
        assert d["unavailable_reason"], "kullanılamıyor ama sebep boş — istemci tahmin etmek zorunda kalır"


@pytest.mark.asyncio
async def test_status_fal_key_yokken_kullanilamaz_der(client, monkeypatch, tmp_path):
    """Anahtar yok + önbellek boş → `available: False` ve sebep FAL_KEY'i söylüyor."""
    from app.api import live_portrait as lp
    monkeypatch.delenv("FAL_KEY", raising=False)
    monkeypatch.setattr(lp, "CACHE_DIR", tmp_path)      # boş önbellek
    monkeypatch.setattr(lp, "_FAL_CIRCUIT_OPEN", False)
    d = (await client.get("/api/live-portrait/status")).json()
    assert d["available"] is False
    assert "FAL_KEY" in d["unavailable_reason"]


@pytest.mark.asyncio
async def test_status_onbellekte_klip_varsa_kullanilabilir(client, monkeypatch, tmp_path):
    """🔴 Anahtar yokluğu tek başına yeterli DEĞİL: klip önbellekteyse katman çalışır.

    `available = not FAL_KEY` yazılsaydı, önbelleği dolu bir kurulumda çalışan
    animasyonlar kapatılırdı — düzeltmenin kendisi bir regresyon üretirdi.
    """
    from app.api import live_portrait as lp
    monkeypatch.delenv("FAL_KEY", raising=False)
    (tmp_path / "breath.mp4").write_bytes(b"x")
    monkeypatch.setattr(lp, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(lp, "_FAL_CIRCUIT_OPEN", False)
    d = (await client.get("/api/live-portrait/status")).json()
    assert d["available"] is True, "önbellekteki klipler varken katman gereksiz yere kapatılıyor"


@pytest.mark.asyncio
async def test_status_devre_acikken_kullanilamaz_der(client, monkeypatch, tmp_path):
    """Circuit breaker açıkken önbellek dolu olsa bile katman kullanılamaz sayılır."""
    from app.api import live_portrait as lp
    monkeypatch.setenv("FAL_KEY", "sahte")
    (tmp_path / "breath.mp4").write_bytes(b"x")
    monkeypatch.setattr(lp, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(lp, "_FAL_CIRCUIT_OPEN", True)
    d = (await client.get("/api/live-portrait/status")).json()
    assert d["available"] is False
    assert "devre" in d["unavailable_reason"].lower()
