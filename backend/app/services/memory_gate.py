"""Anı seçim kapısı — mutlak eşik yerine SIRA-duyarlı (göreli) filtre.

Neden: cosine skoru modele ve dile göre sıkışır. Ölçüm (paraphrase-multilingual
MiniLM, TR): doğru anı sorguların çoğunda **1. sırada** çıkıyor ama skoru
0.24–0.79 arasında geziyor. Sabit 0.40 eşiği "nerede oturuyorum" (0.242, sıra 1)
gibi doğru eşleşmeleri eliyordu → Ultra'nın semantik hafızası sohbete hiç
girmiyordu.

Kural: gerçek çöpü elemek için düşük bir MUTLAK taban + en iyi sonuca göre
GÖRELİ bir kapı. Böylece eşik, sorgunun kendi skor ölçeğine uyum sağlar.
"""
from __future__ import annotations

from typing import Iterable, TypeVar

T = TypeVar("T")


def relative_cutoff(best: float, floor: float, ratio: float) -> float:
    """Bu sorgu için etkin eşik: max(mutlak taban, en iyi skor × oran)."""
    return max(floor, best * ratio)


def filter_relative(
    items: Iterable[T],
    floor: float,
    ratio: float,
    key=lambda m: m.similarity,
) -> list[T]:
    """En iyi skora göre göreli kapı uygula (mutlak taban da geçerli).

    Boş girdide boş liste döner. Sıralamayı korur.
    """
    items = list(items)
    if not items:
        return []
    best = max(key(m) for m in items)
    cutoff = relative_cutoff(best, floor, ratio)
    return [m for m in items if key(m) >= cutoff]
