"""TÜRKİYE/DÜNYA kipinden dönünce 3B harita görünür kalır (statik, sunucusuz).

`clearPlanetMode` 2B haritaya satır içi `opacity: 1` yazıyordu; satır içi stil
`#leaflet-map.hidden-3d { opacity: 0 }` kuralını ezdiği için TÜRKİYE/DÜNYA'ya bir kez
basıldıktan sonra 3B, opak 2B haritanın altında kalıyordu. Kişisel Yuki'deki düzeltmenin
yeniden yazımı: satır içi değer silinir, sınıf kuralı yine çalışır.
"""
import re
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]


def _govde(ad):
    js = (KOK / "js" / "map-engine.js").read_text("utf-8")
    m = re.search(r"function %s\(\)\s*\{(.*?)\n\}" % ad, js, re.S)
    assert m, f"{ad} bulunamadı"
    return m.group(1)


def test_clear_planet_satir_ici_opaklik_yazmaz():
    govde = _govde("clearPlanetMode")
    yazimlar = re.findall(r"leaflet-map'\)\.style\.opacity\s*=\s*'([^']*)'", govde)
    assert yazimlar == [""], yazimlar


def test_hidden_3d_kurali_duruyor():
    css = (KOK / "css" / "map-controls.css").read_text("utf-8")
    assert re.search(r"#leaflet-map\.hidden-3d\s*\{[^}]*opacity:\s*0", css)
