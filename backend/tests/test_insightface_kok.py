"""`buffalo_l` modelinin indiği kök — 'ün kök nedeni.

🔴 **Neden bu dosya var:** `electron/uygulama.js` yıllardır `INSIGHTFACE_HOME`
ortam değişkenini set ediyordu ve backlog notu buna dayanarak *"model
models-cache'e yönlendirilmiş, çift indirme yok"* diyordu. **insightface o
değişkeni hiç okumuyor** — kök `FaceAnalysis(root='~/.insightface')` varsayılan
parametresinden geliyor. Ölçüm (2026-09-06, bu makine): `~/.insightface` **601 MB**
(açılmış model + silinmemiş 289 MB zip), tarih 29 Mayıs.

Yani yönlendirme *"vardı ama çalışmıyordu"*. Bu testler onu tekrar sessizce
kaybetmemizi engelliyor: `root=` parametresi kaldırılırsa ya da `model_koku()`
env'i okumayı bırakırsa kırmızı yanar.
"""

import re
from pathlib import Path

import pytest

from app.services import insightface_havuzu as havuz

KAYNAK = Path(havuz.__file__)


def test_env_verilince_o_kok_kullanilir(tmp_path, monkeypatch):
    monkeypatch.setenv("INSIGHTFACE_HOME", str(tmp_path / "models-cache" / "insightface"))
    kok = havuz.model_koku()
    assert kok == str(tmp_path / "models-cache" / "insightface")
    # Dizin ÖNCEDEN açılmalı: insightface indirmeye başlarken var olmayan bir
    # köke yazmaya çalışırsa indirme yarıda patlar.
    assert Path(kok).is_dir()


def test_env_yoksa_insightface_varsayilanina_dusulur(monkeypatch):
    """Değişken yoksa davranış DEĞİŞMEMELİ — kendi yolumuzu dayatmıyoruz."""
    monkeypatch.delenv("INSIGHTFACE_HOME", raising=False)
    assert havuz.model_koku() == "~/.insightface"


def test_bos_env_varsayilana_dusulur(monkeypatch):
    """Boş string 'yol verildi' sayılmamalı — `Path('')` çalışma dizinini gösterir
    ve model projenin içine inerdi."""
    monkeypatch.setenv("INSIGHTFACE_HOME", "")
    assert havuz.model_koku() == "~/.insightface"


def test_tilde_genisletilir(tmp_path, monkeypatch):
    """`~` genişletilmezse insightface `./~/...` diye gerçek bir dizin açar."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("INSIGHTFACE_HOME", "~/kendi-kokum")
    kok = havuz.model_koku()
    assert "~" not in kok
    assert kok == str(tmp_path / "kendi-kokum")


def test_yazilamayan_kok_ozelligi_OLDURMEZ(monkeypatch):
    """Kök açılamıyorsa ev dizinine düşülür.

    Alternatif — istisna fırlatmak — salt-okunur bir kurulumda yüz tanımayı
    tamamen kapatırdı. Yanlış yere indirmek, hiç indirememekten iyidir; sebep
    log'a düşer.
    """
    monkeypatch.setenv("INSIGHTFACE_HOME", "/proc/olmayan-dizin/kok")
    assert havuz.model_koku() == "~/.insightface"


def test_FaceAnalysis_root_parametresini_GERCEKTEN_geciyor():
    """🔑 Asıl kapı: `model_koku()` doğru çalışsa bile `root=` geçilmezse
    insightface yine ev dizinine iner — kusurun kendisi buydu."""
    kaynak = KAYNAK.read_text(encoding="utf-8")
    blok = kaynak.split("FaceAnalysis(")[1].split(")")[0]
    assert re.search(r"root\s*=", blok), (
        "FaceAnalysis'e `root=` geçilmiyor — model kullanıcının ev dizinine iner "
        "('ün kök nedeni). INSIGHTFACE_HOME'u set etmek YETMEZ, insightface "
        "hiçbir ortam değişkeni okumuyor."
    )


def test_electron_hala_ayni_degiskeni_veriyor():
    """Backend `INSIGHTFACE_HOME` okuyor; Electron onu vermeyi bırakırsa model
    sessizce ev dizinine dönerdi. İki uç ayrı dosyada — bağı test tutuyor."""
    uygulama = KAYNAK.parents[3] / "electron" / "uygulama.js"
    if not uygulama.exists():
        pytest.skip("electron/uygulama.js yok")
    assert "INSIGHTFACE_HOME" in uygulama.read_text(encoding="utf-8"), (
        "Electron INSIGHTFACE_HOME'u artık vermiyor — backend'in kökü boşa düşer"
    )
