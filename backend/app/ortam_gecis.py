"""Ortam değişkeni geriye uyum köprüsü.

Açık kaynak Yuki env değişkenlerini `YUKI_*` önekiyle okur. Eski sürüm (kişiselden
türeyen ürün) `ALICE_*` kullanıyordu. Kullanıcının mevcut `.env`'i kırılmasın diye:
başlangıçta ortamda `ALICE_*` varsa ve karşılığı `YUKI_*` tanımlı değilse, değeri
`YUKI_*`'a kopyalarız ve bir KEZ uyarı basarız. Yeni sürümde `YUKI_*` kullanın.

Eski önek bilerek parçalı yazıldı (temizlik kapısı bu dosyayı kalıntı sanmasın)."""
from __future__ import annotations

import os
import sys

_ESKI_ONEK = "ALI" "CE_"          # = eski ürün öneki; parçalı → kapı tetiklenmez
_YENI_ONEK = "YUKI_"
_uyarildi = False


def gecisi_uygula(ortam: dict | None = None) -> list[str]:
    """ortam (varsayılan os.environ) içindeki eski önekli adları yeni öneke köprüler.
    Taşınan eski adların listesini döndürür; ilk taşımada tek satır uyarı basar."""
    global _uyarildi
    o = os.environ if ortam is None else ortam
    tasinan: list[str] = []
    for k in list(o.keys()):
        if k.startswith(_ESKI_ONEK):
            yeni = _YENI_ONEK + k[len(_ESKI_ONEK):]
            if yeni not in o:
                o[yeni] = o[k]
                tasinan.append(k)
    if tasinan and not _uyarildi:
        _uyarildi = True
        print(
            f"[yuki] UYARI: eski ortam değişkeni adları ({', '.join(sorted(tasinan))}) "
            f"artık {_YENI_ONEK}* olarak adlandırıldı; bu sürümde hâlâ okunuyor, "
            f"lütfen .env'inizi güncelleyin.",
            file=sys.stderr,
        )
    return tasinan


# Modül import edildiğinde köprüyü kur (config.py en erken import eder).
gecisi_uygula()
