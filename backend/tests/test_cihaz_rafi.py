"""CİHAZLAR · CİHAZ RAFI ( panel 13, 2026-10-01 — geliştirici taslak B'yi seçti).

Kapanan kusurlar ve kapıları (her biri panelin gerçek dosyası üzerinde `node` ile ölçülür; mutasyonla kırmızı):

① **Yalancı "henüz cihaz yok".** 401 (oturum kilitli) ve 403 (Ultra değil) boş liste sanılıyordu; çalışmayan
   "Yeni ekle" düğmesi duruyordu. Artık ayrı kart, ekleme yok.
② **Ağ kapalıyken kod üretilebiliyordu** (QR 127.0.0.1'e işaret ederdi). Artık "Cihaz ekle" PASİF, istek gitmez.
③ **Eşleşme panele haber verilmiyordu.** Kod açıkken liste yoklanır; yeni cihaz düşünce çekmece "eşleşti" der.
④ **Çift tık** iki kod üretip birincinin kodunu yakıyordu → tek istek.
⑤ **Süre dolunca** düğme sessizce eski hâline dönüyordu → "Kodun süresi doldu" + yeni kod.
⑥ **Rıza yoktu:** eşleşen cihazda Yuki ekran görüntüsü alır, dosya yazar/siler, komut çalıştırır. Kod üretilmeden
   ÖNCE açıkça listelenir; liste `agent.py` ile eşitlenir (ajan yeni bir eylem kazanırsa test kırmızı olur).
⑦ **Uygulama kilidi yokken ağa açmanın bedeli** söylenir, Güvenlik'e yönlendirilir.
⑧ **Kaldır** `confirm()` değil iki adım; kayıt silinince AÇIK bağlantı da kesilir (eskiden soket açık kaldıkça komut almaya
   devam ederdi — panel "kaldırıldı" derken).
⑨ **"Telefondaki Yuki ajanı" vaadi** kalktı: telefon istemcisi yok, QR'ı okuyan yok → kod metin, komut kopyalanabilir.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from cihaz_panel_kosum import (AG, AG_ACIK, AG_BEKLIYOR, AG_KAPALI, AG_KAPANIS, AG_KILITSIZ, AG_ULASILAMIYOR, C1, C2, C3,
                               DEL_KOD, KOD, LISTE, POST_KOD, PUT_AG, kos, yanit)
from yardim import FRONTEND, sozluk, yorumsuz

PANEL = (FRONTEND / "js" / "cihazlar.js").read_text(encoding="utf-8")
KOK = Path(__file__).resolve().parents[2]


def _son(s):
    return s["adimlar"][-1]["html"]


# ── ① 401 / 403 yalan söylemez ───────────────────────────────────────────────

def test_401_kilitli_der_YALANCI_bos_liste_GOSTERMEZ():
    s = kos({"yanit": yanit(**{AG: [401, {}], LISTE: [401, {}]}), "adimlar": [{"op": "ac"}]})
    h = _son(s)
    assert "cihaz.kilitli-baslik" in h
    assert "cihaz.bos-baslik" not in h, "kilitli kullanıcıya 'henüz cihaz yok' dendi (eşleşmiş cihazları olabilir)"
    assert 'data-cz="ekle"' not in h, "çalışmayan 'Cihaz ekle' duruyor"


def test_ulasilamayan_sunucu_ve_429_ve_500_ayri_cumle():
    for liste, anahtar in (("ag-hatasi", "cihaz.ulasilamadi-baslik"), ([429, {}], "cihaz.cok-sik-baslik"), ([500, {}], "cihaz.hata-baslik")):
        s = kos({"yanit": yanit(**{LISTE: liste}), "adimlar": [{"op": "ac"}]})
        assert anahtar in _son(s), (liste, anahtar)
        assert "cihaz.bos-baslik" not in _son(s)


# ── ② ağ kapalı → ekleme pasif ───────────────────────────────────────────────

def test_ag_kapaliyken_ekle_PASIF_ve_POST_GITMEZ():
    s = kos({"yanit": yanit(ag=AG_KAPALI), "adimlar": [{"op": "ac"}, {"op": "tikla", "g": "ekle"}]})
    h = s["adimlar"][0]["html"]
    assert "cihaz.ag-kapali-baslik" in h, "ağın kapalı olduğu söylenmiyor"
    ekle = re.search(r'<button[^>]*data-cz="ekle"[^>]*>', h).group(0)
    assert "disabled" in ekle, "ağ kapalıyken 'Cihaz ekle' aktif"
    assert not any(c.startswith("POST") for c in s["cagri"]), "ağ kapalıyken kod istendi (127.0.0.1'e işaret ederdi)"
    assert "cihaz.onay-baslik" not in _son(s), "ağ kapalıyken rıza çekmecesi açıldı"


def test_ag_kapali_cozum_ANAHTAR_HOST_metni_YOK():
    """Müşterinin yolu anahtardır: kopyalanabilir `HOST=0.0.0.0` kalktı, hiçbir cümlede HOST geçmez."""
    s = kos({"yanit": yanit(ag=AG_KAPALI), "adimlar": [{"op": "ac"}]})
    h = s["adimlar"][0]["html"]
    assert 'data-cz="ag-ac"' in h and 'role="switch"' in h
    assert "kopya-host" not in h and "HOST" not in h
    assert "HOST" not in yorumsuz(PANEL)


def test_ag_acikken_ekle_aktif():
    s = kos({"yanit": yanit(), "adimlar": [{"op": "ac"}]})
    ekle = re.search(r'<button[^>]*data-cz="ekle"[^>]*>', _son(s)).group(0)
    assert "disabled" not in ekle


def test_ag_durumu_okunamazsa_ekleme_yok_ve_soyler():
    s = kos({"yanit": yanit(**{AG: [500, {}]}), "adimlar": [{"op": "ac"}]})
    h = _son(s)
    assert "cihaz.ag-bilinmiyor" in h and "disabled" in re.search(r'<button[^>]*data-cz="ekle"[^>]*>', h).group(0)


# ── ⑥ rıza: kod üretilmeden ÖNCE ─────────────────────────────────────────────

def test_riza_kod_uretilmeden_ONCE_gosterilir():
    s = kos({"yanit": yanit(), "adimlar": [{"op": "ac"}, {"op": "tikla", "g": "ekle"}, {"op": "tikla", "g": "kod-uret"}]})
    onay = s["adimlar"][1]
    for k in ("ekran", "dosya", "program", "pano"):
        assert f"cihaz.yetki-{k}" in onay["html"], f"rıza listesinde '{k}' yok"
    assert "cihaz.yetki-komut" not in onay["html"], "açık kaynakta komut çalıştırma yok"
    assert not any(c.startswith("POST") for c in onay["cagri"]), "rıza gösterilmeden kod üretildi"
    assert "K7MQ" in s["adimlar"][2]["html"] and POST_KOD in s["cagri"]


def test_riza_listesi_agent_py_ile_ESIT():
    """Rıza metni YALAN olmasın: ajan programı yeni bir eylem öğrenirse (ör. kamera) bu test kırmızı olur ve
    sözlükteki yetki listesi (`cihaz.yetki-*`) güncellenmek zorunda kalır."""
    agent = (KOK / "remote_agent" / "agent.py").read_text(encoding="utf-8")
    eylemler = set(re.findall(r'action == "([a-z_]+)"', agent))
    bilinen = {"sysinfo", "screenshot", "proclist", "filelist", "readfile", "writefile", "deletefile", "killproc",
               "netinfo", "notify", "clipboard_get", "clipboard_set", "diskusage", "ping"}
    assert eylemler == bilinen, f"ajanın eylemleri değişti — rıza metni güncellenmeli: {sorted(eylemler ^ bilinen)}"
    # her riza satırının dayandığı eylem hâlâ var
    for eylem in ("screenshot", "readfile", "writefile", "deletefile", "killproc", "proclist", "clipboard_get", "clipboard_set"):
        assert eylem in eylemler
    # ev klasörü sınırı kodda duruyor (metin "ev klasöründeki" diyor)
    assert agent.count("relative_to(home)") >= 3
    # sunucunun izin listesi ajanın eylemleriyle aynı; komut çalıştırma ikisinde de yok
    from app.api.devices_api import IZINLI_EYLEMLER
    assert set(IZINLI_EYLEMLER) == eylemler
    assert "exec" not in eylemler


# ── ⑦ uygulama kilidi ────────────────────────────────────────────────────────

def test_kilit_yoksa_anahtar_PASIF_sebep_yazar_Guvenlige_goturur_ve_PUT_gitmez():
    s = kos({"yanit": yanit(ag=AG_KILITSIZ), "adimlar": [{"op": "ac"}, {"op": "tikla", "g": "ag-ac", "aria": "false"},
                                                          {"op": "tikla", "g": "guvenlik"}]})
    h = s["adimlar"][0]["html"]
    assert "cihaz.ag-kilitsiz-ne" in h, "kilit yok ama 'önce kilidi kur' söylenmedi"
    assert "disabled" in re.search(r'<button[^>]*data-cz="ag-ac"[^>]*>', h).group(0), "kilitsizken ağ anahtarı etkin"
    assert 'data-ag-hal="kilitsiz"' in h
    assert "GOTO cat guvenlik" in s["cagri"]


def test_kilit_varken_anahtar_etkin_ve_acarken_tek_cumle_soylenir():
    s = kos({"yanit": yanit(ag=AG_KAPALI), "adimlar": [{"op": "ac"}]})
    h = _son(s)
    assert "disabled" not in re.search(r'<button[^>]*data-cz="ag-ac"[^>]*>', h).group(0)
    assert "cihaz.ag-kapali-ne" in h and 'aria-checked="false"' in h
    k = sozluk("tr")["cihaz.ag-risk-kapali"]
    assert "cz-risk" in h, "risk cümlesi kendi satırında değil"
    assert "aynı Wi-Fi" in k and "kilid" in k, "açmadan önce risk + kilidin ne yaptığı söylenmiyor"


def test_kilit_dustu_ve_kilit_kalkti_cumleleri():
    s = kos({"yanit": yanit(ag={**AG_KILITSIZ, "kilit_dustu": True}), "adimlar": [{"op": "ac"}]})
    assert "cihaz.ag-kilit-dustu" in _son(s), "kilit düşüp ağ kapatıldı ama panel söylemiyor"
    s = kos({"yanit": yanit(ag={**AG_ACIK, "kilit_kurulu": False}), "adimlar": [{"op": "ac"}]})
    assert "cihaz.ag-kilit-kalkti" in _son(s), "çalışırken kilit kalktı ama panel söylemiyor"
    assert _isik(_son(s)) == "uyari", "kilit kalktı, sunucu ağdan gelen her isteği reddediyor — yeşil yandı"


# ── ⑩ AĞ ANAHTARI (yeşil yalnız gerçekten dinleniyorsa) ──────────────────────

def _isik(h):
    m = re.search(r'class="cz-serit[^"]*"[^>]*>\s*<span class="durum-isik (\w+)"', h)
    return m.group(1) if m else None


def test_yesil_YALNIZ_dinleniyorsa_diger_hallerde_yesil_YOK():
    """Ayar açık ama süreç hâlâ 127.0.0.1'de → 'yeniden başlatma bekliyor', YEŞİL DEĞİL. HOST açık ama soket cevap
    vermiyorsa da yeşil değil. (Panel `ag_ayari`na değil sunucunun soketten ölçtüğü `dinleniyor`a bakar.)"""
    ak = kos({"yanit": yanit(ag=AG_ACIK), "adimlar": [{"op": "ac"}]})
    assert _isik(_son(ak)) == "iyi" and "cihaz.ag-acik-baslik" in _son(ak)
    for ag, anahtar in ((AG_BEKLIYOR, "cihaz.ag-bekliyor-baslik"), (AG_ULASILAMIYOR, "cihaz.ag-ulasilamiyor-baslik"),
                        (AG_KAPANIS, "cihaz.ag-kapanis-baslik"), (AG_KAPALI, "cihaz.ag-kapali-baslik")):
        h = _son(kos({"yanit": yanit(ag=ag), "adimlar": [{"op": "ac"}]}))
        assert _isik(h) == "uyari", f"{ag['ag_durum']}: yeşil yandı (yalan yeşil)"
        assert anahtar in h, ag["ag_durum"]


def test_ayar_acik_ama_dinlenmiyorsa_ekle_PASIF_ve_sebep_yeniden_baslatma():
    s = kos({"yanit": yanit(ag=AG_BEKLIYOR), "adimlar": [{"op": "ac"}, {"op": "tikla", "g": "ekle"}]})
    h = s["adimlar"][0]["html"]
    assert "disabled" in re.search(r'<button[^>]*data-cz="ekle"[^>]*>', h).group(0), "dinlenmeyen ağda 'Cihaz ekle' aktif"
    assert not any(c.startswith("POST") for c in s["cagri"])
    assert "cihaz.ag-bekliyor-ne" in h and '192.168.1.104:8001' in h, "adres + yeniden başlatınca geçerli bilgisi yok"
    assert "cihaz.ekle-ag-bekliyor" in h


def test_acma_PUT_atar_ve_cevaptaki_durumu_cizer_yeniden_baslatma_bekliyor():
    bekliyor_cevap = [200, {"ok": True, "ag": AG_BEKLIYOR}]
    s = kos({"yanit": yanit(ag=AG_KAPALI, **{PUT_AG: bekliyor_cevap}),
             "adimlar": [{"op": "ac"}, {"op": "tikla", "g": "ag-ac", "aria": "false"}]})
    assert PUT_AG in s["cagri"]
    assert s["govde"] == ['PUT /api/devices/ag {"acik":true}']
    h = _son(s)
    assert "cihaz.ag-bekliyor-baslik" in h and 'aria-checked="true"' in h and _isik(h) == "uyari"


def test_kapatma_PUT_acik_false_kilitsiz_da_gider():
    """Kapatmak her zaman serbest: anahtar açıkken (kilit olmasa bile) etkin, istek `acik:false` gider."""
    acik_kilitsiz = {**AG_ACIK, "kilit_kurulu": False}
    s = kos({"yanit": yanit(ag=acik_kilitsiz, **{PUT_AG: [200, {"ok": True, "ag": AG_KAPANIS}]}),
             "adimlar": [{"op": "ac"}, {"op": "tikla", "g": "ag-ac", "aria": "true"}]})
    assert "disabled" not in re.search(r'<button[^>]*data-cz="ag-ac"[^>]*>', s["adimlar"][0]["html"]).group(0)
    assert s["govde"] == ['PUT /api/devices/ag {"acik":false}']
    assert "cihaz.ag-kapanis-baslik" in _son(s)


def test_sunucu_409_derse_sebep_soylenir_anahtar_acilmis_gorunmez():
    """Panel kilitsiz olduğunu bilmiyordu (bayat) → sunucu 409 verir; panel 'açıldı' DEMEZ, kilit cümlesini yazar."""
    s = kos({"yanit": yanit(ag=AG_KAPALI, **{PUT_AG: [409, {"detail": "x"}]}),
             "adimlar": [{"op": "ac"}, {"op": "yanit", "url": AG, "deger": [200, AG_KILITSIZ]}, {"op": "tikla", "g": "ag-ac", "aria": "false"}]})
    h = _son(s)
    assert "cihaz.ag-kilit-yok-kisa" in h
    assert 'aria-checked="false"' in h and 'data-ag-hal="kilitsiz"' in h


def test_anahtar_cift_tik_TEK_PUT():
    s = kos({"yanit": yanit(ag=AG_KAPALI, **{PUT_AG: [200, {"ok": True, "ag": AG_BEKLIYOR}]}),
             "adimlar": [{"op": "ac"}, {"op": "tikla", "g": "ag-ac", "aria": "false", "kez": 3, "ms": 200}]})
    assert sum(1 for c in s["cagri"] if c == PUT_AG) == 1, "çift tık birden çok PUT attı"


def test_yazilamazsa_anahtar_eski_yerinde_ve_hata_cumlesi():
    s = kos({"yanit": yanit(ag=AG_KAPALI, **{PUT_AG: [500, {}]}), "adimlar": [{"op": "ac"}, {"op": "tikla", "g": "ag-ac", "aria": "false"}]})
    h = _son(s)
    assert 'aria-checked="false"' in h and "cihaz.ag-yazilamadi" in h


def test_yeniden_baslat_masaustunde_MEVCUT_akisi_kullanir_tarayicida_dugme_yok():
    s = kos({"masaustu": True, "yanit": yanit(ag=AG_BEKLIYOR), "adimlar": [{"op": "ac"}, {"op": "tikla", "g": "ag-yeniden"}]})
    assert 'data-cz="ag-yeniden"' in s["adimlar"][0]["html"]
    assert "YENIDEN-BASLAT" in s["cagri"], "mevcut yenidenBaslatCalistir akışı çağrılmadı"
    s = kos({"yanit": yanit(ag=AG_BEKLIYOR), "adimlar": [{"op": "ac"}]})
    assert 'data-cz="ag-yeniden"' not in _son(s) and "cihaz.ag-yb-elle" in _son(s), "tarayıcıda çalışmayan düğme gösterildi"


def test_yeniden_baslatma_yeni_akis_YAZILMADI():
    """Yeni bir yeniden başlatma yolu açılmadı: panel yalnız `yenidenBaslatCalistir`'i çağırır."""
    kod = yorumsuz(PANEL)
    assert "yenidenBaslatCalistir" in kod
    assert "yukiSistem.yenidenBaslat()" not in kod and "relaunch" not in kod.lower()


# ── ④ çift tık ───────────────────────────────────────────────────────────────

def test_uc_hizli_tik_TEK_kod_ister_ve_bitince_dugme_acilir():
    s = kos({"yanit": yanit(), "adimlar": [{"op": "ac"}, {"op": "tikla", "g": "ekle"}, {"op": "tikla", "g": "kod-uret", "kez": 3, "ms": 200}]})
    assert s["cagri"].count(POST_KOD) == 1, s["cagri"]


def test_ikinci_kod_ilkini_yakmadan_once_yeni_istek_yalniz_dugmeyle():
    s = kos({"yanit": yanit(), "adimlar": [{"op": "ac"}, {"op": "tikla", "g": "ekle"}, {"op": "tikla", "g": "kod-uret"},
                                           {"op": "tikla", "g": "ekle"}]})
    assert s["cagri"].count(POST_KOD) == 1, "kod açıkken 'Cihaz ekle' ikinci kod üretti"


# ── ③ eşleşme ────────────────────────────────────────────────────────────────

def test_eslesme_yoklanir_cekmece_eslesti_der_yeni_kart_isaretlenir():
    s = kos({"yanit": yanit(), "adimlar": [
        {"op": "ac"}, {"op": "tikla", "g": "ekle"}, {"op": "tikla", "g": "kod-uret"},
        {"op": "yanit", "url": LISTE, "deger": [200, [C3, C1, C2]]},
        {"op": "tik", "n": 3, "sn": 1}]})
    h = _son(s)
    assert "cihaz.eslesti-baslik" in h and "yeni-pc" in h, "yeni cihaz düştü ama çekmece 'eşleşti' demedi"
    assert re.search(r'cz-kart yeni', h), "yeni kart işaretlenmedi"
    assert "K7MQ" not in h, "kullanılmış kod ekranda duruyor"
    assert not s["adimlar"][-1]["cagri"][-1].startswith("POST")


def test_kod_acikken_yoklama_3_sn_de_bir_ve_yeni_cihaz_yoksa_eslesti_DEMEZ():
    s = kos({"yanit": yanit(), "adimlar": [{"op": "ac"}, {"op": "tikla", "g": "ekle"}, {"op": "tikla", "g": "kod-uret"}]})
    once = s["cagri"].count(LISTE)
    s2 = kos({"yanit": yanit(), "adimlar": [{"op": "ac"}, {"op": "tikla", "g": "ekle"}, {"op": "tikla", "g": "kod-uret"},
                                            {"op": "tik", "n": 6, "sn": 1}]})
    assert s2["cagri"].count(LISTE) - once == 2, "6 saniyede 2 yoklama beklenirdi (3 sn aralık)"
    assert "cihaz.eslesti-baslik" not in _son(s2)


def test_kod_yokken_yoklama_YOK():
    s = kos({"yanit": yanit(), "adimlar": [{"op": "ac"}, {"op": "tik", "n": 9, "sn": 1}]})
    assert s["cagri"].count(LISTE) == 1, "kod açık değilken liste yoklanıyor"


def test_panel_gorunmezse_acik_kod_yanar_ve_yoklama_durur():
    s = kos({"yanit": yanit(), "adimlar": [{"op": "ac"}, {"op": "tikla", "g": "ekle"}, {"op": "tikla", "g": "kod-uret"},
                                           {"op": "gizle"}, {"op": "tik", "n": 1, "sn": 1}]})
    assert DEL_KOD in s["cagri"], "panel kapandı, kod 5 dk açık kaldı"


# ── ⑤ süre dolunca ───────────────────────────────────────────────────────────

def test_sure_dolunca_DOLDU_der_yeni_kod_dugmesi_verir():
    s = kos({"yanit": yanit(), "adimlar": [{"op": "ac"}, {"op": "tikla", "g": "ekle"}, {"op": "tikla", "g": "kod-uret"},
                                           {"op": "tik", "n": 1, "sn": 301}]})
    h = _son(s)
    assert "cihaz.doldu-baslik" in h and 'data-cz="kod-uret"' in h
    assert "K7MQ" not in h, "süresi dolmuş kod ekranda duruyor"
    s = kos({"yanit": yanit(), "adimlar": [{"op": "ac"}, {"op": "tikla", "g": "ekle"}, {"op": "tikla", "g": "kod-uret"},
                                           {"op": "tik", "n": 1, "sn": 301}, {"op": "tikla", "g": "kod-uret"}]})
    assert s["cagri"].count(POST_KOD) == 2 and "K7MQ" in _son(s)


def test_riza_ikinci_kodda_tekrar_sorulmaz_ama_panel_yeniden_acilinca_sorulur():
    s = kos({"yanit": yanit(), "adimlar": [{"op": "ac"}, {"op": "tikla", "g": "ekle"}, {"op": "tikla", "g": "kod-uret"},
                                           {"op": "tikla", "g": "kapat"}, {"op": "tikla", "g": "ekle"}]})
    assert "K7MQ" in _son(s) and s["cagri"].count(POST_KOD) == 2, "aynı açılışta ikinci kod için rıza yeniden istendi"
    s = kos({"yanit": yanit(), "adimlar": [{"op": "ac"}, {"op": "tikla", "g": "ekle"}, {"op": "tikla", "g": "kod-uret"},
                                           {"op": "ac"}, {"op": "tikla", "g": "ekle"}]})
    assert "cihaz.onay-baslik" in _son(s), "panel yeniden açıldı ama rıza listesi atlandı"


# ── kod hataları ─────────────────────────────────────────────────────────────

def test_kod_429_cümlesi_ayri_ve_tekrar_dene_verir():
    s = kos({"yanit": yanit(**{POST_KOD: [429, {}]}), "adimlar": [{"op": "ac"}, {"op": "tikla", "g": "ekle"}, {"op": "tikla", "g": "kod-uret"}]})
    h = _son(s)
    assert "cihaz.hata-cok-sik" in h and 'data-cz="kod-uret"' in h and "K7MQ" not in h


# ── ⑧ kaldır ─────────────────────────────────────────────────────────────────

def test_kaldir_IKI_adimli_ilk_tikta_DELETE_gitmez():
    s = kos({"yanit": yanit(**{"DELETE /api/devices/eslestirilmis/b2": [200, {"ok": True}]}),
             "adimlar": [{"op": "ac"}, {"op": "tikla", "g": "kaldir", "id": "b2"}]})
    h = _son(s)
    assert "cihaz.kaldir-sor" in h and 'data-cz="kaldir-evet"' in h
    assert not any(c.startswith("DELETE") for c in s["cagri"]), "ilk tıkta silindi"
    s = kos({"yanit": yanit(**{"DELETE /api/devices/eslestirilmis/b2": [200, {"ok": True}]}),
             "adimlar": [{"op": "ac"}, {"op": "tikla", "g": "kaldir", "id": "b2"}, {"op": "tikla", "g": "vazgec"}]})
    assert "cihaz.kaldir-sor" not in _son(s) and not any(c.startswith("DELETE") for c in s["cagri"])
    s = kos({"yanit": yanit(**{"DELETE /api/devices/eslestirilmis/b2": [200, {"ok": True}]}),
             "adimlar": [{"op": "ac"}, {"op": "tikla", "g": "kaldir", "id": "b2"}, {"op": "tikla", "g": "kaldir-evet", "id": "b2", "kez": 3}]})
    assert s["cagri"].count("DELETE /api/devices/eslestirilmis/b2") == 1, "çift tık birden çok DELETE yolladı"


def test_kaldir_basarisizsa_satir_icinde_hata_soyler():
    s = kos({"yanit": yanit(**{"DELETE /api/devices/eslestirilmis/b2": [500, {}]}),
             "adimlar": [{"op": "ac"}, {"op": "tikla", "g": "kaldir", "id": "b2"}, {"op": "tikla", "g": "kaldir-evet", "id": "b2"}]})
    assert "cihaz.kaldirilamadi" in _son(s) and "cihaz.kaldir-sor" in _son(s), "hata yutuldu / onay kapandı"


def test_confirm_prompt_alert_YOK():
    kod = yorumsuz(PANEL)
    for yasak in ("confirm(", "prompt(", "alert("):
        assert yasak not in kod


# Backend: kayıt silinince açık bağlantı kesilir ---------------------------------

@pytest.fixture()
def ultra_depo(tmp_path, monkeypatch):
    from app.services import cihaz_eslestirme as ce
    monkeypatch.setenv("YUKI_DATA_DIR", str(tmp_path))
    ce.kod_iptal()
    yield ce
    ce.kod_iptal()


def test_KALDIR_acik_baglantiyi_da_keser(ultra_depo):
    """Token yalnız bağlanırken denetlenir: kayıt silinip soket açık kalırsa cihaz komut almaya devam ederdi."""
    from starlette.websockets import WebSocketDisconnect
    from app.main import app
    from app.services import device_manager as dm
    c = TestClient(app)
    kod = ultra_depo.kod_uret()["kod"]
    with c.websocket_connect(f"/ws/agent?eslestirme={kod}") as ws:
        cihaz_id = json.loads(ws.receive_text())["cihaz_id"]
        ws.send_text(json.dumps({"type": "register", "hostname": "kurban"}))
        for _ in range(50):
            if dm.get(cihaz_id):
                break
            time.sleep(0.05)
        assert dm.get(cihaz_id), "cihaz bağlanamadı (test kurulumu)"
        r = c.delete(f"/api/devices/eslestirilmis/{cihaz_id}")
        assert r.status_code == 200
        assert dm.get(cihaz_id) is None, "kaldırılan cihaz hâlâ bağlı listesinde"
        # `receive_text` bağlantı KESİLMEZSE sonsuza dek bekler → ayrı iş parçacığında, tavanla
        sonuc: dict = {}

        def _bekle():
            try:
                ws.receive_text()
                sonuc["hata"] = None
            except WebSocketDisconnect as e:
                sonuc["hata"] = e

        import threading
        t = threading.Thread(target=_bekle, daemon=True)
        t.start()
        t.join(5)
        assert not t.is_alive(), "kayıt silindi ama cihazın soketi AÇIK kaldı (komut almaya devam eder)"
        assert sonuc["hata"] is not None and sonuc["hata"].code == 4401
    r = c.post(f"/api/devices/{cihaz_id}/command", json={"action": "ping"})
    assert r.status_code == 404, "kaldırılan cihaza hâlâ komut gidebiliyor"


# ── ⑨ QR saklı, vaat doğru ───────────────────────────────────────────────────

def test_QR_saklı_ama_uretec_silinmedi():
    s = kos({"yanit": yanit(), "adimlar": [{"op": "ac"}, {"op": "tikla", "g": "ekle"}, {"op": "tikla", "g": "kod-uret"}]})
    h = _son(s)
    assert "cz-qr" not in h and "<svg" not in h, "QR'ı okuyan istemci yok ama QR çiziliyor"
    kod = yorumsuz(PANEL)
    assert re.search(r"var QR_GOSTER = false;", kod), "QR bayrağı yok / açık"
    assert "QRUret.svg" in kod, "QR üreteci kodu silinmiş (ileride telefon istemcisi gelirse açılacaktı)"
    assert (FRONTEND / "vendor" / "qr-uret.js").exists()


def test_kod_metin_olarak_ve_komut_kopyalanabilir():
    s = kos({"yanit": yanit(), "adimlar": [{"op": "ac"}, {"op": "tikla", "g": "ekle"}, {"op": "tikla", "g": "kod-uret"},
                                           {"op": "tikla", "g": "kopya-kod"}, {"op": "tikla", "g": "kopya-komut"},
                                           {"op": "tikla", "g": "kopya-komut-win"}]})
    h = s["adimlar"][2]["html"]
    assert "K7MQ" in h and "4X2P" in h, "kod metin olarak gösterilmiyor"
    assert s["pano"][0] == "K7MQ4X2P"
    assert s["pano"][1] == "YUKI_SERVER=ws://192.168.1.104:8001/ws/agent python agent.py --eslestir K7MQ4X2P"
    assert s["pano"][2].startswith('$env:YUKI_SERVER="ws://192.168.1.104:8001/ws/agent"') and s["pano"][2].endswith("--eslestir K7MQ4X2P")


def test_telefon_vaadi_sozlukte_YOK():
    for dil in ("tr", "en"):
        # `cihaz.qr-cizilemedi` yalnız QR_GOSTER=true yolunda kullanılır (şimdilik saklı) — vaat değil
        metin = " ".join(v for k, v in sozluk(dil).items() if k.startswith("cihaz.") and k != "cihaz.qr-cizilemedi").lower()
        assert "telefon" not in metin and "phone" not in metin and "qr" not in metin, \
            f"{dil}: cihaz sözlüğünde telefon/QR vaadi duruyor — istemci yok"


def test_kapat_acik_kodu_sunucuda_da_yakar():
    s = kos({"yanit": yanit(), "adimlar": [{"op": "ac"}, {"op": "tikla", "g": "ekle"}, {"op": "tikla", "g": "kod-uret"}, {"op": "tikla", "g": "kapat"}]})
    assert DEL_KOD in s["cagri"] and "K7MQ" not in _son(s)


# ── çeviri tutarlılığı ───────────────────────────────────────────────────────

def test_kullanilan_her_cihaz_anahtari_tr_ve_en_de_var_ve_yer_tutucular_esit():
    kod = yorumsuz(PANEL)
    anahtarlar = {a for a in re.findall(r"'(cihaz\.[a-z0-9-]+)'", kod) if not a.endswith("-")} | {f"cihaz.yetki-{k}" for k in ("ekran", "dosya", "program", "pano")}
    tr, en = sozluk("tr"), sozluk("en")
    for a in sorted(anahtarlar):
        assert a in tr, f"tr'de yok: {a}"
        assert a in en, f"en'de yok: {a}"
        assert re.findall(r"\{[a-z]+\}", tr[a]) == re.findall(r"\{[a-z]+\}", en[a]), f"yer tutucu uyuşmuyor: {a}"
    # ölü anahtar kalmasın
    ek = {k for k in tr if k.startswith("cihaz.")} - anahtarlar
    assert not ek, f"panelin kullanmadığı cihaz.* anahtarları duruyor: {sorted(ek)}"


def test_ham_HOST_ya_da_ajan_dili_musteri_cumlelerinde_yok():
    for dil in ("tr", "en"):
        for k, v in sozluk(dil).items():
            if k.startswith("cihaz.") and k not in ("cihaz.ag-kapali-ne",):
                assert "HOST=" not in v, f"{dil} {k}: geliştirici dili"


# ══ GÖZ TUR 1 (2026-10-01) ═══════════════════════════════════════════════════

# #1 — kod tek biçim, sunucu + ajan normalleştirir ----------------------------

@pytest.mark.parametrize("yazim", ["K7MQ4X2P", "k7mq4x2p", "K7MQ 4X2P", "k7mq-4x2p", " K7MQ  4x2p\n", "K7MQ.4X2P"])
def test_sunucu_kodu_normallestirir(ultra_depo, yazim):
    ce = ultra_depo
    ce._kodlar.clear()
    ce._kodlar["K7MQ4X2P"] = {"son": time.time() + 300, "deneme": 0}
    assert ce.kod_dogrula(yazim, "pc"), f"{yazim!r} reddedildi"
    assert ce.kod_dogrula("K7MQ4X2P") is None, "kod tek kullanımlık kalmalı"


def test_normallestirme_deneme_sayacini_YANLIS_yakmaz(ultra_depo):
    ce = ultra_depo
    ce._kodlar.clear()
    ce._kodlar["K7MQ4X2P"] = {"son": time.time() + 300, "deneme": 0}
    for bos in ("", "   ", "-- --", "\n"):
        assert ce.kod_dogrula(bos) is None
    assert ce._kodlar["K7MQ4X2P"]["deneme"] == 0, "boş/ayraç girişi deneme hakkı yaktı"
    for _ in range(ce.MAX_DENEME - 1):
        assert ce.kod_dogrula("ZZZZ ZZZZ") is None
    assert ce._kodlar["K7MQ4X2P"]["deneme"] == ce.MAX_DENEME - 1
    assert ce.kod_dogrula("k7mq 4x2p"), "doğru kod (boşluklu/küçük) son haktan önce kabul edilmeli"


def test_gercekten_yanlis_kod_hala_yakar(ultra_depo):
    ce = ultra_depo
    ce._kodlar.clear()
    ce._kodlar["K7MQ4X2P"] = {"son": time.time() + 300, "deneme": 0}
    for _ in range(ce.MAX_DENEME):
        ce.kod_dogrula("AAAA BBBB")
    assert ce.kod_dogrula("K7MQ4X2P") is None, "5 yanlıştan sonra kod yaşıyor"


@pytest.mark.parametrize("argv,beklenen", [
    (["agent.py", "--eslestir", "K7MQ", "4X2P"], "K7MQ4X2P"),
    (["agent.py", "--eslestir", "k7mq-4x2p"], "K7MQ4X2P"),
    (["agent.py", "--eslestir", "K7MQ", "4x2p", "--baska"], "K7MQ4X2P"),
    (["agent.py", "--eslestir", "K7MQ4X2P"], "K7MQ4X2P"),
])
def test_ajan_bosluklu_kodu_birlestirir(monkeypatch, argv, beklenen):
    import importlib.util, sys
    monkeypatch.setattr(sys, "argv", argv)
    monkeypatch.delenv("YUKI_ESLESTIRME", raising=False)
    spec = importlib.util.spec_from_file_location("agent_test", KOK / "remote_agent" / "agent.py")
    try:
        m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    except ImportError as e:
        pytest.skip(f"ajan bağımlılığı yok: {e}")
    url, ilk = m._baglanti_urlsi()
    assert ilk and f"eslestirme={beklenen}&" in url, url


def test_ekranda_kod_TEK_biçim_komutla_ayni():
    s = kos({"yanit": yanit(), "adimlar": [{"op": "ac"}, {"op": "tikla", "g": "ekle"}, {"op": "tikla", "g": "kod-uret"}]})
    h = _son(s)
    assert re.search(r'class="cz-kod"[^>]*>K7MQ4X2P</div>', h), "çekmecedeki kod boşluklu/bölünmüş"
    assert "--eslestir K7MQ4X2P" in h


# #2 / #3 — ekle kartı çelişmez --------------------------------------------------

def test_onay_adiminda_ekle_karti_KOD_ACIK_demez():
    s = kos({"yanit": yanit(), "adimlar": [{"op": "ac"}, {"op": "tikla", "g": "ekle"}]})
    kart = re.search(r'data-cz="ekle".*?</button>', _son(s), re.S).group(0)
    assert "cihaz.ekle-kod-acik" not in kart and "cihaz.ekle-onayda" in kart


def test_ag_bilinmiyorken_TEK_teşhis():
    s = kos({"yanit": yanit(**{AG: [500, {}]}), "adimlar": [{"op": "ac"}]})
    h = _son(s)
    assert "cihaz.ekle-ag-yok" not in h, "ağın kapalı olduğu iddia edildi (yalnız bilinmiyor)"
    assert "cihaz.ekle-ag-bilinmiyor" in h and "cihaz.ag-bilinmiyor" in h


# #4 — 429 geri sayım ---------------------------------------------------------------

def test_429da_tekrar_dene_sure_bitene_kadar_PASIF_ve_geri_sayar():
    s = kos({"yanit": yanit(**{LISTE: [429, {}]}), "adimlar": [{"op": "ac"}, {"op": "tik", "n": 1, "sn": 10}, {"op": "tik", "n": 1, "sn": 51}]})
    ilk, orta, son = s["adimlar"]
    dugme = lambda h: re.search(r'<button[^>]*data-cz="tekrar"[^>]*>.*?</button>', h, re.S).group(0)
    assert "disabled" in dugme(ilk["html"]) and "cihaz.tekrar-bekle" in dugme(ilk["html"])
    assert any(f"&quot;n&quot;:{n}" in dugme(orta["html"]) for n in (50, 51)), dugme(orta["html"])
    assert "disabled" not in dugme(son["html"]), "süre bitti ama düğme pasif kaldı"


def test_kod_429da_cekmece_dugmesi_bekletir():
    s = kos({"yanit": yanit(**{POST_KOD: [429, {}]}), "adimlar": [{"op": "ac"}, {"op": "tikla", "g": "ekle"}, {"op": "tikla", "g": "kod-uret"},
                                                                  {"op": "tik", "n": 1, "sn": 61}]})
    a = s["adimlar"][2]["html"]; z = s["adimlar"][3]["html"]
    assert "disabled" in re.search(r'<button[^>]*data-cz="kod-uret"[^>]*>', a).group(0)
    assert "disabled" not in re.search(r'<button[^>]*data-cz="kod-uret"[^>]*>', z).group(0)


# #5 — yetki vurgusu -----------------------------------------------------------------

def test_yetki_listesinde_dosya_vurgulu_komut_yok():
    s = kos({"yanit": yanit(), "adimlar": [{"op": "ac"}, {"op": "tikla", "g": "ekle"}]})
    h = _son(s)
    assert re.search(r'<li class="agir">cihaz\.yetki-dosya', h) and "cihaz.yetki-komut" not in h
    assert not re.search(r'<li class="agir">cihaz\.yetki-(ekran|pano|program)', h)
    css = (FRONTEND / "css" / "hq-cihazlar.css").read_text(encoding="utf-8")
    assert "li.agir" in css


# #6 — süre saat gibi okunmasın --------------------------------------------------------

def test_sure_dakika_cumlesi_ve_ayri_sayac():
    s = kos({"yanit": yanit(), "adimlar": [{"op": "ac"}, {"op": "tikla", "g": "ekle"}, {"op": "tikla", "g": "kod-uret"}]})
    h = _son(s)
    assert 'cihaz.kod-sure{&quot;dk&quot;:5}' in h and "cihaz.kod-kalan" in h and 'data-cz-sure' in h
    tr = sozluk("tr")["cihaz.kod-sure"]
    assert "{dk} dakika" in tr and "{sure}" not in tr


# #7 — komut kelime ortasında kırılmaz -------------------------------------------------

def test_komut_kutusu_kirilmaz_yatay_kayar():
    css = (FRONTEND / "css" / "hq-cihazlar.css").read_text(encoding="utf-8")
    kural = re.search(r"\.cz-komut \{ margin[^}]*\}", css).group(0)
    assert "white-space: pre;" in kural and "overflow-x: auto" in kural and "anywhere" not in kural


# #8 — hata ekranında liste kaybolmaz ---------------------------------------------------

@pytest.mark.parametrize("liste", [[500, {}], [429, {}], "ag-hatasi", [401, {}]])
def test_hata_ekraninda_son_bilinen_liste_guncel_degil_etiketiyle_kalir(liste):
    s = kos({"yanit": yanit(), "adimlar": [{"op": "ac"}, {"op": "yanit", "url": LISTE, "deger": liste}, {"op": "tikla", "g": "tekrar"}]})
    h = _son(s)
    assert "cihaz.eski-liste" in h and "ofis-pc" in h and "mutfak-laptop" in h, "hata ekranında cihazlar kayboldu"
    assert 'data-cz="kaldir"' not in h, "bayat listeden Kaldır verilmemeli"


def test_ilk_acilista_hata_varsa_liste_uydurulmaz():
    s = kos({"yanit": yanit(**{LISTE: [500, {}]}), "adimlar": [{"op": "ac"}]})
    assert "cihaz.eski-liste" not in _son(s)


def test_hata_notlari_cihazlar_silinmedi_der():
    tr = sozluk("tr")
    for k in ("cihaz.cok-sik-not", "cihaz.ulasilamadi-not", "cihaz.hata-not", "cihaz.kilitli-not"):
        assert "silinmedi" in tr[k], k


# ── göz turu 2 ───────────────────────────────────────────────────────────────

def test_acik_anahtara_onceAgaAc_DENMEZ_metin_duruma_gore():
    """Anahtar açıkken 'önce ağa aç' yazmak kullanıcıyı açık anahtara yeniden basmaya yönlendiriyordu."""
    for ag, kart, bos in ((AG_BEKLIYOR, "cihaz.ekle-ag-bekliyor", "cihaz.bos-not-ag-bekliyor"),
                          (AG_ULASILAMIYOR, "cihaz.ekle-ag-ulasilamiyor", "cihaz.bos-not-ag-ulasilamiyor"),
                          (AG_KAPALI, "cihaz.ekle-ag-yok", "cihaz.bos-not-ag-yok")):
        h = _son(kos({"yanit": yanit(ag=ag), "adimlar": [{"op": "ac"}]}))
        assert kart in h, (ag["ag_durum"], kart)
        h2 = _son(kos({"yanit": yanit(ag=ag, liste=()), "adimlar": [{"op": "ac"}]}))
        assert bos in h2, (ag["ag_durum"], bos)
    h = _son(kos({"yanit": yanit(ag=AG_ACIK, liste=()), "adimlar": [{"op": "ac"}]}))
    assert "cihaz.bos-not" in h and "ag-yok" not in h


def test_yeniden_baslat_ikinci_basis_gorunur_sekilde_degisir():
    s = kos({"masaustu": True, "yanit": yanit(ag=AG_BEKLIYOR), "adimlar": [{"op": "ac"}, {"op": "tikla", "g": "ag-yeniden"}]})
    assert "TEXT cihaz.ag-yb-emin" in s["cagri"], "ilk basıştan sonra düğme 'Emin misin?' demedi"
    assert "CLASS cz-yb-onay" in s["cagri"]


def test_kilitsiz_pasif_anahtar_ayirt_edilir_ve_kilit_gerekli_der():
    h = _son(kos({"yanit": yanit(ag=AG_KILITSIZ), "adimlar": [{"op": "ac"}]}))
    assert "cz-sw-kilitli" in h and "cihaz.ag-durum-kilitli" in h
    h = _son(kos({"yanit": yanit(ag=AG_KAPALI), "adimlar": [{"op": "ac"}]}))
    assert "cz-sw-kilitli" not in h and "cihaz.ag-durum-kapali" in h


def test_tarayicida_eylem_cumlesi_ayri_sinifta():
    h = _son(kos({"yanit": yanit(ag=AG_BEKLIYOR), "adimlar": [{"op": "ac"}]}))
    assert 'class="cz-yb-elle"' in h


def test_risk_cumlesi_kendi_satirinda_her_acik_halde():
    for ag in (AG_KAPALI, AG_BEKLIYOR, AG_ACIK):
        assert 'class="cz-risk"' in _son(kos({"yanit": yanit(ag=ag), "adimlar": [{"op": "ac"}]})), ag["ag_durum"]
