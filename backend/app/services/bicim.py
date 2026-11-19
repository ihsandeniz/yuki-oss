"""bicim.py — dile duyarlı biçimlendirme: tarih · sayı · para · başlık.

NEDEN VAR (2026-09-18, FAZ 0):
Global/i18n taraması bu depoda **merkezî bir biçimlendirici olmadığını** ölçtü:
`Intl.*` 0 çağrı · Python `setlocale` 0 · `casefold()` 0 · ortak `formatDate()` yok.
Sonuç: 26 `toLocale*String` + 148 `toFixed` + 23 `strftime` çağrısı **kendi yerinde**
biçimlendiriyor ve TR ay/gün adı **6 ayrı kopya** halinde duruyor.

Bu modül o dağınıklığın panzehiri değil **tohumu**: FAZ 0'da yalnız iki canlı arıza
(A1 sabah brifingi · A5 bütçe özeti) için açıldı. FAZ 5'te kalan çağrılar buraya bağlanacak.

🔑 TEK KAYNAK KURALI: ay ve gün adları **burada** durur. Yeni bir yere kopyalama —
kopyalanan tablo bayatlar ve sessizce ayrışır (bu depoda `characters.css` ile
`personas.py` arasında zaten yaşandı).

⚠️ Henüz buraya TAŞINMAYANLAR (FAZ 5'in işi, bilerek bırakıldı):
  - `app/services/tools/system.py:11-13` `_TR_DAYS` / `_TR_MONTHS`
  - `frontend/planner.html` — 3 ay dizisi + 3 gün dizisi (ikisi farklı indeks tabanlı)
"""
from __future__ import annotations

from datetime import date, datetime

VARSAYILAN_DIL = "tr"

# Ay adları — 1..12 (indeks 0 boş bırakıldı ki `AY_ADLARI[lang][d.month]` doğrudan çalışsın)
AY_ADLARI: dict[str, tuple[str, ...]] = {
    "tr": ("", "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
           "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"),
    "ja": ("", "1月", "2月", "3月", "4月", "5月", "6月",
           "7月", "8月", "9月", "10月", "11月", "12月"),
}

# Gün adları — Python `weekday()` sırası: 0 = Pazartesi
# ⚠️ Bu taban `date.weekday()` ile uyumludur, JS `getDay()` (0 = Pazar) ile DEĞİL.
GUN_ADLARI: dict[str, tuple[str, ...]] = {
    "tr": ("Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"),
    "ja": ("月曜日", "火曜日", "水曜日", "木曜日", "金曜日", "土曜日", "日曜日"),
}

# Binlik / ondalık ayracı. TR: 1.234.567,89 · JA (ve EN): 1,234,567.89
_AYRAC: dict[str, tuple[str, str]] = {
    "tr": (".", ","),
    "ja": (",", "."),
}

# Para simgesi. ⚠️ Bütçe kaydında `currency` alanı YOK (planner.html:1272) —
# yani bu bugün "kullanıcının parası" değil "TL" varsayımıdır. Şema alanı FAZ 5'in işi.
_PARA_SIMGESI: dict[str, str] = {
    "tr": "₺",
    "ja": "¥",
}

# Türkçe'ye özgü harf çiftleri. Python'un varsayılan case dönüşümü Unicode (İngilizce)
# haritasıdır: "İ".lower() → "i̇" (i + U+0307, ÜÇ kod noktası) ve "I".lower() → "i".
# İkisi de Türkçe'de yanlıştır ve karşılaştırmayı sessizce bozar.
_TR_KUCUK = str.maketrans({"I": "ı", "İ": "i"})
_TR_BUYUK = str.maketrans({"ı": "I", "i": "İ"})


def _dil(lang: str | None) -> str:
    """Verilen dili doğrula; verilmediyse aktif asistan dilini al."""
    if lang:
        kod = lang.lower().strip()
        if kod in AY_ADLARI:
            return kod
    if lang is None:
        try:
            from app.config import get_language  # lazy: döngüsel import olmasın
            kod = get_language()
            if kod in AY_ADLARI:
                return kod
        except Exception:
            pass
    return VARSAYILAN_DIL


# --------------------------------------------------------------------------- #
# Büyük/küçük harf — Türkçe i/I çifti
# --------------------------------------------------------------------------- #

def kucult(metin: str, lang: str | None = None) -> str:
    """Dile duyarlı küçük harf. TR'de 'I'→'ı', 'İ'→'i'."""
    if _dil(lang) == "tr":
        return (metin or "").translate(_TR_KUCUK).lower()
    return (metin or "").lower()


def buyult(metin: str, lang: str | None = None) -> str:
    """Dile duyarlı büyük harf. TR'de 'ı'→'I', 'i'→'İ'."""
    if _dil(lang) == "tr":
        return (metin or "").translate(_TR_BUYUK).upper()
    return (metin or "").upper()


def baslik(metin: str, lang: str | None = None) -> str:
    """Her kelimenin ilk harfi büyük — dile duyarlı.

    Python'un `str.title()`'ı TR'de bozar: "işler".title() → "Işler" (doğrusu "İşler").
    Bu, kullanıcının verdiği liste adı diske KALICI yazıldığı için görünür bir hatadır.
    """
    kod = _dil(lang)
    parcalar = []
    for kelime in (metin or "").split(" "):
        if not kelime:
            parcalar.append(kelime)
            continue
        parcalar.append(buyult(kelime[0], kod) + kucult(kelime[1:], kod))
    return " ".join(parcalar)


# --------------------------------------------------------------------------- #
# Tarih
# --------------------------------------------------------------------------- #

def ay_adi(d: date | datetime, lang: str | None = None) -> str:
    return AY_ADLARI[_dil(lang)][d.month]


def gun_adi(d: date | datetime, lang: str | None = None) -> str:
    return GUN_ADLARI[_dil(lang)][d.weekday()]


def uzun_tarih(d: date | datetime, lang: str | None = None) -> str:
    """'18 Eylül 2026' · ja: '2026年9月18日'.

    `strftime('%d %B %Y')` KULLANILMAZ: `%B` işletim sisteminin locale'ine bağlıdır ve
    bu projede hiç `setlocale` çağrılmıyor → Türkçe cümlenin içine 'September' basıyordu.
    """
    kod = _dil(lang)
    if kod == "ja":
        return f"{d.year}年{d.month}月{d.day}日"
    return f"{d.day:02d} {AY_ADLARI[kod][d.month]} {d.year}"


# --------------------------------------------------------------------------- #
# Sayı ve para
# --------------------------------------------------------------------------- #

def sayi(deger: float | int, lang: str | None = None, ondalik: int = 0) -> str:
    """Binlik/ondalık ayracı dile göre. TR: '42.500' · JA/EN: '42,500'."""
    kod = _dil(lang)
    binlik, ondalik_ayrac = _AYRAC.get(kod, _AYRAC["tr"])
    ham = f"{deger:,.{ondalik}f}"          # Python varsayılanı ABD biçimi: 42,500.00
    # İki adımda çevir, yoksa ilk değişim ikincisini yer.
    return ham.replace(",", "\x00").replace(".", ondalik_ayrac).replace("\x00", binlik)


def para(deger: float | int, lang: str | None = None, ondalik: int = 0) -> str:
    """Simge + dile uygun sayı. TR: '₺42.500'."""
    kod = _dil(lang)
    return f"{_PARA_SIMGESI.get(kod, '₺')}{sayi(deger, kod, ondalik)}"
