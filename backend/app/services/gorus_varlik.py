"""Kamera görüşü — varlık durum makinesi ("seni görüyorum").

Girdi yalnız SAYI: karede kaç yüz var + zaman. Kare bu modüle hiç gelmez.

Durumlar: yok → geldi → burada → gitti → yok
  · geldi  : art arda `GEL_KARE` yüzlü kare (tek yanlış algılama "geldi" yapmaz). Tek tıklık.
  · burada : kısa kayıplar (başını çevirdi, el yüzü kapattı) `YOK_SN` dolana kadar durumu
             değiştirmez (histerezis).
  · gitti  : son yüzden bu yana `YOK_SN` geçti ve son kare yüzsüz. Tek tıklık; sonra `yok`.

Olaylar (çağırana döner, kendisi konuşmaz):
  · tanima_iste : yalnız gelişte ve son tanımadan ≥ `TANIMA_ARALIK_SN` sonra (tanıma pahalı).
  · selam       : tanıma bilinen bir ad döndürdüyse, kişi ≥ `DONUS_MIN_SN` uzaktaysa ve son
                  selamdan ≥ `SELAM_ARALIK_SN` geçtiyse. Tavan SÜREÇ genelinde (`SelamDefteri`):
                  kamera yeniden bağlanınca sıfırlanmaz.
  · mola        : kesintisiz oturuş ≥ `MOLA_SN`; ardından en erken `MOLA_SN` sonra yine.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field

GEL_KARE = 3
YOK_SN = 20.0
TANIMA_ARALIK_SN = 60.0
DONUS_MIN_SN = 300.0
SELAM_ARALIK_SN = 1800.0
MOLA_SN = 50 * 60.0


class SelamDefteri:
    """Süreç genelinde selam tavanı."""

    def __init__(self) -> None:
        self._son: float | None = None
        self._kilit = threading.Lock()

    def izin_ver(self, t: float) -> bool:
        with self._kilit:
            if self._son is not None and t - self._son < SELAM_ARALIK_SN:
                return False
            self._son = t
            return True

    def sifirla(self) -> None:
        with self._kilit:
            self._son = None


defter = SelamDefteri()


def _ortak_defter() -> SelamDefteri:
    return defter


@dataclass
class VarlikIzleyici:
    """Bağlantı başına durum. `kare(yuz_sayisi, t)` her işlenen karede çağrılır."""

    defter: SelamDefteri = field(default_factory=_ortak_defter)
    durum: str = "yok"
    _ardisik: int = 0
    _son_yuz: float | None = None
    _son_ayrilis: float | None = None
    _son_tanima: float | None = None
    _oturus_bas: float | None = None
    _son_mola: float | None = None
    _tanima_bekliyor: bool = False

    def kare(self, yuz_sayisi: int, t: float) -> list[str]:
        olaylar: list[str] = []
        var = yuz_sayisi > 0
        self._ardisik = self._ardisik + 1 if var else 0
        if var:
            self._son_yuz = t

        if self.durum == "geldi":
            self.durum = "burada"
        elif self.durum == "gitti":
            self.durum = "yok"

        if self.durum == "yok":
            if self._ardisik >= GEL_KARE:
                self.durum = "geldi"
                self._oturus_bas = t - (GEL_KARE - 1)
                olaylar.append("geldi")
                if self._son_tanima is None or t - self._son_tanima >= TANIMA_ARALIK_SN:
                    self._son_tanima = t
                    self._tanima_bekliyor = True
                    olaylar.append("tanima_iste")
        elif self.durum == "burada":
            if not var and self._son_yuz is not None and t - self._son_yuz >= YOK_SN:
                self.durum = "gitti"
                self._son_ayrilis = self._son_yuz
                self._oturus_bas = None
                self._tanima_bekliyor = False
                olaylar.append("gitti")
            elif var and self._oturus_bas is not None and t - self._oturus_bas >= MOLA_SN and (
                    self._son_mola is None or t - self._son_mola >= MOLA_SN):
                self._son_mola = t
                olaylar.append("mola")
        return olaylar

    def tanima_sonucu(self, ad: str | None, t: float) -> list[str]:
        """`tanima_iste`'ye gelen cevap. Selam kararı burada verilir."""
        if not self._tanima_bekliyor:
            return []
        self._tanima_bekliyor = False
        if not ad or self.durum not in ("geldi", "burada"):
            return []
        if self._son_ayrilis is not None and t - self._son_ayrilis < DONUS_MIN_SN:
            return []
        if not self.defter.izin_ver(t):
            return []
        return ["selam"]
