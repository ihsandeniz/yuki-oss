"""TR recall ölçümü — anı sohbete giriyor mu? (B1 kanıt scripti)

Tam yolu taklit eder: search() (mutlak taban + göreli kapı) → _build_context
kategori kapısı. Pozitif sorgular doğru anıyı çekmeli, negatif sorgular
alakasız anı ENJEKTE ETMEMELİ.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services import memory_sqlite as ms  # noqa: E402
from app.config import (  # noqa: E402
    MEMORY_MIN_SIMILARITY,
    MEMORY_REL_RATIO,
    MEMORY_SEARCH_LIMIT,
)
from app.services.memory_gate import relative_cutoff  # noqa: E402

ANILAR = [
    ("Kullanıcı Arch Linux kullanıyor, masaüstü ortamı Hyprland.", "fact"),
    ("Kullanıcının adı Geliştirici.", "fact"),
    ("Kullanıcı kahveyi sütsüz seviyor.", "preference"),
    ("Kullanıcı akşamları kod yazmayı tercih ediyor.", "preference"),
    ("Kullanıcının kedisinin adı Mırmır.", "fact"),
    ("Kullanıcı Python ve JavaScript ile çalışıyor.", "fact"),
    ("Kullanıcı Ankara'da yaşıyor.", "fact"),
    ("Bugün hava çok sıcaktı ve dışarı çıkmadık.", "conversation"),
    ("Dün akşam film izledik, bilim kurgu türündeydi.", "conversation"),
    ("Kullanıcı sabahları erken kalkmakta zorlanıyor.", "preference"),
]

POZITIF = [
    ("hangi işletim sistemini kullanıyorum", 0),
    ("benim adım ne", 1),
    ("kahvemi nasıl içerim", 2),
    ("kedimin adı neydi", 4),
    ("hangi dillerde kod yazıyorum", 5),
    ("nerede oturuyorum", 6),
    ("ne zaman çalışmayı severim", 3),
]

# Hafızada karşılığı OLMAYAN sorgular — bunlarda bağlam boş ya da çok kısa olmalı.
NEGATIF = [
    "fotosentez nasıl çalışır",
    "dolar kuru kaç oldu",
    "kuantum dolanıklık nedir",
]


def _baglam_satirlari(relevant):
    """llm._build_context'teki kategori kapısının birebir kopyası."""
    best = max((m.similarity for m in relevant), default=0.0)
    fact_gate = relative_cutoff(best, MEMORY_MIN_SIMILARITY, MEMORY_REL_RATIO)
    conv_gate = relative_cutoff(best, MEMORY_MIN_SIMILARITY + 0.10, 0.85)
    out = []
    for m in relevant:
        if m.category in ("preference", "fact") and m.similarity >= fact_gate:
            out.append(m.content)
        elif m.category == "conversation" and m.similarity >= conv_gate:
            out.append(m.content)
    return out


async def main():
    svc = ms.SqliteVecMemoryService()
    for icerik, kat in ANILAR:
        await svc.add(icerik, category=kat, scope=kat, role="user")

    print(f"taban={MEMORY_MIN_SIMILARITY}  oran={MEMORY_REL_RATIO}  "
          f"limit={MEMORY_SEARCH_LIMIT}  anı={len(ANILAR)}\n")
    print(f"{'POZİTİF sorgu':36} {'skor':>6} {'bağlam':>7}  sonuç")
    print("-" * 74)
    gecen = 0
    for sorgu, idx in POZITIF:
        rel = await svc.search(sorgu, limit=MEMORY_SEARCH_LIMIT)
        satirlar = _baglam_satirlari(rel)
        beklenen = ANILAR[idx][0]
        skor = next((m.similarity for m in rel if m.content == beklenen), 0.0)
        ok = beklenen in satirlar
        gecen += ok
        print(f"{sorgu:36} {skor:6.3f} {len(satirlar):7}  "
              f"{'✅ enjekte edildi' if ok else '❌ DÜŞTÜ'}")

    print(f"\n{'NEGATİF sorgu':36} {'bağlam':>7}  sonuç")
    print("-" * 74)
    temiz = 0
    for sorgu in NEGATIF:
        rel = await svc.search(sorgu, limit=MEMORY_SEARCH_LIMIT)
        satirlar = _baglam_satirlari(rel)
        ok = len(satirlar) <= 2          # tamamen boş şart değil; sel olmamalı
        temiz += ok
        print(f"{sorgu:36} {len(satirlar):7}  "
              f"{'✅ temiz' if ok else '⚠️ gürültü: ' + str(satirlar)}")

    print(f"\nPOZİTİF: {gecen}/{len(POZITIF)} · NEGATİF temiz: {temiz}/{len(NEGATIF)}")


if __name__ == "__main__":
    asyncio.run(main())
