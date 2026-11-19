"""`models-manifest.json` mevcut müşteriye GERÇEKTEN ulaşıyor mu?

🔴 NEDEN VAR (2026-09-05 Dalga 2 düşmanca turu):

Manifest, indir-gerektiğinde yüklerin kayıt defteridir; her yeni yükle DEĞİŞİR.
Ama iki bağımsız yerde kopuktu ve ikisi de **sessiz**di:

  ① `scripts/update_payload.py` delta yükünde `electron/` altından yalnız
     `.js/.html/.css` taşıyor. Manifest `.json` → yüke HİÇ GİRMİYORDU.
  ② `electron/uygulama.js` manifesti `PAKET_KOK`'ten okuyordu (paketin kendisi),
     `kaynak()`'ten değil → delta ile gelen kopya kullanılmazdı.

Sonuç: yeni bir yük (ör. yüz tanıma kütüphanesi) eklendiğinde `.js` dosyaları
delta ile giderdi, manifest ESKİ kalırdı → `model-manager.js` *"Bilinmeyen
model"* der, özellik ölü doğar. Sürüm notu "yeni özellik" derken müşteride
hiçbir şey açılmaz; hata mesajı da yanlış yeri gösterir.

📏 v0.6.13'ün dersi burada tekrarlandı: *yamanın müşteriye ULAŞTIĞI ölçülmeli.*
Aynı ailenin üçüncü vakası — `pybundle` taranmıyordu, `fitness.py` paketten
düşmüştü, şimdi manifest delta'ya girmiyordu.

Bu test iki ucu da mekanik olarak kilitler.
"""
from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[2]          # → depo kökü
MANIFEST_ADI = "models-manifest.json"


def _update_payload():
    yol = KOK / "scripts" / "update_payload.py"
    spec = importlib.util.spec_from_file_location("_up", yol)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_manifest_delta_yukune_giriyor():
    """① Yük üreticisi manifesti taşıyor mu — uzantı beyaz listesine takılmasın."""
    up = _update_payload()
    yollar = [arsiv_yolu for _, arsiv_yolu in up._yuk_dosyalari()]
    assert f"electron/{MANIFEST_ADI}" in yollar, (
        f"{MANIFEST_ADI} delta yükünde YOK → yeni indirilebilir yükler mevcut "
        f"müşteriye hiç ulaşmaz ('Bilinmeyen model' hatası). "
        f"update_payload.py → ELECTRON_EK_DOSYA"
    )


def test_manifest_yasakli_listede_degil():
    """Kabuk kimliği dosyaları güncellenemez; manifest onlardan DEĞİL — veri."""
    up = _update_payload()
    assert MANIFEST_ADI not in up.ELECTRON_YASAK


def test_uygulama_manifesti_KATMANLI_okuyor():
    """② Delta ile gelen manifest fiilen kullanılıyor mu?

    `PAKET_KOK` paketin kendisidir (salt-okunur, delta oraya yazamaz).
    Katmanlı çözüm `kaynak()` — overlay'de varsa oradan alır. Manifest
    `PAKET_KOK`'ten okunursa ① düzeltilse bile yeni yükler görünmez.
    """
    # Yorumlarda da geçtiği için ADA göre değil, ATAMAYA göre eşle: aradığımız
    # şey manifestin nereden okunduğu, nerede anıldığı değil.
    kaynak_metin = (KOK / "electron" / "uygulama.js").read_text(encoding="utf-8")
    satirlar = [s for s in kaynak_metin.splitlines() if "manifestPath:" in s]
    assert satirlar, "manifestPath ataması bulunamadı — test bayatlamış olabilir"
    for s in satirlar:
        assert "kaynak(" in s, (
            f"manifest katmansız okunuyor → delta ile gelen kopya kullanılmaz:\n  {s.strip()}"
        )
        assert "PAKET_KOK" not in s, (
            f"manifest PAKET_KOK'ten okunuyor (paket salt-okunur, delta oraya yazamaz):\n  {s.strip()}"
        )


def test_manifest_gecerli_json_ve_sozlesmeye_uygun():
    """Yük kaydı sözleşmesi: `models` altındakiler indirilebilir SAYILIR.

    Bu yüzden url/sha256'sı olmayan bir kayıt `models` altında durmamalı —
    manifestin kendi kuralı; UI 'indir' gösterip indirme anında patlar.
    """
    import json
    veri = json.loads((KOK / "electron" / MANIFEST_ADI).read_text(encoding="utf-8"))

    for mid, m in veri.get("models", {}).items():
        assets = m.get("assets")
        girdiler = list(assets.values()) if assets else [m]
        for a in girdiler:
            assert a.get("url"), f"{mid}: 'models' altında ama url yok"
            sha = a.get("sha256", "")
            assert re.fullmatch(r"[0-9a-fA-F]{64}", sha), f"{mid}: geçersiz sha256"

    for mid, m in veri.get("plannedModels", {}).items():
        # 'yakında' kayıtları indirilebilir SAYILMAZ; burada url olması sorun
        # değil (yüklenmemiş olabilir), `models` altına terfi `--dogrula` ile olur.
        assert "presenceDir" in m, f"{mid}: presenceDir yok"

    # pydeps kayıtlarında extractTo ile presenceDir AYNI OLMAMALI — açıcı hedefi
    # kendisi mkdir'liyor, aynıysa boş arşiv "kuruldu" sayılır (2026-09-05 ölçümü).
    for bolum in ("models", "plannedModels"):
        for mid, m in veri.get(bolum, {}).items():
            if m.get("kind") == "pydeps":
                assert m.get("presenceDir") != m.get("extractTo"), (
                    f"{mid}: presenceDir == extractTo → boş arşiv 'kuruldu' sayılabilir"
                )
