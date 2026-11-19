"""InsightFace `landmark_2d_106` anatomik haritası + yüz bölgeleme (FAZ 0 + FAZ 1).

📦 **ÜRÜN NOTU ( Dalga 2 FAZ 4, 2026-09-05):** bu dosya kişisel Alice'ten
(`projects/AliceAi`) **olduğu gibi** taşındı. Tek satırı değiştirilmedi ve
değiştirilmemeli: içindeki her eşik gerçek yüzlerde ölçülmüş, `GOZ_KAPALI_ESIGI`
22 kare + 6 farklı yüzle iki kez doğrulanmış, `POZA_BAGLI` tablosu 22 karede
sayılmıştır. Bu sayıları burada "ürüne uygun" diye yeniden seçmek, ölçümü
tahminle değiştirmek olurdu.

Üründe kullanıcısı: `face_liveness.py` — göz kırpma ile canlılık kontrolü.
Kişiseldeki kullanıcısı göz takibiydi; ürüne göz takibi taşınmadı.
İki kopya ayrışırsa **kişiseldeki asıldır** (ölçüm orada yapılıyor).


✅ **FAZ 0 GÖZLE ONAYLANDI** (geliştirici, 2026-08-03): numaralı PNG'de her renk doğru organı
örtüyor. Onay sonrası FAZ 1 fonksiyonları (`bolgele`, `goz_kutusu`, `goz_acikligi`)
bu dosyanın altına eklendi.

## Bu sayılar nereden geldi (tahmin DEĞİL)

Üretici: `backend/scripts/landmark_haritasi_cikar.py` — yeniden koşulabilir.
Girdi: geliştiricinin webcam'inden 7 kare (yaw −27°…+38°, pitch −13°…+19°; 22 karenin
poz çeşitliliğine göre seçilmiş 7'si). Görüntüler **repo'ya girmedi**, scratchpad'de kaldı.

İki geçişli ölçüm:

1. **68-nokta köprüsü.** 106'nın haritası bilinmiyor ama `landmark_3d_68` **300W/dlib
   standardını** kullanıyor ve o sıralama belgeli. Aynı yüzden ikisi de çıkarılıp her
   106-nokta en yakın 68-noktanın BİLİNEN grubunu devraldı.
2. **Küme rafinesi.** 1. geçişin sistematik bir hatası ölçüldü: 68 modelinin **iç göz
   köşesi** landmark'ı burun sırtının tepesine düşüyor → 76 ve 82 "göz" etiketi almıştı.
   2. geçiş 68'e hiç bakmaz; oybirliğiyle oturmuş kümelerin **en yakın noktasına** göre
   yeniden oylar. 11 indeksi düzeltti, '?' sayısını 7'den **0**'a indirdi.

Plandaki iki başarısız denemenin (ezber blok haritası · "en yakın 5 anahtar noktaya bak")
neden yanlış olduğu da böylece açıklandı: 5 nokta yüzü kaplamıyor, yakınlık organ vermiyor.

## Bilinen kararsızlıklar — dürüstlük notu

`KARARSIZ_SINIR` = **1** ve **17**: çene konturunun şakak uçları. 7 karenin bir kısmında
en yakın kesin küme KAŞ çıkıyor. Çoğunluk oyu CENE dedi ve öyle bırakıldı, ama üst/alt
bölme ya da açı hesabında bu iki indekse tek başına yaslanılmamalı.

Ağız içinde `AGIZ_DIS ↔ AGIZ_IC` arasında salınan 9 indeks var (54,57,58,60,62,65,66,69,70).
Organ değişmiyor, yalnız dudak dış/iç çizgisi ayrımı poza göre kayıyor — `AGIZ` birleşik
kümesi kullanıldığı sürece etkisiz.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

# ── Ana bölgeler ────────────────────────────────────────────────────────────
CENE: list[int] = [
    0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16,
    17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32,
]
SAG_KAS: list[int] = [43, 44, 45, 46, 47, 48, 49, 50, 51]
SOL_KAS: list[int] = [97, 98, 99, 100, 101, 102, 103, 104, 105]
BURUN_SIRTI: list[int] = [72, 73, 74, 86]
BURUN_TABANI: list[int] = [76, 77, 78, 79, 80, 82, 83, 84, 85]
SAG_GOZ: list[int] = [33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 75]
SOL_GOZ: list[int] = [81, 87, 88, 89, 90, 91, 92, 93, 94, 95, 96]
AGIZ_DIS: list[int] = [52, 53, 55, 56, 57, 58, 59, 61, 63, 64, 65, 67, 68, 70, 71]
AGIZ_IC: list[int] = [54, 60, 62, 66, 69]

# ── Türetilmiş kolaylık kümeleri ────────────────────────────────────────────
KAS: list[int] = sorted(SAG_KAS + SOL_KAS)
BURUN: list[int] = sorted(BURUN_SIRTI + BURUN_TABANI)
AGIZ: list[int] = sorted(AGIZ_DIS + AGIZ_IC)
GOZLER: list[int] = sorted(SAG_GOZ + SOL_GOZ)

BOLGELER: dict[str, list[int]] = {
    "CENE": CENE,
    "SAG_KAS": SAG_KAS,
    "SOL_KAS": SOL_KAS,
    "BURUN_SIRTI": BURUN_SIRTI,
    "BURUN_TABANI": BURUN_TABANI,
    "SAG_GOZ": SAG_GOZ,
    "SOL_GOZ": SOL_GOZ,
    "AGIZ_DIS": AGIZ_DIS,
    "AGIZ_IC": AGIZ_IC,
}

# ── Tekil, operasyonel olarak değerli noktalar (ayrıca ölçüldü) ─────────────

#: Burun ucu. 7/7 karede `kps[2]`'ye en yakın 106-nokta bu çıktı (ort. %2.4 yüz genişliği).
#: FAZ 1'in ÜST/ALT bölme çizgisi bundan okunacak — bbox oranından değil.
BURUN_UCU: int = 86

#: Göz merkezleri (bebek hizası). `kps[0]`/`kps[1]`'e ortalama uzaklık
#: sağda %0.9, solda %0.5 (yüz genişliğine oranla) — kümenin diğer noktaları %3-10.
SAG_GOZ_MERKEZ: list[int] = [34, 38]
SOL_GOZ_MERKEZ: list[int] = [88, 92]

#: Göz kümesinin merkeze EN UZAK noktaları = göz köşeleri (sağ %9.5/%10.2, sol %9.4/%9.9).
#: ⚠️ İç/dış köşe ayrımı BU TURDA YAPILMADI — FAZ 1'in işi.
SAG_GOZ_KOSE: list[int] = [35, 39]
SOL_GOZ_KOSE: list[int] = [89, 93]

#: Poza göre grup değiştiren sınır indeksleri — tek başına referans alınmamalı.
KARARSIZ_SINIR: list[int] = [1, 17]

TOPLAM_NOKTA: int = 106


# ══════════════════════════════════════════════════════════════════════════
#  FAZ 1 — Bölgeleme · göz kutusu · göz açıklığı
#
#  Buradaki her eşik ÖLÇÜLDÜ, seçilmedi. Ölçüm kaydı ilgili sabitin yanında.
#  Bağımlılık: yalnız numpy (zaten `eye_tracker`'ın yığınında var).
# ══════════════════════════════════════════════════════════════════════════

#: Göz KAPALI eşiği — `goz_acikligi()` bunun altındaysa göz kapalı sayılır.
#: Ölçüldü (2026-08-03, 22 kare, geliştiricinin webcam'i): açık gözde 0.284–0.428
#: (medyan 0.34), gerçekten kapalı iki karede 0.094–0.113. İki küme arasında
#: ~2.5 kat boşluk var; eşik ortadan biraz aşağıya kondu.
#: ⚠️ Tek kişide ölçüldü. Başka bir yüzde kayarsa buradan ayarlanır.
#: 2026-08-15 doğrulaması: 6 farklı yüzde (StyleGAN2 demo seti) poz düzeltmeli
#: açık-göz değerleri **0.268–0.396** çıktı — eşik hâlâ kümenin epey altında.
GOZ_KAPALI_ESIGI: float = 0.18

#: Poz düzeltmesinde açıların kırpıldığı sınır. Ötesinde `cos` hızla küçülüp
#: düzeltmeyi patlatır; ayrıca o açılarda göz zaten büyük ölçüde kapanmış
#: görünür ve landmark modeli de güvenilirliğini yitirir (aşağıdaki nota bak).
POZ_TAVANI_DERECE: float = 50.0


@dataclass
class YuzBolgeleri:
    """`bolgele()` çıktısı — bir karedeki yüzün ÜST/ALT ayrımı ve referansları."""

    ust: list[int]           #: ÜST bölgeye düşen 106-indeksleri (gözler/kaşlar/burun sırtı)
    alt: list[int]           #: ALT bölgeye düşen indeksler (burun tabanı/ağız/çene)
    bolme_noktasi: tuple[float, float]   #: burun ucunun piksel konumu (çizginin geçtiği yer)
    eksen: tuple[float, float]           #: yüzün KENDİ dikey ekseni (birim vektör)
    bolme_y_norm: float      #: burun ucunun bbox içindeki normalize y'si (0=üst, 1=alt)


def _yuz_ekseni(landmarks: np.ndarray) -> np.ndarray:
    """Yüzün kendi dikey ekseni: göz-ortası → ağız-ortası, birim vektör.

    Neden bbox'ın dikeyi DEĞİL: kafa yana yatınca (roll) yatay bir bölme çizgisi
    yüzü yamuk keser — bir gözü ALT'a, bir ağız köşesini ÜST'e atabilir. Yüzün
    kendi ekseni roll'dan etkilenmez.
    """
    goz_orta = landmarks[SAG_GOZ_MERKEZ + SOL_GOZ_MERKEZ].mean(axis=0)
    agiz_orta = landmarks[AGIZ].mean(axis=0)
    v = agiz_orta - goz_orta
    n = float(np.linalg.norm(v))
    if n < 1e-6:                      # dejenere kare — dikeye düş
        return np.array([0.0, 1.0])
    return v / n


def bolgele(landmarks, bbox=None) -> YuzBolgeleri:
    """Yüzü burun ucundan ÜST/ALT diye ikiye ayırır (geliştiricinin isteği, plan §3 FAZ 1).

    Bölme çizgisi **sabit bir oran değil**: her karede burun ucunun (`BURUN_UCU`)
    yüz ekseni üzerindeki izdüşümü eşik olur. Plan bu değeri bir test karesinde
    0.67 ölçmüştü ama sabitlemedi — poza göre değişiyor, her karede yeniden hesaplanır.

    landmarks: (106, 2) dizi · bbox: (x1, y1, x2, y2) — yalnız `bolme_y_norm` için.
    """
    L = np.asarray(landmarks, dtype=float)
    if L.shape[0] != TOPLAM_NOKTA:
        raise ValueError(f"106 nokta bekleniyor, {L.shape[0]} geldi")

    eksen = _yuz_ekseni(L)
    izdusum = L @ eksen
    # Eşik izdüşüm dizisinin KENDİSİNDEN okunuyor. `float(L[BURUN_UCU] @ eksen)`
    # yazılırsa aynı sayı iki farklı kod yolundan (matris çarpımı ↔ tek nokta
    # çarpımı) hesaplanır ve son bitleri ayrışabilir → bölme noktası taraf değiştirir.
    esik = float(izdusum[BURUN_UCU])

    # ⚠️ Bölme noktasının KENDİSİ çizginin tam üstünde durur: `izdusum[86] == esik`
    #    kayan nokta gürültüsüyle bir o yana bir bu yana düşüyordu (roll testi
    #    yakaladı — yüz 25° döndürülünce yalnız L[86] taraf değiştiriyordu).
    #    Plan bunu zaten tanımlamış: *"ALT bölge (burun ucu ve altı)"* → ALT.
    ust = [i for i in range(TOPLAM_NOKTA) if i != BURUN_UCU and izdusum[i] < esik]
    alt = [i for i in range(TOPLAM_NOKTA) if i == BURUN_UCU or izdusum[i] >= esik]

    if bbox is not None:
        y1, y2 = float(bbox[1]), float(bbox[3])
        y_norm = (float(L[BURUN_UCU][1]) - y1) / max(y2 - y1, 1e-6)
    else:
        y_norm = float("nan")

    return YuzBolgeleri(
        ust=ust,
        alt=alt,
        bolme_noktasi=(float(L[BURUN_UCU][0]), float(L[BURUN_UCU][1])),
        eksen=(float(eksen[0]), float(eksen[1])),
        bolme_y_norm=y_norm,
    )


def goz_kutusu(landmarks, taraf: str, pay: float = 0.35) -> tuple[int, int, int, int]:
    """Tek gözün kırpma kutusu — GERÇEK göz kapağı noktalarından.

    Bugüne kadar göz bölgesi diye elde yalnız `kps[0]`/`kps[1]` (tek merkez nokta)
    vardı; kutu ancak tahmini bir yarıçapla çizilebilirdi. Artık kümenin kendi
    sınırları kullanılıyor → iris tespiti (FAZ 2) için zemin.

    `pay`: kutunun her yöne genişletme oranı (göz kapağı + kirpik payı).
    Döndürür: (x1, y1, x2, y2) tam sayı piksel.
    """
    idx = {"sag": SAG_GOZ, "sol": SOL_GOZ}.get(taraf)
    if idx is None:
        raise ValueError("taraf 'sag' veya 'sol' olmalı")  # i18n-istisna: programlama hatası (geçersiz argüman)
    P = np.asarray(landmarks, dtype=float)[idx]
    x1, y1 = P.min(axis=0)
    x2, y2 = P.max(axis=0)
    gx, gy = (x2 - x1) * pay, (y2 - y1) * pay
    # ⚠️ Göz kapalıyken yükseklik ~0'a çöker; dikey payın tabanı yatay boydan alınır,
    #    yoksa kapalı gözde kutu bir çizgiye dönüşür ve kırpma boş görüntü verir.
    gy = max(gy, (x2 - x1) * 0.20)
    return int(x1 - gx), int(y1 - gy), int(x2 + gx), int(y2 + gy)


def poz_duzeltme_carpani(yaw: float | None, pitch: float | None) -> float:
    """EAR'ı poz kısaltmasından arındıran çarpan (yaw/pitch yoksa 1.0).

    ⚠️ Bu düzeltme **ölçümle geldi, tahminle değil** (2026-08-15). Kusur şuydu:
    kafa yana döndükçe göz KÖŞE mesafesi kısalır (yatay kısalma), kirpik
    yayılımı ise kısalmaz → bölüm büyür, yani **neredeyse kapalı göz "açık"
    okunur**. Wiki'deki *"aşırı pozlarda 0.22–0.36"* şikâyetinin geometrik
    karşılığı budur.

    Ölçüm (`backend/scripts/goz_acikligi_olc.py`, 8 yüz × 6 poz, gerçek
    algılama): aynı yüzün EAR'ı poz değiştikçe ortalama **0.059** geziniyordu;
    düzeltmeden sonra **0.038** — sapmanın %36'sı silindi (7 yüz düzeldi,
    1'i kıpırdamadı: o karede solvePnP yaw'ı küçük çıkıyor, düzeltecek bir şey
    görmüyor). Artakalan sapma dürüstçe duruyor: düzlem döndürmesi gerçek kafa
    dönüşünün yaklaşığı ve landmark modelinin kendi hatası da içeride.

    Pitch ters yönde çalışır (yukarı/aşağı bakışta kirpik yayılımı kısalır,
    köşe mesafesi kısalmaz) → biri çarpan, öbürü bölen.
    """
    if yaw is None and pitch is None:
        return 1.0
    tavan = POZ_TAVANI_DERECE
    y = math.radians(max(-tavan, min(tavan, float(yaw or 0.0))))
    p = math.radians(max(-tavan, min(tavan, float(pitch or 0.0))))
    return math.cos(y) / max(math.cos(math.radians(tavan)), math.cos(p))


def goz_acikligi(landmarks, taraf: str,
                 yaw: float | None = None, pitch: float | None = None) -> float:
    """Göz açıklık oranı (EAR benzeri) — 0 = tamamen kapalı.

    Yöntem: gözün KENDİ köşe ekseni referans alınır (`*_GOZ_KOSE`), tüm göz
    noktaları o eksene DİK yönde izdüşürülür, yayılım köşeler arası mesafeye
    bölünür. Böylece ölçüm kafanın yana yatmasından (roll) ve yüzün kameraya
    uzaklığından bağımsız kalır.

    `yaw`/`pitch` verilirse (derece, `gaze.kafa_acisi()` çıktısı) sonuç poz
    kısaltmasından da arındırılır → `poz_duzeltme_carpani`. Verilmezse davranış
    eskisiyle birebir aynıdır; çağıranı bozmaz ama **düzeltmesiz değer aşırı
    pozda yanıltır**, elde açı varsa geçilmeli.

    Klasik EAR üst/lower göz kapağı noktalarını ayrı ayrı bilmeyi ister; 106
    haritasında iç/dış kapak ayrımı HENÜZ YAPILMADI (FAZ 0 dürüstlük notu),
    bu yüzden ayrım gerektirmeyen "dik yayılım" biçimi seçildi.

    ⚠️ Ölçülüp ELENEN hipotez (2026-08-15): kusurun kaynağı `SAG_GOZ`/`SOL_GOZ`
    kümesindeki 75/81 sanılmıştı (kapak konturunun dışındalar — `gaze.KAPAK_*`
    onları bu yüzden dışlıyor). Gerçek yüzlerde ölçüldü: ikisinin köşe eksenine
    dik izdüşümü ±1 px, yani yayılıma **hiç dokunmuyorlar** (kapak-only yayılım
    tam kümeyle birebir aynı çıktı). Kümeyi daraltmak bu kusuru çözmezdi.
    """
    idx = {"sag": SAG_GOZ, "sol": SOL_GOZ}.get(taraf)
    kose = {"sag": SAG_GOZ_KOSE, "sol": SOL_GOZ_KOSE}.get(taraf)
    if idx is None:
        raise ValueError("taraf 'sag' veya 'sol' olmalı")  # i18n-istisna: programlama hatası (geçersiz argüman)
    L = np.asarray(landmarks, dtype=float)
    a, b = L[kose[0]], L[kose[1]]
    eksen = b - a
    boy = float(np.linalg.norm(eksen))
    if boy < 1e-6:
        return 0.0
    dik = np.array([-eksen[1], eksen[0]]) / boy
    pr = (L[idx] - a) @ dik
    return float((pr.max() - pr.min()) / boy) * poz_duzeltme_carpani(yaw, pitch)


def gozler_acik_mi(landmarks, esik: float = GOZ_KAPALI_ESIGI,
                   yaw: float | None = None, pitch: float | None = None) -> bool:
    """İki gözden EN AZ BİRİ açıksa True.

    Neden "en az biri": tek göz kırpma (wink) ya da tek gözün kadraj/saç yüzünden
    bozuk ölçülmesi, takibi tamamen susturmamalı. İkisi birden kapalıysa yayın
    durur — bugünkü kod kapalı gözde bile son konumu yayınlamaya devam ediyordu.

    `yaw`/`pitch` (derece) verilirse ölçüm poz kısaltmasından arındırılır.
    """
    return max(goz_acikligi(landmarks, "sag", yaw, pitch),
               goz_acikligi(landmarks, "sol", yaw, pitch)) >= esik


# ── ÜST/ALT kararlılığı — 22 gerçek karede ölçüldü (2026-08-03) ─────────────
#
# `bolgele()` bölmeyi GEOMETRİK yapar (burun ucundan geçen çizgi), organ
# listesinden değil. Sonuç: bazı noktalar her pozda aynı tarafta kalır, bazıları
# kafa yukarı/aşağı bakınca taraf değiştirir. Bu bir kusur değil, çizginin
# tanımının doğal sonucu — ama BİLİNMEDEN kullanılırsa kusura dönüşür:
# "burun tabanı hep ALT'tadır" varsayan bir kod, kafa yukarı bakınca kırılır.
#
# Ölçüm: yaw −47°…+38°, pitch −13,5°…+19° arası 22 kare.

#: 22/22 karede ÜST'te kalan indeksler (gözler · kaşlar · burun sırtı · şakaklar).
SABIT_UST: list[int] = sorted(
    SAG_GOZ + SOL_GOZ + SAG_KAS + SOL_KAS + [72, 73, 74] + [1, 9, 17, 25]
)

#: 22/22 karede ALT'ta kalan indeksler (ağız · burun tabanının alt 7'si · çene yayı).
SABIT_ALT: list[int] = sorted(
    AGIZ + [77, 78, 79, 80, 83, 84, 85] + [BURUN_UCU]
    + [0, 2, 3, 4, 5, 6, 7, 8, 14, 15, 16, 18, 19, 20, 21, 22, 23, 24, 30, 31, 32]
)

#: Poza göre taraf değiştiren indeksler → yanlarındaki sayı "22 karenin kaçında ÜST".
#: 76/82 = burun kanadının ÜST kenarı (burun ucunun hemen üstünde durur).
#: 10-13 / 26-29 = yanak-çene geçişi (kafa yukarı bakınca ALT'a iner).
#: Bunlara "hep şu taraftadır" diye yaslanan kod yazma.
POZA_BAGLI: dict[int, int] = {
    76: 18, 82: 18,
    10: 20, 11: 18, 12: 17, 13: 5,
    26: 20, 27: 18, 28: 16, 29: 2,
}
