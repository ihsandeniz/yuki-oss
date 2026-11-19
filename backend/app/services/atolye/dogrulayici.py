"""Site doğrulayıcı — Yuki Atölye v2, Faz 1.

İki katman, ikisi de çalışma alanına SALT-OKUNUR bakar:
  1. Statik: `index.html` var mı · viewport/title/lang · dış kaynak (CDN, font, script —
     site türünde ağ yok) · kırık yerel bağlantı · SVG iyi biçimli, `viewBox`'lı, betiksiz.
  2. Ekran (Playwright, Chromium): önizleme işleyicisiyle (aynı CSP) geçici portta açılır,
     1440 ve 390 genişlikte: `pageerror` · konsol hatası · kırık istek · yatay taşma
     (taşan öğeler adıyla) · boş sayfa · küçük punto (uyarı). Önizleme kökeni dışındaki
     her istek iptal edilir ve sayılır. Ekran görüntüleri `.gorev/ekran/`'a yazılır
     (görsel kontrol bunları modele verir — `gorev.py`).

Hüküm `temiz` = hata yok (uyarılar hükmü bozmaz). Playwright yoksa ekran katmanı
"yapılamadı" uyarısıyla atlanır, statik hüküm geçerli kalır.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

from app.services.atolye import alan

logger = logging.getLogger(__name__)

GENISLIKLER = ((1440, 900), (390, 844))
EKRAN_AZAMI_YUKSEKLIK = 2400       # px — görsel kontrol için tam sayfa görüntü kırpılır
KUCUK_PUNTO = 12                   # px altı görünür metin → uyarı
SONUC_DOSYASI = "dogrulama.json"   # .gorev/ altında


def parmak_izi(kok: Path) -> str:
    """Çalışma alanının (görev kaydı hariç) içerik özeti — değişmediyse ölçüm yeniden koşmaz."""
    h = hashlib.sha256()
    for rel in alan._dosyalar(kok):
        p = kok / rel
        try:
            if p.is_symlink():
                continue
            h.update(rel.encode() + b"\0" + p.read_bytes() + b"\0")
        except OSError:
            continue
    return h.hexdigest()


# ── statik ────────────────────────────────────────────────────────────────
class _HtmlTarayici(HTMLParser):
    KAYNAK = {("script", "src"), ("img", "src"), ("source", "src"), ("source", "srcset"),
              ("img", "srcset"), ("iframe", "src"), ("embed", "src"), ("object", "data"),
              ("video", "src"), ("video", "poster"), ("audio", "src"), ("track", "src"),
              ("input", "src"), ("image", "href"), ("use", "href"), ("image", "xlink:href"),
              ("use", "xlink:href")}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.kaynaklar: list[tuple[str, str]] = []   # (etiket.öznitelik, değer)
        self.baglantilar: list[str] = []              # <a href>
        self.viewport = self.title_var = self.lang = False
        self._title_ic = False
        self.title_metin = ""
        self.stiller: list[str] = []
        self._stil_ic = False

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "html" and a.get("lang", "").strip():
            self.lang = True
        if tag == "meta" and a.get("name", "").lower() == "viewport":
            self.viewport = True
        if tag == "title":
            self.title_var, self._title_ic = True, True
        if tag == "style":
            self._stil_ic = True
        if tag == "link" and a.get("href"):
            rel = a.get("rel", "").lower()
            if any(r in rel for r in ("stylesheet", "icon", "preload", "modulepreload",
                                      "manifest", "prefetch", "preconnect", "dns-prefetch")):
                self.kaynaklar.append(("link.href", a["href"]))
        if tag == "a" and a.get("href"):
            self.baglantilar.append(a["href"])
        for k, v in a.items():
            if (tag, k) in self.KAYNAK and v:
                if k == "srcset":
                    for parca in v.split(","):
                        if parca.strip():
                            self.kaynaklar.append((f"{tag}.srcset", parca.strip().split()[0]))
                else:
                    self.kaynaklar.append((f"{tag}.{k}", v))
            if k == "style" and v:
                self.stiller.append(v)

    def handle_endtag(self, tag):
        if tag == "title":
            self._title_ic = False
        if tag == "style":
            self._stil_ic = False

    def handle_data(self, data):
        if self._title_ic:
            self.title_metin += data
        if self._stil_ic:
            self.stiller.append(data)


_CSS_URL = re.compile(r"""url\(\s*['"]?([^'")\s]+)['"]?\s*\)""", re.I)
_CSS_IMPORT = re.compile(r"""@import\s+(?:url\()?\s*['"]?([^'");\s]+)""", re.I)


def _dis_mi(url: str) -> bool:
    u = url.strip().lower()
    return u.startswith(("http:", "https:", "//", "ftp:", "ws:", "wss:"))


def _yerel_mi(url: str) -> bool:
    u = url.strip().lower()
    return bool(u) and not (_dis_mi(u) or u.startswith(("data:", "#", "mailto:", "tel:",
                                                         "javascript:", "about:", "blob:")))


def _css_kaynaklari(metin: str) -> list[str]:
    return _CSS_URL.findall(metin) + _CSS_IMPORT.findall(metin)


def _yerel_hedef(kok: Path, kaynak_dosya: str, url: str) -> str:
    yol = urlsplit(url).path
    if yol.startswith("/"):
        return yol.lstrip("/")
    taban = str(Path(kaynak_dosya).parent)
    return str(Path(taban) / yol) if taban != "." else yol


def statik(kok: Path) -> tuple[list[str], list[str]]:
    hatalar: list[str] = []
    uyarilar: list[str] = []
    dosyalar = alan._dosyalar(kok)
    if "index.html" not in dosyalar:
        return ["index.html yok — site ana dosyası çalışma alanının kökünde olmalı"], uyarilar

    def _var_mi(rel: str) -> bool:
        try:
            p = alan.guvenli_yol(kok, rel)
        except alan.AlanHatasi:
            return False
        return p.is_file()

    for rel in dosyalar:
        p = kok / rel
        uz = p.suffix.lower()
        if p.is_symlink():
            hatalar.append(f"{rel}: sembolik bağ")
            continue
        try:
            metin = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if uz in (".html", ".htm"):
            t = _HtmlTarayici()
            try:
                t.feed(metin)
            except Exception as e:     # HTMLParser çok hoşgörülü; yine de
                hatalar.append(f"{rel}: HTML ayrıştırılamadı ({e})")
                continue
            if rel == "index.html":
                if not t.viewport:
                    hatalar.append("index.html: <meta name=\"viewport\"> yok — telefonda küçülür")
                if not t.title_metin.strip():
                    hatalar.append("index.html: <title> boş ya da yok")
                if not t.lang:
                    uyarilar.append("index.html: <html lang=\"tr\"> yok")
            kaynaklar = list(t.kaynaklar)
            for stil in t.stiller:
                kaynaklar += [("css.url", u) for u in _css_kaynaklari(stil)]
            for ne, url in kaynaklar:
                if _dis_mi(url):
                    hatalar.append(f"{rel}: dış kaynak ({ne} → {url[:80]}) — site türünde ağ yok, "
                                   "dosyayı çalışma alanına koy ya da kaldır")
                elif _yerel_mi(url) and not _var_mi(_yerel_hedef(kok, rel, url)):
                    hatalar.append(f"{rel}: kırık bağlantı ({ne} → {url[:80]}) — dosya yok")
            for url in t.baglantilar:
                if _yerel_mi(url) and urlsplit(url).path and \
                        not _var_mi(_yerel_hedef(kok, rel, url)):
                    hatalar.append(f"{rel}: kırık sayfa bağlantısı (a.href → {url[:80]})")
        elif uz == ".css":
            for url in _css_kaynaklari(metin):
                if _dis_mi(url):
                    hatalar.append(f"{rel}: dış kaynak (css → {url[:80]}) — site türünde ağ yok")
                elif _yerel_mi(url) and not _var_mi(_yerel_hedef(kok, rel, url)):
                    hatalar.append(f"{rel}: kırık bağlantı (css → {url[:80]})")
        elif uz == ".svg":
            try:
                kokel = ET.fromstring(metin)
            except ET.ParseError as e:
                hatalar.append(f"{rel}: SVG bozuk XML ({e})")
                continue
            if not kokel.tag.endswith("svg"):
                hatalar.append(f"{rel}: kök öğe <svg> değil")
                continue
            if not kokel.get("viewBox"):
                hatalar.append(f"{rel}: viewBox yok — ölçeklenmez")
            for el in kokel.iter():
                ad = el.tag.rsplit("}", 1)[-1]
                if ad == "script":
                    hatalar.append(f"{rel}: SVG içinde <script> yasak")
                    break
                if any(k.lower().startswith("on") for k in el.attrib):
                    hatalar.append(f"{rel}: SVG içinde olay özniteliği (on…) yasak")
                    break
                for k, v in el.attrib.items():
                    if k.rsplit("}", 1)[-1] == "href" and _dis_mi(v):
                        hatalar.append(f"{rel}: SVG dış kaynak ({v[:80]})")
    return hatalar, uyarilar


# ── ekran ─────────────────────────────────────────────────────────────────
_TASMA_JS = """() => {
  const w = window.innerWidth, d = document.documentElement;
  const tasan = [];
  if (d.scrollWidth > w + 1) {
    for (const el of document.body.querySelectorAll('*')) {
      const r = el.getBoundingClientRect();
      if (r.width && r.right > w + 1) {
        const ad = el.tagName.toLowerCase() + (el.id ? '#' + el.id : '') +
          (typeof el.className === 'string' && el.className.trim()
            ? '.' + el.className.trim().split(/\\s+/).slice(0, 2).join('.') : '');
        tasan.push(ad + ' (sağ kenar ' + Math.round(r.right) + 'px)');
        if (tasan.length >= 4) break;
      }
    }
  }
  let kucuk = 0;
  const yuruyen = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  const gorulen = new Set();
  while (yuruyen.nextNode()) {
    const n = yuruyen.currentNode, el = n.parentElement;
    if (!el || gorulen.has(el) || !n.textContent.trim()) continue;
    gorulen.add(el);
    const cs = getComputedStyle(el), r = el.getBoundingClientRect();
    if (cs.visibility === 'hidden' || cs.display === 'none' || !r.width) continue;
    if (parseFloat(cs.fontSize) < %d) kucuk++;
  }
  return {scrollWidth: d.scrollWidth, genislik: w, tasan,
          metin: (document.body.innerText || '').trim().length, kucuk};
}""" % KUCUK_PUNTO


def ekran(kok: Path, tur: str, ad: str, ekran_dizini: Path | None = None
          ) -> tuple[list[str], list[str], dict]:
    """Playwright ölçümü. Döner: (hatalar, uyarılar, ölçümler)."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return [], ["ekran ölçümü yapılamadı (Playwright yok) — yalnız statik denetim"], {}
    from app.services.atolye.onizleme import OnizlemeSunucusu

    hatalar: list[str] = []
    uyarilar: list[str] = []
    olcum: dict = {}
    atolye_kok = kok.parent.parent
    with OnizlemeSunucusu(atolye_kok, 0) as srv:
        taban = f"http://127.0.0.1:{srv.port}/"
        url = srv.url(tur, ad)
        with sync_playwright() as p:
            tarayici = p.chromium.launch()
            try:
                for gen, yuk in GENISLIKLER:
                    sayfa = tarayici.new_page(viewport={"width": gen, "height": yuk})
                    pe: list[str] = []
                    kons: list[str] = []
                    kirik: list[str] = []
                    dis: list[str] = []
                    sayfa.on("pageerror", lambda e, pe=pe: pe.append(str(e)[:160]))
                    sayfa.on("console", lambda m, k=kons: k.append(m.text[:160])
                             if m.type == "error" else None)

                    # 🔴 Varsayılan argümanla liste bağlama: Playwright route işleyicisine
                    # 2 parametre görürse (route, request) verir → liste Request'le ezilir.
                    def _yon_kur(dis):
                        def _yon(route):
                            if route.request.url.startswith(taban):
                                return route.continue_()
                            dis.append(route.request.url[:100])
                            return route.abort()
                        return _yon
                    sayfa.route("**/*", _yon_kur(dis))
                    sayfa.on("response", lambda r, k=kirik: k.append(f"{r.status} {r.url[-60:]}")
                             if r.status >= 400 else None)

                    # 404 gövdesi text/plain + nosniff → Chromium ORB isteği `requestfailed`
                    # yapar, `response` olayı GELMEZ (ölçüldü). CSP'nin kestiği dış yükleme de
                    # burada görünür (failure "csp"), route'a hiç ulaşmaz.
                    def _dustu_kur(kirik, dis):
                        def _dustu(r):
                            if r.url.startswith(taban):
                                kirik.append(f"{r.failure} {r.url[-60:]}")
                            elif r.url[:100] not in dis:
                                dis.append(r.url[:100])
                        return _dustu
                    sayfa.on("requestfailed", _dustu_kur(kirik, dis))
                    sayfa.goto(url, wait_until="load", timeout=15000)
                    sayfa.wait_for_timeout(400)
                    m = sayfa.evaluate(_TASMA_JS)
                    etiket = f"{gen}px"
                    if pe:
                        hatalar.append(f"{etiket}: JS hatası ×{len(pe)} — {pe[0]}")
                    # CSP ihlali/kırık istek konsolda da görünür; ayrı sayılanları tekrar yazma
                    kons_ozgun = [k for k in kons if "Failed to load resource" not in k
                                  and not k.startswith("Loading the ")]
                    if kons_ozgun:
                        hatalar.append(f"{etiket}: konsol hatası ×{len(kons_ozgun)} — {kons_ozgun[0]}")
                    if kirik:
                        hatalar.append(f"{etiket}: kırık istek ×{len(kirik)} — {kirik[0]}")
                    if dis:
                        hatalar.append(f"{etiket}: dış istek ×{len(dis)} (engellendi) — {dis[0]}")
                    if m["scrollWidth"] > m["genislik"] + 1:
                        hatalar.append(f"{etiket}: yatay taşma — sayfa {m['scrollWidth']}px, "
                                       f"ekran {m['genislik']}px; taşan: {', '.join(m['tasan']) or '?'}")
                    if m["metin"] < 20:
                        hatalar.append(f"{etiket}: sayfa neredeyse boş ({m['metin']} karakter metin)")
                    if m["kucuk"]:
                        uyarilar.append(f"{etiket}: {m['kucuk']} metin öğesi {KUCUK_PUNTO}px'ten küçük")
                    olcum[etiket] = {"pageerror": len(pe), "konsol_hatasi": len(kons_ozgun),
                                     "kirik_istek": len(kirik), "dis_istek": len(dis),
                                     "scrollWidth": m["scrollWidth"], "genislik": m["genislik"],
                                     "kucuk_punto": m["kucuk"], "metin": m["metin"]}
                    if ekran_dizini is not None:
                        ekran_dizini.mkdir(parents=True, exist_ok=True)
                        yukseklik = min(EKRAN_AZAMI_YUKSEKLIK,
                                        sayfa.evaluate("document.documentElement.scrollHeight"))
                        sayfa.screenshot(path=str(ekran_dizini / f"{gen}.png"), full_page=True,
                                         clip={"x": 0, "y": 0, "width": gen,
                                               "height": max(yuk, yukseklik)})
                    sayfa.close()
            finally:
                tarayici.close()
    return hatalar, uyarilar, olcum


def dogrula(kok: Path, ekran_kaydet: bool = True) -> dict:
    """Tam doğrulama — `kok` = `<atölye>/<tür>/<ad>`. Sonuç `.gorev/dogrulama.json`'a da
    yazılır (parmak iziyle)."""
    t0 = time.monotonic()
    tur, ad = kok.parent.name, kok.name
    iz = parmak_izi(kok)
    hatalar, uyarilar = statik(kok)
    olcum: dict = {}
    if "index.html yok" not in " ".join(hatalar):
        try:
            h2, u2, olcum = ekran(kok, tur, ad,
                                  kok / alan.AYRILMIS / "ekran" if ekran_kaydet else None)
            hatalar += h2
            uyarilar += u2
        except Exception as e:
            logger.exception("[dogrulayici] ekran ölçümü çöktü")
            uyarilar.append(f"ekran ölçümü yapılamadı ({type(e).__name__})")
    sonuc = {"temiz": not hatalar, "hatalar": hatalar, "uyarilar": uyarilar,
             "olcum": olcum, "parmak_izi": iz, "sure_sn": round(time.monotonic() - t0, 2),
             "zaman": time.strftime("%Y-%m-%d %H:%M:%S")}
    kayit = kok / alan.AYRILMIS
    if kayit.is_dir():
        (kayit / SONUC_DOSYASI).write_text(json.dumps(sonuc, ensure_ascii=False, indent=1),
                                           encoding="utf-8")
    return sonuc


def son_sonuc(kok: Path) -> dict | None:
    """Son doğrulama — çalışma alanı o zamandan beri değişmediyse; değiştiyse None."""
    try:
        s = json.loads((kok / alan.AYRILMIS / SONUC_DOSYASI).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return s if s.get("parmak_izi") == parmak_izi(kok) else None


def metin(sonuc: dict) -> str:
    """Modele dönen kısa rapor."""
    if sonuc["temiz"]:
        satirlar = ["DOĞRULAMA TEMİZ — hata yok (1440 ve 390 genişlikte ölçüldü)."]
        if sonuc["uyarilar"]:
            satirlar.append("Uyarılar (isteğe bağlı düzelt): " + " · ".join(sonuc["uyarilar"][:5]))
        satirlar.append("Şimdi araç çağırmadan kısa bir özet yaz; görev biter.")
        return "\n".join(satirlar)
    satirlar = [f"DOĞRULAMA KİRLİ — {len(sonuc['hatalar'])} hata. Hepsini düzelt, sonra "
                "yeniden alan_bitir çağır:"]
    satirlar += [f"- {h}" for h in sonuc["hatalar"][:20]]
    if sonuc["uyarilar"]:
        satirlar.append("Uyarılar: " + " · ".join(sonuc["uyarilar"][:5]))
    return "\n".join(satirlar)
