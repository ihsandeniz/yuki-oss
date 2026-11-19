"""`face_store` — Postgres'siz yüz deposu.

Bu testlerin varlık sebebi: kişiseldeki yüz kodu pgvector'a yaslanıyordu ve
üründe Postgres YOK. Depo yeniden yazıldıysa, pgvector'ın verdiği garantilerin
(kişi başına en iyi mesafe · sıralama · son kaydı koruma) burada da tuttuğu
**ölçülmelidir** — "aynı şeyi yapıyor" bir varsayımdır, test bir ölçümdür.
"""
from __future__ import annotations

import json

import numpy as np
import pytest

from app.services import face_store


@pytest.fixture(autouse=True)
def temiz_depo(tmp_path, monkeypatch):
    """Her test kendi diskinde koşsun — gerçek `data/faces.json`'a dokunma."""
    monkeypatch.setattr(face_store, "_DOSYA", tmp_path / "faces.json")
    monkeypatch.setattr(face_store, "DATA_DIR", tmp_path)
    yield


def _vec(tohum: int, boyut: int = 512) -> np.ndarray:
    """L2-normalize sahte embedding — gerçek `normed_embedding` gibi."""
    rng = np.random.default_rng(tohum)
    v = rng.standard_normal(boyut).astype(np.float32)
    return v / np.linalg.norm(v)


def _yakin(v: np.ndarray, gurultu: float, tohum: int = 99) -> np.ndarray:
    """`v`'ye yakın ama aynı olmayan vektör — aynı kişinin başka karesi gibi.

    ⚠️ Gürültü BOYUTA göre ölçeklenir. Birim vektörün 512 bileşeni ortalama
    1/√512 ≈ 0,044 büyüklüktedir; bileşen başına 0,05 gürültü eklemek "biraz
    farklı kare" değil **bambaşka bir vektör** üretir (ilk sürümde bu yapıldı
    ve test kendi kurgusunu ölçtü, depoyu değil). Bölmeyle `gurultu` yaklaşık
    olarak radyan cinsinden açı sapmasına karşılık gelir.
    """
    rng = np.random.default_rng(tohum)
    u = v + rng.standard_normal(v.shape).astype(np.float32) * (gurultu / np.sqrt(v.size))
    return u / np.linalg.norm(u)


# ── temel ───────────────────────────────────────────────────────────────────
def test_bos_depo_bos_doner():
    assert face_store.kisiler() == []
    assert face_store.en_yakin_kisiler(_vec(1)) == []
    assert face_store.sahip_oku() is None


def test_ekle_ve_listele():
    face_store.ekle("Ayşe", _vec(1))
    face_store.ekle("Ayşe", _vec(2))
    face_store.ekle("Mehmet", _vec(3))

    kisiler = {k["name"]: k for k in face_store.kisiler()}
    assert kisiler["Ayşe"]["encodings"] == 2
    assert kisiler["Mehmet"]["encodings"] == 1
    assert face_store.benzersiz_kisiler() == {"Ayşe", "Mehmet"}


def test_id_ler_tekil_ve_artan():
    a = face_store.ekle("A", _vec(1))
    b = face_store.ekle("A", _vec(2))
    assert b > a


# ── arama: pgvector `<=>` paritesi ─────────────────────────────────────────
def test_en_yakin_kisi_bulunur_ve_siralanir():
    hedef = _vec(10)
    face_store.ekle("Hedef", hedef)
    face_store.ekle("Uzak", _vec(20))

    sonuc = face_store.en_yakin_kisiler(_yakin(hedef, 0.05), limit=2)
    assert sonuc[0][0] == "Hedef"
    assert sonuc[0][1] < sonuc[1][1], "sıralama yakından uzağa olmalı"
    assert 0.0 <= sonuc[0][1] < 0.1


def test_kisi_basina_EN_IYI_mesafe_doner():
    """pgvector'da `MIN(...) GROUP BY name` vardı — parite şart.

    Kişinin kötü bir karesi varsa, o kişi listede EN İYİ karesiyle temsil
    edilmeli. Ortalama alınsaydı, çok kayıtlı bir kişi kendi iyi karesi yüzünden
    değil kötü kareleri yüzünden elenirdi.
    """
    hedef = _vec(10)
    face_store.ekle("Hedef", _vec(77))          # çok uzak, kötü kayıt
    face_store.ekle("Hedef", hedef)             # iyi kayıt
    ad, mesafe = face_store.en_yakin_kisiler(_yakin(hedef, 0.02), limit=1)[0]
    assert ad == "Hedef"
    assert mesafe < 0.05, "en iyi kayıt kullanılmalı, ortalama değil"


def test_kisiye_min_mesafe_yoksa_none():
    assert face_store.kisiye_min_mesafe(_vec(1), "YokKişi") is None
    face_store.ekle("Var", _vec(5))
    assert face_store.kisiye_min_mesafe(_vec(5), "Var") == pytest.approx(0.0, abs=1e-5)


def test_mesafe_kosinus_tanimi():
    """Eşikler (0,45 / 0,35) kosinüs mesafesinde kalibre edildi — tanım kaymamalı."""
    v = _vec(1)
    assert face_store._mesafe(v, v) == pytest.approx(0.0, abs=1e-6)
    assert face_store._mesafe(v, -v) == pytest.approx(2.0, abs=1e-6)


def test_6_basamak_yuvarlama_mesafeyi_bozmuyor():
    """Diske 6 basamakla yazılıyor; bu, eşik yakınında taraf değiştirmemeli."""
    v = _vec(42)
    face_store.ekle("K", v)
    _, mesafe = face_store.en_yakin_kisiler(v, limit=1)[0]
    assert mesafe < 1e-5


# ── silme ───────────────────────────────────────────────────────────────────
def test_son_kaydi_silmek_reddedilir():
    """Kişinin tek kaydını silmek onu tanınmaz yapar — bu sessizce olmamalı."""
    face_store.ekle("Tek", _vec(1))
    with pytest.raises(ValueError, match="tek kaydı"):
        face_store.sil_kayit_denetimli(1)
    assert face_store.kisi_kayit_sayisi("Tek") == 1


def test_ikiden_biri_silinebilir():
    face_store.ekle("Çift", _vec(1))
    ikinci = face_store.ekle("Çift", _vec(2))
    assert face_store.sil_kayit_denetimli(ikinci) == "Çift"
    assert face_store.kisi_kayit_sayisi("Çift") == 1


def test_olmayan_kayit_keyerror():
    with pytest.raises(KeyError):
        face_store.sil_kayit_denetimli(4242)


def test_kisi_silme_tum_kayitlari_goturur():
    face_store.ekle("Sil", _vec(1))
    face_store.ekle("Sil", _vec(2))
    face_store.ekle("Kal", _vec(3))
    assert face_store.sil_kisi("Sil") == 2
    assert face_store.benzersiz_kisiler() == {"Kal"}
    assert face_store.sil_kisi("Sil") == 0


# ── sahiplik ────────────────────────────────────────────────────────────────
def test_sahip_yazilir_ve_kalir():
    face_store.sahip_yaz("Sahip")
    assert face_store.sahip_oku() == "Sahip"
    face_store.ekle("Başkası", _vec(1))
    assert face_store.sahip_oku() == "Sahip", "kayıt eklemek sahibi silmemeli"


# ── dayanıklılık ────────────────────────────────────────────────────────────
def test_bozuk_dosya_yedeklenir_sessizce_silinmez():
    """🔴 Bozuk JSON'u sessizce boş kabul etmek, kullanıcının tüm kayıtlarını atmaktır."""
    face_store.ekle("Veri", _vec(1))
    face_store._DOSYA.write_text("{bu json değil", encoding="utf-8")

    assert face_store.kisiler() == []                      # temiz başlar
    bozuk = face_store._DOSYA.with_suffix(".bozuk")
    assert bozuk.exists(), "bozuk dosya YEDEKLENMELİ, silinmemeli"
    assert "bu json değil" in bozuk.read_text(encoding="utf-8")


def test_yazma_atomik_gecici_dosya_birakmaz():
    face_store.ekle("A", _vec(1))
    artiklar = list(face_store._DOSYA.parent.glob(".faces-*.tmp"))
    assert artiklar == [], f"geçici dosya kaldı: {artiklar}"


def test_eksik_alanli_dosya_kurtarilir():
    """Elle düzenlenmiş / eski şemalı dosya patlamamalı."""
    face_store._DOSYA.write_text(json.dumps({"faces": []}), encoding="utf-8")
    assert face_store.kisiler() == []
    face_store.ekle("Yeni", _vec(1))
    assert face_store.kisi_kayit_sayisi("Yeni") == 1
