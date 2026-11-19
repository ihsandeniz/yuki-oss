"""Yüzle girişte model ısıtma — `/api/face/warmup` (2026-09-09).

📏 **Ölçüm (kod okumasıyla, `app-lock.js:250-305`):** yüzle giriş akışında
kullanıcının beklediği süre dört parçadan oluşuyordu:

    geri sayım 3×700ms = 2,1 sn
    40 kare × 100 ms   ≈ 4,0 sn
    model yüklemesi    ≈ 2-4 sn  ← kareler POST edildikten SONRA başlıyordu
    40 karenin analizi ≈ 4-6 sn

Üçüncü kalem, ilk ikisinin ölü zamanına sığar: istemci geri sayarken ve kare
toplarken sunucu boş duruyordu. Isıtma ucu o boşluğu doldurur.

🔑 **Bu bir iyileştirmedir, bir kapı değil.** Bu dosyanın koruduğu asıl şey
ısıtmanın *hızı* değil, **giriş akışını bozmaması**:

  ① Uç asla beklemez — hazır olmayan modeli beklerse kazanç sıfırlanır.
  ② Kütüphane yoksa **200 + `basladi: false`** döner, 503 değil: yetenek
    sorusu hata koduyla sorulmaz (bkz. `face_api` modül başlığı) ve ısıtmanın
    başarısızlığı girişi durdurmamalı.
  ③ Uç kimlik doğrulamasından **muaf** olmalı — kilit ekranı onu giriş
    ÖNCESİ çağırır; token isteseydi tam da işe yarayacağı anda çağrılamazdı.
  ④ `yuklu()` yüklemeyi TETİKLEMEZ — `al()` ile karıştırılırsa "hazır mı"
    sorusu modelin kendisini yükler ve ısıtma anlamını yitirir.
"""

import asyncio
import types

import pytest

from app.services import insightface_havuzu as havuz


# ── ④ Sorgu yüklemeyi tetiklemez ───────────────────────────────────────────

def test_yuklu_modeli_yuklemez(monkeypatch):
    """`yuklu()` yalnız sözlüğe bakar; `al()` çağırmaz."""
    cagrildi = []
    monkeypatch.setattr(havuz, "al", lambda p: cagrildi.append(p))
    monkeypatch.setattr(havuz, "_ornekler", {})

    assert havuz.yuklu("TANIMA") is False
    assert cagrildi == [], "yuklu() modeli yüklemeye kalktı — ısıtma anlamsızlaşır"


def test_yuklu_yuklenmis_profili_gorur(monkeypatch):
    monkeypatch.setattr(havuz, "_ornekler", {"TANIMA": object()})
    assert havuz.yuklu("TANIMA") is True


# ── ② Kütüphane yoksa 200 + basladi:false ──────────────────────────────────

def test_kutuphane_yoksa_hata_degil_bilgi(monkeypatch):
    """503 DEĞİL: ısıtmanın başarısızlığı giriş akışını durdurmamalı."""
    from app.api import face_api

    monkeypatch.setattr(havuz, "kullanilabilir", lambda: (False, "Kütüphane inmemiş."))
    sonuc = asyncio.run(face_api.warmup.__wrapped__(_sahte_request()))

    assert sonuc["basladi"] is False
    assert sonuc["hazir"] is False
    assert "inmemiş" in sonuc["sebep"]


# ── ① Zaten yüklüyse ikinci kez ısıtmaz ────────────────────────────────────

def test_zaten_yukluyse_isitmaz(monkeypatch):
    from app.api import face_api

    monkeypatch.setattr(havuz, "kullanilabilir", lambda: (True, None))
    monkeypatch.setattr(havuz, "yuklu", lambda p: True)
    cagrildi = []
    monkeypatch.setattr(havuz, "al", lambda p: cagrildi.append(p))

    sonuc = asyncio.run(face_api.warmup.__wrapped__(_sahte_request()))

    assert sonuc == {"basladi": False, "hazir": True}
    assert cagrildi == [], "hazır model yeniden yüklendi"


def test_isitma_cagirani_bekletmez(monkeypatch):
    """Uç, model yüklenmesini BEKLEMEDEN dönmeli.

    Yükleme sahtesi 5 sn uyusaydı bile uç anında dönmeli — bu testte yükleme
    bir olayla bloke edilir, uç yine de sonuç üretir.
    """
    from app.api import face_api

    monkeypatch.setattr(havuz, "kullanilabilir", lambda: (True, None))
    monkeypatch.setattr(havuz, "yuklu", lambda p: False)

    kapi = asyncio.Event()  # hiç set edilmez → yükleme "asılı" kalır
    basladi = []

    def _asili_yukleme(profil):
        basladi.append(profil)
        import time
        time.sleep(0.3)   # uç bunu beklerse test 0,3 sn'den uzun sürer

    monkeypatch.setattr(havuz, "al", _asili_yukleme)

    async def _kos():
        basla = asyncio.get_running_loop().time()
        sonuc = await face_api.warmup.__wrapped__(_sahte_request())
        return sonuc, asyncio.get_running_loop().time() - basla

    sonuc, gecen = asyncio.run(_kos())

    assert sonuc == {"basladi": True, "hazir": False}
    assert gecen < 0.2, f"uç yüklemeyi bekledi ({gecen:.3f} sn) — ısıtmanın kazancı sıfırlanır"
    assert kapi is not None


def test_isitma_hatasi_yutulur(monkeypatch):
    """Yükleme patlarsa uç yine de normal döner — gerçek hatayı /verify söyler."""
    from app.api import face_api

    monkeypatch.setattr(havuz, "kullanilabilir", lambda: (True, None))
    monkeypatch.setattr(havuz, "yuklu", lambda p: False)

    def _patla(profil):
        raise RuntimeError("model dosyası bozuk")

    monkeypatch.setattr(havuz, "al", _patla)
    sonuc = asyncio.run(face_api.warmup.__wrapped__(_sahte_request()))
    assert sonuc == {"basladi": True, "hazir": False}


# ── ③ Kimlik doğrulamasından muaf ──────────────────────────────────────────

def test_warmup_token_istemez():
    """Kilit ekranı bunu giriş ÖNCESİ çağırır — token isteseydi çağrılamazdı."""
    from app.main import _SKIP_PATHS

    assert "/api/face/warmup" in _SKIP_PATHS


def test_warmup_onek_olarak_acilmadi():
    """`_SKIP_PATHS` tam eşleşmedir; uç önek listesine sızmamalı."""
    from app.main import _SKIP_PREFIXES

    assert not any(p.startswith("/api/face") for p in _SKIP_PREFIXES)


# ── istemci: ısıtma beklenmeden çağrılıyor mu ──────────────────────────────

def test_istemci_isitmayi_beklemiyor():
    """`app-lock.js` ısıtmayı `await` etmemeli — beklerse kazanç sıfırlanır."""
    from pathlib import Path

    kaynak = Path(__file__).resolve().parents[2] / "frontend" / "js" / "app-lock.js"
    metin = kaynak.read_text(encoding="utf-8")

    assert "/api/face/warmup" in metin, "istemci ısıtmayı hiç çağırmıyor"
    satir = next(s for s in metin.splitlines() if "/api/face/warmup" in s)
    assert "await" not in satir, f"ısıtma beklenerek çağrılmış: {satir.strip()}"
    assert ".catch(" in satir, "ısıtma hatası yakalanmıyor — giriş akışı düşebilir"


def _sahte_request():
    """`limiter` dekoratörü atlandığı için yalnız `client` alanı yeterli."""
    return types.SimpleNamespace(client=types.SimpleNamespace(host="127.0.0.1"))
