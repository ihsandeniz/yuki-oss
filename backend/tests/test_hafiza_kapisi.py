"""Semantik hafıza (Ultra) kapısı — HER uçta, yeni uçlar dâhil.

🔴 Neden bu dosya var: `semantic_memory` kapısı `FEATURE_DURUM`'da "uygulandi"
yazıyordu ve gerçekten de dört uçta uygulanmıştı. Ama `api/memory.py`'de dokuz
uç var. Aynı sınıf kusur **iki kez** çıktı:

  · 2026-07-28 — bir uç atlanmış (o turda kapatıldı)
  · 2026-08-06 — SATILAN PAKETTE ölçüldü (Yuki-0.5.8-lite.AppImage,
    `--appimage-mount`, paketin kendi pybundle'ıyla backend ayağa kaldırılıp
    Free kademede uçlar tek tek yoklandı). Dört uç kapısızdı:
        GET  /api/memory/export      → anıların TAM İÇERİĞİNİ döktü
        DELETE /api/memory/{id}      → Ultra anısını gerçekten SİLDİ (200)
        POST /api/memory/cleanup     → toplu temizlik çalıştı (200)
        PUT  /api/memory/{id}        → kapı yok; yalnızca eksik embedding
                                       modeli 500'e düşürüyordu (tesadüf)
    Aynı anda `list` boş liste, `stats` `total: 0` diyordu → panel "hafıza yok"
    derken export her şeyi veriyordu.

Ders: **uç uç test etmek yetmez, sayı büyüyor.** Bu dosya kapıyı uç listesinden
DEĞİL, router'ın kendisinden türetir — yarın eklenen bir uç kendiliğinden
denetime girer. Kapısız kalan her yeni uç burayı kırmızı yakar.
"""
from __future__ import annotations

import inspect

import pytest

from app.api import memory as memory_api

# Kapıyı uygulayan sembollerden biri handler'ın gövdesinde geçmek ZORUNDA.
KAPI_SEMBOLLERI = ("_require_semantic", "_semantic_entitled")

# Bilinçli istisna — kapı GEREKMEZ, gerekçesi burada yazılı olmak zorunda.
# Yeni istisna eklemek isteyen, veri sızdırmadığını burada savunmak zorunda.
ISTISNALAR: dict[str, str] = {
    "memory_engine": (
        "Yalnız motor DURUMUNU bildirir (backend/model var mı, allowed mı) — "
        "anı içeriği dönmez. Frontend'in 'model indirilsin mi' kararı buna bakar; "
        "kapatmak Ultra kullanıcısının model indirme yolunu kapatırdı."
    ),
}


def _hafiza_handlerlari():
    """Router'daki her uç → (ad, metotlar, yol, kaynak)."""
    for route in memory_api.router.routes:
        fn = getattr(route, "endpoint", None)
        if fn is None:
            continue
        yield fn.__name__, sorted(getattr(route, "methods", []) or []), route.path, inspect.getsource(fn)


def test_her_hafiza_ucunun_kapisi_var():
    """Kapısız uç = paywall deliği ya da veri sızıntısı. İstisna yazılı olmalı."""
    kapisiz = []
    for ad, metotlar, yol, kaynak in _hafiza_handlerlari():
        if ad in ISTISNALAR:
            continue
        if not any(s in kaynak for s in KAPI_SEMBOLLERI):
            kapisiz.append(f"{'/'.join(metotlar)} {yol} ({ad})")
    assert not kapisiz, (
        "semantik hafıza kapısı olmayan uç(lar): " + ", ".join(kapisiz) + "\n"
        "Ya kapıyı ekle (_require_semantic → yazma/yıkıcı yol; _semantic_entitled "
        "→ okuma yolunu boşa düşür) ya da ISTISNALAR'a gerekçesiyle yaz."
    )


def test_istisna_listesi_hayalet_kayit_tutmuyor():
    """Silinen bir uç istisnada kalırsa liste sessizce bayatlar."""
    adlar = {ad for ad, _, _, _ in _hafiza_handlerlari()}
    fazla = set(ISTISNALAR) - adlar
    assert not fazla, f"artık var olmayan uç istisnada duruyor: {fazla}"


def test_istisnalarin_gerekcesi_yazili():
    for ad, gerekce in ISTISNALAR.items():
        assert len(gerekce.strip()) > 40, f"{ad}: istisna gerekçesi çok kısa/boş"


# ── Davranışsal: Free kademede gerçekten reddediyor mu ────────────────
# Sembol varlığı yetmez (multi_character dersi 2026-08-02: kapı vardı ama
# özellik adı üzerinden değildi). Aşağısı gerçek HTTP davranışını ölçer.

@pytest.fixture
def yetkisiz(mocker):
    """Yetki kapalı — gerçek kapı fonksiyonunun okuduğu kaynağı (yetki.feature_allowed) kıs."""
    mocker.patch(
        "app.services.yetki.feature_allowed",
        side_effect=lambda f, *a, **k: False if f == "semantic_memory" else True,
    )
    mocker.patch.object(memory_api, "MEMORY_ENABLED", True)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "metot,yol",
    [
        ("GET", "/api/memory/export"),        # 🔴 tam içeriği döküyordu
        ("PUT", "/api/memory/1"),
        ("DELETE", "/api/memory/1"),
        ("POST", "/api/memory/cleanup"),
        ("POST", "/api/memory"),              # zaten kapalıydı — regresyon çapası
    ],
)
async def test_yetkisizde_yazma_ve_disa_aktarma_403(client, yetkisiz, metot, yol):
    r = await client.request(metot, yol, json={"content": "x", "importance": 0.5})
    assert r.status_code == 403, (
        f"{metot} {yol} → {r.status_code} (403 bekleniyordu). "
        "Yetkisiz kademe bu ucu kullanabiliyor."
    )


@pytest.mark.asyncio
async def test_export_ani_icerigi_sizdirmiyor(client, yetkisiz):
    """Asıl bulgunun çapası: gövdede tek bir anı bile dönmemeli."""
    r = await client.get("/api/memory/export")
    assert r.status_code == 403
    assert "memories" not in r.text, "403 gövdesinde bile anı alanı dönüyor"


@pytest.mark.asyncio
async def test_okuma_yolu_403_yerine_bos_donuyor(client, yetkisiz):
    """Panel açılışında çağrılan uçlar UI'ı kırmamalı — boş, ama sızdırmadan."""
    r = await client.get("/api/memory")
    assert r.status_code == 200 and r.json() == []

    s = await client.get("/api/memory/stats")
    assert s.status_code == 200
    assert s.json().get("total") == 0


# ── Gömme modeli yokken (README yolu: MEMORY_BACKEND=sqlite, EMBED_ONNX_DIR yok) ──────────
# Eskiden POST /api/memory ve /search ModuleNotFoundError('sentence_transformers') → 500
# "Beklenmeyen hata" veriyordu (temiz klonda ölçüldü).

@pytest.fixture
def modelsiz(mocker):
    mocker.patch.object(memory_api, "MEMORY_ENABLED", True)
    mocker.patch("app.services.llm._embedding_engine_ready", return_value=False)
    servis = mocker.MagicMock()
    servis.add.side_effect = AssertionError("model yokken servise inilmemeli")
    servis.search.side_effect = AssertionError("model yokken servise inilmemeli")
    servis.update.side_effect = AssertionError("model yokken servise inilmemeli")
    mocker.patch.object(memory_api, "get_memory_service", return_value=servis)
    return servis


@pytest.mark.asyncio
async def test_modelsiz_ekleme_anlasilir_503(client, modelsiz):
    r = await client.post("/api/memory", json={"content": "Kedimin adı Pamuk"})
    assert r.status_code == 503, r.text
    assert "EMBED_ONNX_DIR" in r.text


@pytest.mark.asyncio
async def test_modelsiz_icerik_guncelleme_503(client, modelsiz):
    r = await client.put("/api/memory/1", json={"content": "yeni"})
    assert r.status_code == 503, r.text


@pytest.mark.asyncio
async def test_modelsiz_anlamsal_arama_bos(client, modelsiz):
    r = await client.get("/api/memory/search", params={"q": "kedi"})
    assert r.status_code == 200 and r.json() == []


@pytest.mark.asyncio
async def test_modelsiz_yalniz_onem_guncellemesi_calisir(client, modelsiz):
    """Önem güncellemesi vektöre dokunmaz; model yokken de çalışmalı (kapı aşırı genişlemesin)."""
    async def _guncelle(memory_id, importance=None, content=None):
        assert content is None
        return True
    modelsiz.update.side_effect = _guncelle
    r = await client.put("/api/memory/1", json={"importance": 0.9})
    assert r.status_code == 200, r.text
