"""Fitnes v2 — oyun motoru (P2): saf kurallar + depo katmanı.

Korunan şeyler:
  ① dokunulmamış (şablondan gelen) set XP/rekor üretmez; girildi ya da completed sayılır
  ② seviye eğrisi 100·L^1.25, Epley e1RM 1-12 tekrar
  ③ süreli hareket "(sn)" tonaja ve rekora girmez
  ④ lig: Gölge'nin %110'u terfi, deload/dondurma değerlendirilmez
  ⑤ olay günlüğü tekil anahtarlı: aynı kutlama iki kez yazılmaz
  ⑥ ilk çalışma: geçmiş tarihli olay "görüldü" yazılır, bugünkü bekler
  ⑦ unvan kalıcı: kayıt silinse de kalır; dayanağı giden beceri "askida"
  ⑧ Pazartesi 08:30'dan önce haftalık özet doğmaz
  ⑨ metinler arayüz diline uyar (tr/en)
"""
from datetime import date, datetime, timedelta

import pytest

from app.services import fitness_oyun as F

PZT = date(2026, 11, 9)   # pazartesi


def _set(tarih, ad="Squat", kilo=100, tekrar=5, tamam=True, **ek):
    return {"tarih": tarih, "ad": ad, "kilo": kilo, "tekrar": tekrar, "tamam": tamam, "olusturma": None,
            "oturum": str(tarih), **ek}


def _veri(setler=(), ogunler=(), plan=(1, 3, 5), tur=None):
    return {"setler": list(setler), "ogunler": list(ogunler), "hedef": {"kal": 2000, "protein": 150},
            "plan_gunleri": list(plan), "hafta_turu": tur or {}}


# ── saf kurallar ───────────────────────────────────────────────────────────────

def test_egri_ve_seviye():
    assert [F.gereken(L) for L in (1, 2, 10)] == [100, 238, 1778]
    assert F.seviye(0) == 1 and F.seviye(99.9) == 1 and F.seviye(100) == 2
    assert F.seviye(F.kumulatif(7)) == 7


def test_e1rm_aralik_ve_set_xp():
    assert F.e1rm(100, 5) == pytest.approx(116.6667, rel=1e-4)
    assert F.e1rm(100, 0) is None and F.e1rm(100, 13) is None
    assert F.set_xp(100, 5, True) == 20 and F.set_xp(100, 5, False) == 0
    assert F.set_xp(200, 10, True) == 30, "kilo×tekrar payı en çok 20"


def test_dokunulmamis_sablon_seti_sayilmaz():
    d = F.durum_hesapla(_veri([_set(PZT, tamam=False, girildi=None)]), PZT)
    assert d["xp_toplam"] == 0 and d["stat"]["guc"] == 0
    d2 = F.durum_hesapla(_veri([_set(PZT, tamam=False, girildi="2026-11-09T10:00:00")]), PZT)
    assert d2["xp_toplam"] > 0, "girildi damgalı set yapılmış sayılır"


def test_sureli_hareket_tonaj_ve_rekor_disi():
    assert F.set_tonaj("Plank (sn)", 10, 60) == 0
    assert F.set_tonaj("Squat", 100, 5, [{"kg": 80, "tekrar": 5}]) == 900
    d = F.durum_hesapla(_veri([_set(PZT, ad="Squat (sn)", kilo=100, tekrar=5)]), PZT)
    assert not [o for o in d["olaylar"] if o["tur"] == "REKOR"]


def test_normal_ad_turkce():
    assert F.normal_ad("  Ölü   Kaldırma ") == "olu kaldirma"
    assert F.hareket_kodu("İNCLİNE") is None and F.hareket_kodu("Bench Press") == "bench"


def test_lig_terfi_ve_dondurma():
    H = lambda xp, tuttu=False, tur="normal": {"xp": xp, "tuttu": tuttu, "tur": tur}  # noqa: E731
    assert F.rutbe_gecmisi([H(100), H(100), H(115)]) == ["E", "E", "D"]
    assert F.rutbe_gecmisi([H(100), H(100), H(500, tur="dondurma")]) == ["E", "E", "E"]


def test_hafta_turu_kurali():
    assert F.hafta_turu_kontrol({}, PZT, "deload") is None
    assert F.hafta_turu_kontrol({PZT - timedelta(days=14): "deload"}, PZT, "deload")
    assert F.hafta_turu_kontrol({}, PZT + timedelta(days=1), "deload"), "pazartesi olmalı"
    assert F.hafta_turu_kontrol({}, PZT, "dondurma", bugun=PZT + timedelta(days=8)), "bitmiş hafta"


def test_rekor_olayi_tekil_anahtarli():
    d = F.durum_hesapla(_veri([_set(PZT)]), PZT)
    rek = [o for o in d["olaylar"] if o["tur"] == "REKOR"]
    assert len(rek) == 1 and rek[0]["anahtar"].startswith(f"pr:squat:{PZT}")
    assert "100 kg × 5" in rek[0]["metin"]


def test_metin_ingilizceye_doner(monkeypatch):
    from app.services import fitnes_metin
    monkeypatch.setattr(fitnes_metin, "dil", lambda: "en")
    d = F.durum_hesapla(_veri([_set(PZT)]), PZT)
    assert d["lig_ad"] == "Ash"
    assert "new personal record" in [o for o in d["olaylar"] if o["tur"] == "REKOR"][0]["metin"]


# ── depo katmanı ───────────────────────────────────────────────────────────────

@pytest.fixture()
def depo(tmp_path, monkeypatch):
    from app.services import fitness_store as fs
    monkeypatch.setattr(fs, "_STORE_FILE", tmp_path / "fitness_store.json")
    return fs


def _yap(depo, gun, ad="Squat", kg=100, tekrar=5):
    ex = depo.add_exercise(ad, [{"reps": tekrar, "weight": kg}], session_date=gun.isoformat())
    depo.update_exercise_sets(ex["id"], [{"id": ex["sets"][0]["id"], "reps": tekrar, "weight": kg,
                                          "dokunuldu": True}])
    return ex


def test_olay_iki_kez_yazilmaz(depo):
    _yap(depo, PZT)
    ilk = F.olay_uret(PZT)
    assert any(o["tur"] == "REKOR" for o in ilk)
    assert F.olay_uret(PZT) == [], "aynı anahtar ikinci turda yazılmaz"


def test_ilk_calisma_gecmis_olayi_goruldu_yazar(depo):
    _yap(depo, PZT - timedelta(days=3))
    _yap(depo, PZT, kg=110)
    F.olay_uret(PZT)
    rek = {o["veri"]["tarih"]: o["goruldu"] for o in depo._load()["olaylar"] if o["tur"] == "REKOR"}
    assert rek[(PZT - timedelta(days=3)).isoformat()] is True
    assert rek[PZT.isoformat()] is False
    assert any(o["anahtar"] == f"surum:{F.HESAP_SURUMU}" for o in depo._load()["olaylar"])


def test_unvan_kalici_beceri_askida(depo):
    with depo.islem() as db:
        db["olaylar"].append({"id": "x", "anahtar": "surum:2", "tur": "SURUM", "metin": "", "veri": {"tarih": "2000-01-01"},
                              "olustu": "2000-01-01", "goruldu": True, "teslim": None, "itildi": None})
    exler = [_yap(depo, PZT - timedelta(days=i), kg=150) for i in range(0, 1)]
    d = F.durum(PZT)
    assert any(b["kod"] == "agir_yuk" and b["durum"] == "edinildi" for b in d["beceriler"])
    for ex in exler:
        depo.delete_exercise(ex["id"])
    d2 = F.durum(PZT)
    assert next(b for b in d2["beceriler"] if b["kod"] == "agir_yuk")["durum"] == "askida"


def test_bekleyen_olaylar_sirali_ve_goruldu_dusurur(depo):
    _yap(depo, PZT)
    d = F.durum(PZT)
    turler = [o["tur"] for o in d["bekleyen_olaylar"]]
    assert "REKOR" in turler
    assert turler == sorted(turler, key=lambda x: F.SIRA.get(x, 9))
    assert all(o["teslim"] for o in d["bekleyen_olaylar"])


def test_pazartesi_ozet_saat_kapisi(depo):
    gecen = PZT - timedelta(days=7)
    _yap(depo, gecen)
    erken = datetime.combine(PZT, datetime.min.time()).replace(hour=7)
    F.olay_uret(PZT, simdi=erken)
    assert not any(o["tur"] == "HAFTALIK_OZET" for o in depo._load()["olaylar"])
    F.olay_uret(PZT, simdi=erken.replace(hour=9))
    assert any(o["tur"] == "HAFTALIK_OZET" for o in depo._load()["olaylar"])


def test_haftalik_ozet_pazartesi_ister(depo):
    with pytest.raises(ValueError):
        F.haftalik_ozet(PZT + timedelta(days=1))
    _yap(depo, PZT)
    oz = F.haftalik_ozet(PZT, PZT + timedelta(days=7))
    assert oz["antrenman"]["yapilan_set"] == 1 and oz["hafta"] == PZT.isoformat()
