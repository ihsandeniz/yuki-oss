"""H1-d ölçümü için yazıcı (Harness H1) — test_gorev_kuyrugu.py çağırır, dışarıdan kill -9 edilir.

Ayrı SÜREÇTE gerçek `GorevKuyrugu._kaydet` yolunu durmadan koşar (büyük kayıt: ~1,3 MB,
yazım uzun sürsün ki öldürme yazımın ortasına denk gelsin). Kök `YUKI_ATOLYE_KOK`.
İlk yazımdan sonra `HAZIR` basar. :8000'e, ~/YukiAtolye'ye, LLM'e dokunmaz.
"""
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.gorev import GorevServisi  # noqa: E402
from app.services.gorev_kuyrugu import GorevKuyrugu  # noqa: E402

KOK = Path(os.environ["YUKI_ATOLYE_KOK"])
KAYIT = 300


def main() -> None:
    k = GorevKuyrugu(GorevServisi(KOK, bildir=lambda *a: None))
    if len(k._kayitlar) < KAYIT:
        son = time.time() + 86400
        k._kayitlar = [{"id": f"Q-20261022-{i + 1:04d}", "tur": "deneme", "ad": f"y{i}",
                        "istek": "ş" * 4000, "kaynak": "kullanici", "durum": "oneri",
                        "son_gecerlilik": son, "yazim": 0} for i in range(KAYIT)]
    k._kaydet()
    print("HAZIR", flush=True)
    while True:
        k._kayitlar[0]["yazim"] = k._kayitlar[0].get("yazim", 0) + 1
        k._kaydet()


if __name__ == "__main__":
    main()
