"""Masaüstü Yuki — saf mantık (GTK'siz, test edilebilir): tıklama bölgesi (alfa) + pencere ölçüsü.

Chibi sprite yaprağı (Moonveil, Codex pets kökenli, dağıtım lisansı belirsiz) bu kopyada YOK; yalnız
alfa kutusu/şerit ve kip tam ölçüsü kaldı. Pencere/çizim `yuki_govde.py`'de.
"""

from __future__ import annotations


def alfa_kutusu(pikseller: bytes, w: int, h: int, rowstride: int, kanal: int = 4,
                esik: int = 8) -> tuple[int, int, int, int] | None:
    """Alfası `esik`ten büyük piksellerin sınır kutusu (x, y, w, h); tamamen saydamsa None.

    Tıklama bölgesi bundan kurulur: kutunun dışı tıklamayı alttaki pencereye geçirir.
    """
    if kanal != 4:
        return (0, 0, w, h)
    x0, y0, x1, y1 = w, h, -1, -1
    for y in range(h):
        satir = pikseller[y * rowstride: y * rowstride + w * 4]
        alfalar = satir[3::4]
        sol = next((x for x, a in enumerate(alfalar) if a > esik), None)
        if sol is None:
            continue
        sag = w - 1 - next(x for x, a in enumerate(reversed(alfalar)) if a > esik)
        x0, x1 = min(x0, sol), max(x1, sag)
        y0, y1 = min(y0, y), max(y1, y)
    if x1 < 0:
        return None
    return x0, y0, x1 - x0 + 1, y1 - y0 + 1




def alfa_bantlari(pikseller: bytes, w: int, h: int, rowstride: int, bant: int = 16,
                  esik: int = 8) -> list[tuple[int, int, int, int]]:
    """Görüntüyü `bant` yatay şeride böl, her şeridin alfa kutusunu ver (boş şerit atlanır).

    Tek kutu büst portrede neredeyse tüm kareyi kaplıyor (omuzlar genişliği dolduruyor), başın iki
    yanındaki saydam köşeler de tıklamayı yutuyordu. Şeritler karakterin şekline uyar.
    """
    out = []
    for b in range(bant):
        y0, y1 = h * b // bant, h * (b + 1) // bant
        if y1 <= y0:
            continue
        parca = pikseller[y0 * rowstride: y1 * rowstride]
        k = alfa_kutusu(parca, w, y1 - y0, rowstride, 4, esik)
        if k:
            out.append((k[0], y0 + k[1], k[2], k[3]))
    return out


TAM_ORAN = 0.45      # kip tam: pencere boyu = ekran yüksekliği × oran ("tam boy")
TAM_EN_BOY = 0.5     # en = boy × 0.5 — kollar yanda dururken de el sallarken de sığar


def tam_boy_olcu(boyut: float | None, ekran_h: int) -> tuple[int, int]:
    """Kip tam pencere ölçüsü (en, boy). `boyut`: None → ekranın %45'i · ≤1 → oran · >1 → piksel boy.

    Boy 200 px ile ekran yüksekliği arasında kalır.
    """
    if boyut is None or boyut <= 0:
        boy = ekran_h * TAM_ORAN
    elif boyut <= 1:
        boy = ekran_h * boyut
    else:
        boy = boyut
    boy = int(round(min(max(boy, 200), ekran_h)))
    return int(round(boy * TAM_EN_BOY)), boy
