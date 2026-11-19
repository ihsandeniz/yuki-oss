"""HARİTA › GÜNDEM kümeleme: aynı olayı anlatan başlıkları tek satırda toplar.

Haber akışında aynı olay farklı kaynaklardan 3-4 kez geçer ve kısa listeyi doldurur. Bu modül
başlıkları ağ ve model kullanmadan gruplar; her grup tek satır olur, kaç kaynağın verdiği sayılır.

Yöntem:
  · "Başlık - Kaynak" kalıbında kaynak ayrılır; benzerliğe girmez, yalnız sayılır
  · başlık Türkçe kurallarıyla küçültülür, kesme işaretinden sonraki ek atılır, her kelimenin
    ilk `KOK_UZUNLUK` harfi kök sayılır (ek yığılan dilde kaba ama yeterli gövdeleme)
  · iki başlığın benzerliği, ortak köklerin ağırlığına dayanan Dice oranıdır; ağırlık aynı
    akıştan hesaplanan idf'dir (akışta sık geçen kök az değerlidir)
  · birleşmek için hem oran eşiği hem `EN_AZ_ORTAK` ortak kök gerekir: tek bir sık kelime
    ("dolar") iki ayrı haberi birleştiremez
  · akış sırası korunur; grubun temsilcisi gruba giren ilk başlıktır

Bayrak: `GUNDEM_KUME` (varsayılan açık; `0` ham listeyi geri getirir). Çağıran taraf hata
durumunda ham listeye düşer — kümeleme haberi asla kaybettirmez.
"""
from __future__ import annotations

import math
import os
import re
from collections import Counter

ESIK = 0.5
EN_AZ_ORTAK = 3
KOK_UZUNLUK = 5
# idf'nin taban havuzu: 3-5 başlıklık kısa akışta ortak her kök "sık" görünüp değersizleşir
# ve aynı olay bile birleşmez. Havuz en az bu kadar başlık varmış gibi sayılır.
HAVUZ_TABAN = 20

# Olay ayırt etmeyen kelimeler (tam kelime ya da kök hâliyle eşleşir).
_ETKISIZ = frozenset({
    # Türkçe bağlaç / edat / soru
    "ve", "ile", "ya", "veya", "ama", "fakat", "ancak", "için", "gibi", "kadar", "göre",
    "bir", "bu", "şu", "o", "da", "de", "ki", "mi", "mı", "mu", "mü", "ne", "nasıl",
    "neden", "niye", "kaç", "hangi", "her", "tüm", "bütün", "daha", "çok", "az", "en",
    "ise", "olan", "oldu", "olduğ", "olarak", "sonra", "önce", "kadar",
    # haber kalıpları
    "son", "dakik", "flaş", "haber", "canlı", "işte", "yeni", "bugü", "yarın", "dün",
    "açıkl", "belli", "ortay",
    # İngilizce akış için asgari liste
    "the", "and", "for", "with", "from", "that", "this", "after", "over", "into", "news",
})

_KAYNAK = re.compile(r"^(?P<b>.*\S)\s+[-–—]\s+(?P<k>[^-–—]{2,40})$")
_HARF = "0-9a-zçğıöşüâîû"
_KELIME = re.compile(f"[{_HARF}]+")
_KESME = re.compile(f"['’`´‘][{_HARF}]*")


def acik() -> bool:
    return os.getenv("GUNDEM_KUME", "1").strip().lower() not in ("0", "false", "hayir", "kapali", "off")


def tr_kucuk(s: str) -> str:
    """Türkçe küçük harf: 'I' → 'ı', 'İ' → 'i' (str.lower ikisini de 'i' yapar)."""
    return s.replace("I", "ı").replace("İ", "i").lower()


def baslik_ayir(ham) -> tuple[str, str]:
    """'Başlık - Kaynak' → (başlık, kaynak); kaynak eki yoksa ('…', '')."""
    t = " ".join(str(ham or "").split())
    m = _KAYNAK.match(t)
    if m is None:
        return t, ""
    return m.group("b"), m.group("k").strip()


def kokler(baslik: str) -> set[str]:
    sonuc: set[str] = set()
    for kelime in _KELIME.findall(_KESME.sub("", tr_kucuk(baslik))):
        if len(kelime) < 3 and not kelime.isdigit():
            continue
        kok = kelime[:KOK_UZUNLUK]
        if kelime in _ETKISIZ or kok in _ETKISIZ:
            continue
        sonuc.add(kok)
    return sonuc


def kumele(basliklar: list, esik: float = ESIK, en_az_ortak: int = EN_AZ_ORTAK) -> list[dict]:
    """Ham başlık listesi → grup listesi (akış sırası korunur).

    Her grup: {"title": temsilci ham başlık, "basliklar": [...], "kaynaklar": [...],
               "kaynak_sayisi": max(1, kaynak sayısı)}
    """
    parcalar = []
    for ham in basliklar:
        govde, kaynak = baslik_ayir(ham)
        parcalar.append((ham, kaynak, kokler(govde)))

    havuz = max(len(parcalar), HAVUZ_TABAN)
    gecis = Counter(k for _, _, ks in parcalar for k in ks)
    agirlik = {k: math.log((havuz + 1) / (n + 0.5)) for k, n in gecis.items()}

    def toplam(ks) -> float:
        return sum(agirlik[k] for k in ks)

    gruplar: list[dict] = []
    ic: list[tuple[set[str], float]] = []   # gruba paralel: (temsilcinin kökleri, ağırlığı)
    for ham, kaynak, ks in parcalar:
        a = toplam(ks)
        yer = None
        for i, (gk, ga) in enumerate(ic):
            ortak = ks & gk
            if len(ortak) < en_az_ortak or a + ga <= 0:
                continue
            # Dice (2·ortak / toplam), kısa başlığa göre oran (ortak / min) DEĞİL: kısa başlık
            # uzun ve ilgisiz bir başlığın alt kümesi olunca min-oran onu yapıştırır.
            if 2 * toplam(ortak) / (a + ga) >= esik:
                yer = i
                break
        if yer is None:
            gruplar.append({"title": ham, "basliklar": [ham], "kaynaklar": [kaynak] if kaynak else []})
            ic.append((ks, a))
            continue
        g = gruplar[yer]
        g["basliklar"].append(ham)
        if kaynak and kaynak not in g["kaynaklar"]:
            g["kaynaklar"].append(kaynak)
    for g in gruplar:
        g["kaynak_sayisi"] = max(1, len(g["kaynaklar"]))
    return gruplar


def isle(ogeler: list[dict]) -> list[dict]:
    """Uç için: [{"title": …}] → grup temsilcileri (+ kaynak_sayisi, kaynaklar).

    Bayrak kapalıysa ya da kümeleme hata verirse girdi değişmeden döner."""
    if not acik():
        return ogeler
    try:
        gruplar = kumele([o.get("title") for o in ogeler])
    except Exception:
        return ogeler
    return [{"title": g["title"], "kaynak_sayisi": g["kaynak_sayisi"], "kaynaklar": g["kaynaklar"]}
            for g in gruplar]
