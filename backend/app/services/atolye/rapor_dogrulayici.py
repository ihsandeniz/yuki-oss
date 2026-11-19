"""Rapor doğrulayıcısı — araştırma türü (Yuki Atölye v2, Faz 2). LLM ÇAĞIRMAZ, deterministik.

Kurallar (FAZ2-TASARIM § 4):
  D1 RAPOR.md var, boş değil, ≤ 200 KB, UTF-8                                  → hata
  D2 her iddia birimi (paragraf · liste maddesi · tablo satırı; başlık, kod bloğu,
     `## Kaynaklar` ve 6 kelimeden kısa etiket satırları hariç) ≥ 1 [K|W|A<n>] taşır → hata
  D3 her işaret defterde var; K/W gerçekten okunmuş (anlık görüntü dosyası var)  → hata
     yalnız [A] (arama özeti) ile desteklenen birim > %30                          → uyarı
  D4 `## Kaynaklar` var; gövdede kullanılan her id orada; oradaki URL/yol defterle birebir;
     bölümde kimlik/URL taşımayan satır yok (iddia oraya saklanamaz)               → hata
  D5 rapordaki her http(s) bağlantısı defterde (uydurma URL yok)                 → hata
  D6 tırnak içindeki ≥ 20 krk alıntı, aynı birimdeki K/W kaynaklarından birinin
     anlık görüntüsünde geçer (boşluk/harf/tırnak normalize)                      → hata
  D7 okunup kullanılmayan kaynak · tek alan adı · < 3 farklı kaynak               → uyarı
  D8 çalışma alanında .md dışı dosya                                            → uyarı
🔴 Ölçmediği: iddianın kaynakta ANLAMCA desteklendiği (F2 a: model denetimi yok).
"""

from __future__ import annotations

import hashlib
import json
import re
import time
import unicodedata
from pathlib import Path
from urllib.parse import urlsplit

from app.services.atolye import alan, kaynak
from app.services.atolye.dogrulayici import parmak_izi as _alan_izi

RAPOR = "RAPOR.md"
SONUC_DOSYASI = "dogrulama.json"
RAPOR_AZAMI = 200_000
KISA_BIRIM_KELIME = 6
ALINTI_KRK = 20
A_ORANI = 0.30

_ISARET = re.compile(r"\[((?:[KWA]\d+)(?:\s*[,;]\s*[KWA]\d+)*)\]")
_ID = re.compile(r"[KWA]\d+")
_URL = re.compile(r"https?://[^\s<>\"'`)\]}|]+", re.I)
_ALINTI = re.compile(r"[\"“”«]([^\"“”«»]{%d,})[\"“”»]" % ALINTI_KRK)
_TABLO_AYIRICI = re.compile(r"^\|?\s*:?-{2,}")


def _norm(metin: str) -> str:
    m = unicodedata.normalize("NFKC", metin).casefold()
    for a, b in (("’", "'"), ("‘", "'"), ("“", '"'), ("”", '"'), ("«", '"'), ("»", '"')):
        m = m.replace(a, b)
    return " ".join(m.split())


def parmak_izi(kok: Path) -> str:
    """Çalışma alanı + kaynak defteri — yeni okuma yapılınca eski hüküm bayatlar."""
    h = hashlib.sha256(_alan_izi(kok).encode())
    try:
        h.update((kok / alan.AYRILMIS / kaynak.KAYIT).read_bytes())
    except OSError:
        pass
    return h.hexdigest()


def birimler(metin: str) -> tuple[list[str], list[str]]:
    """(iddia birimleri, Kaynaklar bölümü satırları)."""
    out: list[str] = []
    kaynaklar: list[str] = []
    paragraf: list[str] = []
    kodda = kaynak_bolumu = False
    tablo_baslik_bekleniyor = True

    def _bosalt():
        if paragraf:
            out.append(" ".join(paragraf))
            paragraf.clear()

    for ham in metin.splitlines():
        satir = ham.strip()
        if satir.startswith("```") or satir.startswith("~~~"):
            _bosalt()
            kodda = not kodda
            continue
        if kodda:
            continue
        if satir.startswith("#"):
            _bosalt()
            baslik = satir.lstrip("#").strip().casefold()
            kaynak_bolumu = satir.startswith("## ") and baslik.startswith("kaynak")
            tablo_baslik_bekleniyor = True
            continue
        if kaynak_bolumu:
            if satir:
                kaynaklar.append(satir)
            continue
        if not satir:
            _bosalt()
            tablo_baslik_bekleniyor = True
            continue
        if satir.startswith("|"):
            _bosalt()
            if _TABLO_AYIRICI.match(satir):
                continue
            if tablo_baslik_bekleniyor:
                tablo_baslik_bekleniyor = False
                continue                       # tablonun başlık satırı iddia değil
            out.append(satir)
            continue
        tablo_baslik_bekleniyor = True
        if re.match(r"^([-*+]|\d+[.)])\s+", satir):
            _bosalt()
            out.append(re.sub(r"^([-*+]|\d+[.)])\s+", "", satir))
            continue
        paragraf.append(satir.lstrip("> ").strip())
    _bosalt()
    iddia = [b for b in out if len(_ISARET.sub("", b).split()) >= KISA_BIRIM_KELIME]
    return iddia, kaynaklar


def _idler(metin: str) -> list[str]:
    return [i for grup in _ISARET.findall(metin) for i in _ID.findall(grup)]


def dogrula(kok: Path) -> dict:
    t0 = time.monotonic()
    hatalar: list[str] = []
    uyarilar: list[str] = []
    olcum: dict = {}
    yol = kok / RAPOR
    metin = ""
    try:
        if yol.is_symlink():
            raise OSError("sembolik bağ")
        veri = yol.read_bytes()
        if len(veri) > RAPOR_AZAMI:
            hatalar.append(f"D1: {RAPOR} {RAPOR_AZAMI} bayttan büyük")
        metin = veri.decode("utf-8")
        if not metin.strip():
            hatalar.append(f"D1: {RAPOR} boş")
    except FileNotFoundError:
        hatalar.append(f"D1: {RAPOR} yok — raporu çalışma alanının köküne {RAPOR} adıyla yaz")
    except UnicodeDecodeError:
        hatalar.append(f"D1: {RAPOR} UTF-8 değil")
    except OSError as e:
        hatalar.append(f"D1: {RAPOR} okunamadı ({e})")

    defter = kaynak.defter(kok)
    kayit = {k["id"]: k for k in defter if k.get("id")}
    okunmus = {kid for kid, k in kayit.items() if k.get("tip") == "web"
               and kaynak.anlik_yolu(kok, kid).is_file()}
    bilinen_url = set()
    for k in defter:
        for alanadi in ("url", "istenen"):
            if k.get(alanadi):
                bilinen_url.add(kaynak.normal_url(k[alanadi]))

    if metin.strip():
        iddia, kaynak_satirlari = birimler(metin)
        kullanilan: set[str] = set()
        yalniz_a = 0
        for b in iddia:
            ids = _idler(b)
            if not ids:
                hatalar.append(f"D2: kaynaksız iddia: \"{b[:60]}…\"")
                continue
            kullanilan.update(ids)
            for i in ids:
                if i not in kayit:
                    hatalar.append(f"D3: [{i}] defterde yok (uydurma kaynak işareti)")
                elif i[0] in "KW" and i not in okunmus:
                    hatalar.append(f"D3: [{i}] okunmamış — önce kaynak_oku")
            if all(i.startswith("A") for i in ids):
                yalniz_a += 1
            # D6 — alıntı birebir mi
            kw = [i for i in ids if i in okunmus]
            for alinti in _ALINTI.findall(b):
                n = _norm(alinti)
                if not any(n in _norm(kaynak.anlik_yolu(kok, i).read_text(encoding="utf-8",
                                                                         errors="replace"))
                           for i in kw):
                    hatalar.append(f"D6: uydurma alıntı (kaynağında yok): \"{alinti[:60]}\"")
        if iddia and yalniz_a / len(iddia) > A_ORANI:
            uyarilar.append(f"D3: birimlerin %{round(100 * yalniz_a / len(iddia))}'i yalnız arama "
                            "özetine ([A]) dayanıyor — kaynağı okuyup [K] ver")
        # D4 — Kaynaklar bölümü
        if not kaynak_satirlari:
            hatalar.append("D4: '## Kaynaklar' bölümü yok ya da boş")
        else:
            listelenen: set[str] = set()
            for s in kaynak_satirlari:
                if not _ID.search(s) and not _URL.search(s):
                    # Kaynaklar bölümüne kaynaksız iddia saklanamasın (D2 bu bölümü saymaz)
                    hatalar.append(f"D4: Kaynaklar'da kaynak olmayan satır: \"{s[:60]}\"")
                    continue
                ids = _ID.findall(s.split("http")[0]) if "http" in s else _ID.findall(s)
                for i in ids:
                    listelenen.add(i)
                    k = kayit.get(i)
                    if k is None:
                        hatalar.append(f"D4: Kaynaklar'da [{i}] defterde yok")
                        continue
                    urller = {kaynak.normal_url(u.rstrip(".,;:")) for u in _URL.findall(s)}
                    beklenen = {kaynak.normal_url(k[a]) for a in ("url", "istenen") if k.get(a)}
                    if not urller & beklenen:
                        hatalar.append(f"D4: [{i}] URL'si defterle uyuşmuyor "
                                       f"(beklenen {k.get('url')})")
            for i in sorted(kullanilan - listelenen):
                if i in kayit:
                    hatalar.append(f"D4: [{i}] gövdede kullanılmış ama Kaynaklar'da yok")
        # D5 — uydurma URL
        for u in dict.fromkeys(_URL.findall(metin)):
            if kaynak.normal_url(u.rstrip(".,;:")) not in bilinen_url:
                hatalar.append(f"D5: uydurma bağlantı (defterde yok): {u[:100]}")
        # D7
        kullanilmayan = sorted(okunmus - kullanilan)
        if kullanilmayan:
            uyarilar.append("D7: okunup kullanılmayan kaynak: " + ", ".join(kullanilmayan[:8]))
        alanlar = {urlsplit(kayit[i]["url"]).hostname for i in kullanilan
                   if i in kayit and kayit[i].get("tip") in ("web", "arama") and kayit[i].get("url")}
        if len(alanlar) == 1:
            uyarilar.append("D7: rapor tek bir alan adına dayanıyor")
        if len(kullanilan & set(kayit)) < 3:
            uyarilar.append("D7: 3'ten az farklı kaynak kullanılmış")
        olcum = {"birim": len(iddia), "isaretli": len(iddia) - sum(
            1 for b in iddia if not _idler(b)), "kaynak": len(kullanilan & set(kayit)),
            "okunan": len(okunmus)}
    # D8
    disi = [d for d in alan._dosyalar(kok) if not d.endswith(".md")]
    if disi:
        uyarilar.append("D8: .md dışı dosya: " + ", ".join(disi[:5]))

    hatalar = list(dict.fromkeys(hatalar))
    sonuc = {"temiz": not hatalar, "hatalar": hatalar, "uyarilar": uyarilar, "olcum": olcum,
             "parmak_izi": parmak_izi(kok), "sure_sn": round(time.monotonic() - t0, 3),
             "zaman": time.strftime("%Y-%m-%d %H:%M:%S")}
    d = kok / alan.AYRILMIS
    if d.is_dir() and not d.is_symlink():
        (d / SONUC_DOSYASI).write_text(json.dumps(sonuc, ensure_ascii=False, indent=1),
                                       encoding="utf-8")
    return sonuc


def son_sonuc(kok: Path) -> dict | None:
    try:
        s = json.loads((kok / alan.AYRILMIS / SONUC_DOSYASI).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return s if s.get("parmak_izi") == parmak_izi(kok) else None


def metin(sonuc: dict) -> str:
    if sonuc["temiz"]:
        s = ["DOĞRULAMA TEMİZ — her iddiada okunmuş kaynak, uydurma URL/alıntı yok."]
        if sonuc["uyarilar"]:
            s.append("Uyarılar (isteğe bağlı): " + " · ".join(sonuc["uyarilar"][:5]))
        s.append("Şimdi araç çağırmadan kısa bir özet yaz; görev biter.")
        return "\n".join(s)
    s = [f"DOĞRULAMA KİRLİ — {len(sonuc['hatalar'])} hata. Düzelt, sonra yeniden rapor_bitir çağır:"]
    s += [f"- {h}" for h in sonuc["hatalar"][:20]]
    if sonuc["uyarilar"]:
        s.append("Uyarılar: " + " · ".join(sonuc["uyarilar"][:5]))
    return "\n".join(s)
