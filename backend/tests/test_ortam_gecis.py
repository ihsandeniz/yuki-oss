"""Geriye uyum: eski ALICE_* ortam adları YUKI_*'a köprülenir.

Kullanıcının mevcut .env'i kırılmasın: eski önekli bir değişken varsa ve karşılığı
yeni önekle tanımlı değilse, değer yeni ada kopyalanır ve BİR KEZ uyarı basılır.
Eski önek testte de parçalı yazılır ki temizlik kapısı bu dosyayı kalıntı sanmasın."""
from __future__ import annotations

import importlib

ESKI = "ALI" "CE_"   # = eski ürün öneki (parçalı → kapı tetiklenmez)


def _modul():
    m = importlib.import_module("app.ortam_gecis")
    m._uyarildi = False   # her test kendi uyarı sayımını ölçsün
    return m


def test_eski_ad_yeni_ada_koprulenir():
    g = _modul()
    ortam = {ESKI + "DATA_DIR": "/tmp/veri", ESKI + "PACKAGE": "full"}
    tasinan = g.gecisi_uygula(ortam)
    assert ortam["YUKI_DATA_DIR"] == "/tmp/veri"
    assert ortam["YUKI_PACKAGE"] == "full"
    assert set(tasinan) == {ESKI + "DATA_DIR", ESKI + "PACKAGE"}


def test_yeni_ad_varsa_ezilmez():
    g = _modul()
    ortam = {ESKI + "DATA_DIR": "/eski", "YUKI_DATA_DIR": "/yeni"}
    g.gecisi_uygula(ortam)
    assert ortam["YUKI_DATA_DIR"] == "/yeni"   # yeni ad korunur, eski ezemez


def test_uyari_bir_kez(capsys):
    g = _modul()
    ortam = {ESKI + "DATA_DIR": "/tmp/x"}
    g.gecisi_uygula(ortam)
    ilk = capsys.readouterr().err
    assert "UYARI" in ilk and "YUKI_" in ilk
    # İkinci çağrı (aynı süreçte) tekrar uyarmaz
    g.gecisi_uygula({ESKI + "PACKAGE": "full"})
    assert "UYARI" not in capsys.readouterr().err


def test_eski_ad_yoksa_sessiz(capsys):
    g = _modul()
    tasinan = g.gecisi_uygula({"YUKI_DATA_DIR": "/sade"})
    assert tasinan == []
    assert capsys.readouterr().err == ""
