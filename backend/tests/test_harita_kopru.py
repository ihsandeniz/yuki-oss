"""Yuki ↔ harita köprüsü — komut gider, sonuç geri gelir.

Bu dosyanın asıl derdi **sessiz başarı iddiası**. Bir harita komutu üç ayrı
yerde hiçbir şey yapmadan "oldu" görünebilir:
  ① backend cevap beklemez → Yuki "gösterdim" der, harita kapalıdır
  ② katman anahtarı uydurmadır → `toggleLayer('yanardag')` hiçbir şey yapmaz
  ③ frontend köprüsü olmayan bir global'e yaslanır → çağrı sessizce düşer

②/③ **statik olarak** ölçülür: canlı tarayıcı olmadan, kaynak dosyalara karşı.
Böyle bir kapı olmasaydı arıza ancak kullanıcı bir gün "deprem katmanını aç"
dediğinde ve hiçbir şey olmadığında görülürdü.
"""
from __future__ import annotations

import asyncio
import re
from pathlib import Path

import pytest

from app.services import harita_kopru
from app.services.tools import harita

KOK = Path(__file__).resolve().parents[2]
MAP_ENGINE = (KOK / "frontend" / "js" / "map-engine.js").read_text(encoding="utf-8")
MAP_KOPRU = (KOK / "frontend" / "js" / "map-kopru.js").read_text(encoding="utf-8")
INDEX = (KOK / "frontend" / "index.html").read_text(encoding="utf-8")


@pytest.fixture(autouse=True)
def temiz():
    harita_kopru._sifirla()
    yield
    harita_kopru._sifirla()


# ── ② katman anahtarları GERÇEK mi ──────────────────────────────────────────
def test_katman_anahtarlari_map_enginede_GERCEKTEN_var():
    """🔴 Uydurma anahtar hata vermez, sessizce hiçbir şey yapmaz.

    `toggleLayer(key)` bilinmeyen anahtarla çağrılınca `_layerActive[key]`
    oluşturulur, `_fetchLayer(key)` veri bulamaz ve kullanıcı "açtım" cevabı
    alır. Kapı: her anahtarın `index.html`'de bir düğmesi (`map-layer-<key>`)
    olmalı — düğme, o katmanın gerçekten var olduğunun kanıtıdır.
    """
    eksik = [k for k in set(harita.KATMANLAR.values())
             if f'id="map-layer-{k}"' not in INDEX]
    assert not eksik, f"index.html'de karşılığı olmayan katman anahtarı: {eksik}"


def test_katman_takma_adlari_hepsi_gecerli_anahtara_cikiyor():
    gecerli = set(harita.KATMANLAR.values())
    assert all(v in gecerli for v in harita.KATMANLAR.values())
    # Türkçe ünsüz yumuşaması tuzağı:
    # "yanardağ" ve "yanardag" ikisi de tanınmalı.
    assert harita._katman_coz("yanardağ") == harita._katman_coz("yanardag") == "volcano"
    assert harita._katman_coz("YANGIN") == "fire", "büyük harf tanınmalı"


def test_bilinmeyen_katman_reddedilir():
    assert harita._katman_coz("kahve") is None


# ── ③ köprünün yaslandığı global'ler VAR mı ────────────────────────────────
@pytest.mark.parametrize("sembol,desen", [
    ("_lmap", r"\b_lmap\b"),
    ("toggleLayer", r"function\s+toggleLayer\s*\("),
    ("_layerActive", r"\b_layerActive\b"),
])
def test_kopru_map_enginein_GERCEK_globallerini_kullaniyor(sembol, desen):
    """Köprü `map-engine.js`'in global'lerine yaslanır; biri yeniden
    adlandırılırsa köprü sessizce ölür (hata vermez, `typeof` kontrolü yutar).
    """
    assert re.search(desen, MAP_ENGINE), f"map-engine.js'te {sembol} yok"
    assert sembol in MAP_KOPRU, f"köprü {sembol} kullanmıyor"


def test_kopru_map_engineden_SONRA_yukleniyor():
    """Sıra kapıdır: köprü önce yüklenirse global'ler henüz tanımsızdır."""
    i_engine = INDEX.find("map-engine.js?v=")
    i_kopru = INDEX.find("map-kopru.js?v=")
    assert i_engine != -1 and i_kopru != -1, "script etiketleri index.html'de yok"
    assert i_engine < i_kopru, "map-kopru.js, map-engine.js'ten ÖNCE yükleniyor"


def test_kopru_her_yoldan_SONUC_donuyor():
    """Köprü `komutIsle`'de cevabı koşulsuz yollamalı.

    Bir dal cevapsız kalırsa backend 8 sn bekleyip zaman aşımına düşer ve
    kullanıcı sebebi belirsiz bir gecikme yaşar.
    """
    assert "harita_sonuc" in MAP_KOPRU
    assert "catch" in MAP_KOPRU, "istisna yolu da sonuç döndürmeli"


# ── ① cevap beklemek: zaman aşımı SONUÇTUR, istisna değil ──────────────────
async def test_cevap_gelmezse_ulasildi_FALSE_doner(monkeypatch):
    """Harita kapalıyken araç patlamamalı — ne olduğunu söylemeli."""
    monkeypatch.setattr(harita_kopru, "BEKLEME_SN", 0.05)

    async def sahte_broadcast(mesaj):
        return None

    from app.api import websocket
    monkeypatch.setattr(websocket._manager, "broadcast", sahte_broadcast)

    s = await harita_kopru.gonder({"eylem": "durum"})
    assert s["ulasildi"] is False
    assert "cevap vermedi" in s["hata"]


async def test_zaman_asiminda_bekleyen_kayit_SIZMIYOR(monkeypatch):
    """Her başarısız komut bir Future bırakırsa sözlük sınırsız büyür."""
    monkeypatch.setattr(harita_kopru, "BEKLEME_SN", 0.02)

    async def sahte_broadcast(mesaj):
        return None

    from app.api import websocket
    monkeypatch.setattr(websocket._manager, "broadcast", sahte_broadcast)

    for _ in range(5):
        await harita_kopru.gonder({"eylem": "durum"})
    assert harita_kopru._bekleyenler == {}


async def test_sonuc_bekleyen_caginin_cevabi_oluyor(monkeypatch):
    """Mutlu yol: frontend cevap verince araç onu görür."""
    async def sahte_broadcast(mesaj):
        # Frontend'i taklit et: aynı istek_id ile cevabı geri yolla.
        harita_kopru.sonuc_geldi(mesaj["istek_id"],
                                 {"ok": True, "lat": 39.9, "lon": 32.85, "zoom": 11})

    from app.api import websocket
    monkeypatch.setattr(websocket._manager, "broadcast", sahte_broadcast)

    s = await harita_kopru.gonder({"eylem": "git", "yer": "Ankara"})
    assert s["ulasildi"] is True and s["ok"] is True and s["lat"] == 39.9


async def test_COK_ISTEMCI_basarili_cevap_kazanir(monkeypatch):
    """🔴 Canlı turda görülen yarış: Electron + tarayıcı + telefon aynı anda bağlı.

    MAP sekmesi yalnız birinde açıksa üç cevap döner. İlk gelen kazansaydı,
    harita gerçekten uçmuşken Yuki "MAP sekmesi açılmadı" diyebilirdi.
    """
    async def sahte_broadcast(mesaj):
        iid = mesaj["istek_id"]
        # ① MAP'i kapalı istemci önce cevaplıyor
        harita_kopru.sonuc_geldi(iid, {"ok": False, "hata": "MAP sekmesi henüz açılmadı."})
        # ② MAP'i açık istemci sonra
        harita_kopru.sonuc_geldi(iid, {"ok": True, "lat": 39.9, "lon": 32.85, "zoom": 11})

    from app.api import websocket
    monkeypatch.setattr(websocket._manager, "broadcast", sahte_broadcast)

    s = await harita_kopru.gonder({"eylem": "git", "yer": "Ankara"})
    assert s["ok"] is True, "olumsuz cevap yarışı kazandı"
    assert s["lat"] == 39.9


async def test_TUM_istemciler_basarisizsa_hata_yine_de_geliyor(monkeypatch):
    """Başarılıyı beklemek, hiç cevap gelmediğinde bilgiyi kaybetmemeli.

    Bu kapı olmasaydı "başarılı kazanır" kuralı, olumsuz cevabı yutar ve
    kullanıcı sebebini asla öğrenemezdi ("harita cevap vermedi" derdik —
    oysa cevap gelmişti).
    """
    monkeypatch.setattr(harita_kopru, "BEKLEME_SN", 0.05)

    async def sahte_broadcast(mesaj):
        harita_kopru.sonuc_geldi(mesaj["istek_id"],
                                 {"ok": False, "hata": "MAP sekmesi henüz açılmadı."})

    from app.api import websocket
    monkeypatch.setattr(websocket._manager, "broadcast", sahte_broadcast)

    s = await harita_kopru.gonder({"eylem": "durum"})
    assert s["ulasildi"] is True, "cevap gelmişti, 'hiç cevap yok' denemez"
    assert s["ok"] is False and "MAP sekmesi" in s["hata"]


def test_bilinmeyen_istek_id_SESSIZCE_atiliyor():
    """Zaman aşımına uğramış bir cevap, sonraki isteğe teslim EDİLMEMELİ.

    Edilseydi iki komut birbirine karışır ve "Ankara'ya git" komutuna bir
    önceki "durum" sorgusunun cevabı dönerdi.
    """
    assert harita_kopru.sonuc_geldi("olmayan-kimlik", {"ok": True}) is False


async def test_ayni_cevap_IKINCI_kez_teslim_edilmez(monkeypatch):
    async def sahte_broadcast(mesaj):
        harita_kopru.sonuc_geldi(mesaj["istek_id"], {"ok": True})
        # İkinci kez teslim denemesi — çağrı zaten tamamlandı
        assert harita_kopru.sonuc_geldi(mesaj["istek_id"], {"ok": False}) is False

    from app.api import websocket
    monkeypatch.setattr(websocket._manager, "broadcast", sahte_broadcast)
    s = await harita_kopru.gonder({"eylem": "durum"})
    assert s["ok"] is True


# ── araç katmanı: dönüş metinleri gerçeği anlatıyor mu ─────────────────────
async def test_hedefsiz_goto_aciklama_veriyor():
    assert "belirtilmedi" in await harita.map_goto()


async def test_harita_kapaliyken_goto_YAPTIM_demiyor(monkeypatch):
    monkeypatch.setattr(harita_kopru, "BEKLEME_SN", 0.02)

    async def sahte_broadcast(mesaj):
        return None

    from app.api import websocket
    monkeypatch.setattr(websocket._manager, "broadcast", sahte_broadcast)

    metin = await harita.map_goto("Ankara")
    assert "götürüldü" not in metin, "harita cevap vermeden başarı iddia edildi"
    assert "MAP sekmesi" in metin or "cevap vermedi" in metin


async def test_bos_katman_listesi_BILINMIYOR_demiyor(monkeypatch):
    """Boş liste "hiç katman yok" demektir; "bilinmiyor" değil."""
    async def sahte_broadcast(mesaj):
        harita_kopru.sonuc_geldi(mesaj["istek_id"],
                                 {"ok": True, "lat": 39.9, "lon": 32.8,
                                  "zoom": 6, "acik_katmanlar": []})

    from app.api import websocket
    monkeypatch.setattr(websocket._manager, "broadcast", sahte_broadcast)
    metin = await harita.map_status()
    assert "açık katman yok" in metin


async def test_gecersiz_katman_adi_ARACTA_da_reddediliyor():
    metin = await harita.map_layer("kahve")
    assert "Bilinmeyen katman" in metin


# ── 🔴 CANLI TURDA BULUNDU ────────────────────────────────────
@pytest.mark.parametrize("cagri", [
    lambda: harita.map_goto("Ankara"),
    lambda: harita.map_layer("deprem"),
    lambda: harita.map_status(),
])
async def test_ulasildi_ama_OK_DEGIL_ham_alan_basmiyor(monkeypatch, cagri):
    """"Ulaşıldı" ile "başarılı oldu" AYRI iki sorudur.

    Canlı turda `map_status` bunu karıştırdı: frontend
    `{ok:false, hata:'MAP sekmesi henüz açılmadı'}` demişken araç
    *"Harita merkezi None, None · yakınlaştırma None"* bastı. `map_goto` ve
    `map_layer` kapıyı taşıyordu, `map_status` unutmuştu — ve testler `ok:True`
    besledikleri için üçünü de yeşil gördü.

    Bu test ÜÇÜNÜ birden ölçer: biri kapıyı kaybederse kırmızı yanar.
    """
    # Olumsuz cevap artık başarılıyı beklediği için zaman aşımına kadar sürer
    # (§ çok-istemci yarışı) — testte o bekleme kısaltılır, kural değişmez.
    monkeypatch.setattr(harita_kopru, "BEKLEME_SN", 0.05)

    async def sahte_broadcast(mesaj):
        harita_kopru.sonuc_geldi(mesaj["istek_id"],
                                 {"ok": False, "hata": "MAP sekmesi henüz açılmadı."})

    from app.api import websocket
    monkeypatch.setattr(websocket._manager, "broadcast", sahte_broadcast)

    metin = await cagri()
    assert "None" not in metin, f"başarısız cevabın ham alanları basıldı: {metin}"
    assert "MAP sekmesi" in metin or "okunamadı" in metin or "gidemedi" in metin, metin


# ── dispatcher kaydı ────────────────────────────────────────────────────────
def test_araclar_dispatcherda_KAYITLI():
    """Şemada olmayan araç LLM'e hiç sunulmaz — özellik "var ama ulaşılamaz" olur."""
    from app.services.tools.dispatcher import TOOLS
    adlar = {t["function"]["name"] for t in TOOLS}
    assert {"map_goto", "map_layer", "map_status"} <= adlar


async def test_dispatcher_dagitimi_araci_GERCEKTEN_cagiriyor(monkeypatch):
    """Şemaya eklenip dispatch dalı yazılmazsa araç "bilinmeyen" diye döner."""
    from app.services.tools import dispatcher

    async def sahte_broadcast(mesaj):
        harita_kopru.sonuc_geldi(mesaj["istek_id"], {"ok": True, "acik": True})

    from app.api import websocket
    monkeypatch.setattr(websocket._manager, "broadcast", sahte_broadcast)

    sonuc = await dispatcher._call_tool_impl("map_layer", {"katman": "deprem"})
    assert "açıldı" in str(sonuc)


# ── WS + core.js bağlantısı ─────────────────────────────────────────────────
def test_ws_harita_sonuc_sohbet_akisina_girmeden_teslim_ediliyor():
    """`harita_sonuc` işlenmezse cevap hiç teslim edilmez (8 sn zaman aşımı)
    ya da boş bir kullanıcı turu başlar."""
    ws = (KOK / "backend" / "app" / "api" / "websocket.py").read_text(encoding="utf-8")
    i = ws.index('"harita_sonuc"')
    assert "harita_kopru.sonuc_geldi" in ws[i:i + 600]
    assert "continue" in ws[i:i + 700]


def test_core_js_harita_komutunu_kopruye_veriyor():
    core = (KOK / "frontend" / "js" / "core.js").read_text(encoding="utf-8")
    assert "d.type === 'harita_komut'" in core and "YukiHarita.komutIsle" in core
    assert "window.YukiHarita" in MAP_KOPRU
