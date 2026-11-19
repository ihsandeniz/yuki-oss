"""`kameraya_bak` aracı — "Yuki bak" dendiğinde kameradan tek kareye yerel modelle bakar.

Araç kaydı: dispatcher `TOOLS` + `call_tool`, bayrak `yetki.ARACLAR['gorus']`, alan `alan_secici` kamera. Araç kendi kapılarını da taşır:
bayrak kapalıysa ya da rıza yoksa kareye hiç dokunmaz, nedenini söyler.
"""
from __future__ import annotations

TANIM = {
    "name": "kameraya_bak",
    "description": ("Kullanıcı 'bak', 'ne görüyorsun', 'elimde ne var' gibi kameraya bakmanı istediğinde "
                    "kameradan TEK kare alır ve bu bilgisayardaki yerel görsel modelle betimler. "
                    "Görüntü saklanmaz, dışarı gönderilmez."),
    "input_schema": {
        "type": "object",
        "properties": {"soru": {"type": "string", "description": "Kareye sorulacak soru (isteğe bağlı)"}},
    },
}


async def kameraya_bak(soru: str = "") -> str:
    from app.api.gorus_api import bayrak_acik
    from app.services import biyometrik_riza, gorus_bak
    if not bayrak_acik():
        return "Kamera görüşü bu kurulumda kapalı; bakamıyorum."
    if not biyometrik_riza.var_mi("gorus"):
        return "Kamera görüşü için rıza verilmedi; ayarlardan açılınca bakabilirim."
    sonuc = await gorus_bak.bak(soru)
    if not sonuc["ok"]:
        return sonuc["metin"]
    return ("Kameradan tek kareye yerel modelle baktım (görüntü saklanmadı). Gördüğüm: "
            f"{sonuc['metin']}\n[Bunu kendi sözünle kısa aktar; burada olmayanı ekleme.]")
