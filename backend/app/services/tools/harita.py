"""Yuki'nin harita araçları — MAP sekmesini sürer (GeoLibre FAZ 2).

İlk tasarım bu işi *"Yuki ↔ harita **iframe**'ine `postMessage` köprüsü"* diye
tarif ediyordu. Ölçüldü: **o tarif geçersiz.** MAP sekmesi bir iframe değil, Yuki'nin
kendi belgesinde koşan Leaflet + MapLibre katmanı (`map-engine.js`);
`postMessage` aynı belge içinde gereksiz bir dolambaç olurdu — köprülenecek
iframe ortada yok.

İşin özü değişmedi: *Yuki haritayı sürebilsin.* Yol değişti.

🔑 **Dönüş metinleri GERÇEKLEŞENİ anlatır.** Her araç `harita_kopru` üzerinden
frontend'in cevabını bekler; harita kapalıysa "gösterdim" demez, açık olmadığını
söyler. Sebebi `harita_kopru` başlığında yazılı.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

#: Kullanıcının söyleyebileceği ad → `toggleLayer()` anahtarı.
#: Anahtarlar `map-engine.js::toggleLayer` ve `index.html`'deki `map-layer-*`
#: düğme id'leriyle **aynı** olmak zorunda; uydurma ad sessizce hiçbir şey
#: yapmayan bir çağrı üretirdi.
KATMANLAR: dict[str, str] = {
    "deprem": "eq", "sismik": "eq", "eq": "eq",
    "yangın": "fire", "yangin": "fire", "fire": "fire",
    "volkan": "volcano", "yanardağ": "volcano", "yanardag": "volcano", "volcano": "volcano",
    "iss": "iss", "uzay istasyonu": "iss",
    "uçak": "adsb", "ucak": "adsb", "uçuş": "adsb", "ucus": "adsb", "adsb": "adsb",
    "uydu": "sat", "sat": "sat",
}


def _katman_coz(ad: str) -> str | None:
    return KATMANLAR.get((ad or "").strip().lower())


async def map_goto(yer: str = "", lat: float | None = None,
                   lon: float | None = None, zoom: int | None = None) -> str:
    """Haritayı bir yere götürür — yer **adı** ya da koordinat.

    Yer adı verilirse çözümü frontend yapar (Nominatim zaten orada; ikinci bir
    çözücü ikinci bir bayatlama kaynağı olurdu → `harita_kopru` başlığı).
    """
    from app.services import harita_kopru

    if not yer and (lat is None or lon is None):
        return "Nereye gidileceği belirtilmedi: bir yer adı ya da lat/lon ver."

    s = await harita_kopru.gonder({
        "eylem": "git", "yer": yer, "lat": lat, "lon": lon, "zoom": zoom,
    })
    if not s.get("ulasildi"):
        return (f"{s.get('hata')} Haritayı açmak için 'harita sekmesine geç' diyebilirsin.")
    if not s.get("ok"):
        return f"Harita gidemedi: {s.get('hata') or 'bilinmeyen sebep'}"

    ad = s.get("ad") or yer or f"{lat}, {lon}"
    return (f"Harita {ad} konumuna götürüldü "
            f"({s.get('lat')}, {s.get('lon')} · yakınlaştırma {s.get('zoom')}).")


async def map_layer(katman: str, ac: bool = True) -> str:
    """Harita katmanını açar/kapatır (deprem · yangın · volkan · ISS · uçak · uydu)."""
    from app.services import harita_kopru

    anahtar = _katman_coz(katman)
    if anahtar is None:
        return (f"Bilinmeyen katman: '{katman}'. "
                f"Geçerli olanlar: {', '.join(sorted(set(KATMANLAR.values())))}.")

    s = await harita_kopru.gonder({"eylem": "katman", "katman": anahtar, "ac": bool(ac)})
    if not s.get("ulasildi"):
        return s.get("hata", "Haritaya ulaşılamadı.")
    if not s.get("ok"):
        return f"Katman değiştirilemedi: {s.get('hata') or 'bilinmeyen sebep'}"
    return f"{katman} katmanı {'açıldı' if s.get('acik') else 'kapatıldı'}."


async def map_status() -> str:
    """Haritada şu an ne görünüyor — merkez, yakınlaştırma, açık katmanlar."""
    from app.services import harita_kopru

    s = await harita_kopru.gonder({"eylem": "durum"})
    if not s.get("ulasildi"):
        return s.get("hata", "Haritaya ulaşılamadı.")
    # 🔴 `ok` kapısı CANLI TURDA eklendi. Yokken şu çıkıyordu:
    # *"Harita merkezi None, None · yakınlaştırma None"* — frontend zaten
    # `{ok:false, hata:'MAP sekmesi henüz açılmadı'}` demişti, araç onu okumadan
    # alanları basıyordu. 📏 Ders: "ulaşıldı" ile "başarılı oldu" AYRI iki
    # sorudur; kardeş fonksiyonların ikisinde de vardı, burada unutulmuştu ve
    # testler `ok:True` besledikleri için kusuru göremedi.
    if not s.get("ok"):
        return s.get("hata") or "Harita durumu okunamadı."
    katman = s.get("acik_katmanlar") or []
    # 🔑 Boş liste "bilinmiyor" DEĞİL "hiç katman yok" demektir — ikisini aynı
    # cümleyle anlatmak modeli yanlış çıkarıma iter.
    kat_metin = ", ".join(katman) if katman else "açık katman yok"
    return (f"Harita merkezi {s.get('lat')}, {s.get('lon')} · "
            f"yakınlaştırma {s.get('zoom')} · {kat_metin}.")
