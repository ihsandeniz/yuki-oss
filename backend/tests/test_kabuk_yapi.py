"""index.html kabuk yapısı — bütün sekme panelleri <main class="kabuk-icerik"> içinde (v0.8.4).

Neden: v0.8.3'te Halka Konsolu yazı alanı sonundaki fazladan bir </div> (a9a805f, kısayol çipleri
silinirken kalan kapanış) tarayıcıda <main>'i erken kapattı. Sonuç: #tab-hq (AYAR, Free dahil her
kademe) ekranın sağ yarısına sıkıştı, #tab-panel 1280'de genişlik 0 oldu, PLAN/HARİTA/İŞLER/AJAN
<main> dışına düştü. HTML hata vermez; yalnız ekran bozulur.

Ayrıştırma tarayıcının kuralına yakın: kapanış etiketi açık yığında aynı adlı en yakın öğeye kadar
her şeyi kapatır (eşleşen yoksa yok sayılır). Fazladan </div> böylece <main>'i de kapatır.
"""
from html.parser import HTMLParser
from pathlib import Path

INDEX = Path(__file__).resolve().parents[2] / "frontend" / "index.html"
BOS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
PANELLER = ("app", "tab-planner", "tab-hq", "tab-map", "tab-yedek", "tab-ajan")   # 11-13: tab-panel kalktı, tab-yedek geldi


class _Yigin(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.yigin = []          # [(etiket, attrs)]
        self.ata = {}            # id -> main.kabuk-icerik içinde miydi
        self.erken_kapanan = []  # main'i kendi </main>'i dışında kapatan kapanış etiketleri (satır)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if a.get("id") in PANELLER:
            self.ata[a["id"]] = any(t == "main" and "kabuk-icerik" in (x.get("class") or "") for t, x in self.yigin)
        if tag not in BOS:
            self.yigin.append((tag, a))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in BOS:
            self.yigin.pop()

    def handle_endtag(self, tag):
        for i in range(len(self.yigin) - 1, -1, -1):
            if self.yigin[i][0] == tag:
                kapanan = [t for t, _ in self.yigin[i + 1:]]
                if "main" in kapanan and tag != "main":
                    self.erken_kapanan.append((self.getpos()[0], tag))
                del self.yigin[i:]
                return


def _ayristir(metin):
    p = _Yigin()
    p.feed(metin)
    return p


def test_butun_sekme_panelleri_main_icinde():
    p = _ayristir(INDEX.read_text(encoding="utf-8"))
    assert set(p.ata) == set(PANELLER), f"panel eksik: {set(PANELLER) - set(p.ata)}"
    disarida = [k for k, v in p.ata.items() if not v]
    assert not disarida, f"<main class=kabuk-icerik> dışında kalan panel: {disarida}"


def test_main_kendi_kapanisindan_once_kapanmaz():
    p = _ayristir(INDEX.read_text(encoding="utf-8"))
    assert not p.erken_kapanan, f"<main>'i erken kapatan kapanış etiketi (satır, etiket): {p.erken_kapanan}"


def test_dedektor_fazladan_div_kapanisini_yakalar():
    """Mutasyon kanıtı testin içinde: sohbet panelinin sonuna bir </div> eklenince iki kapı da kırmızı."""
    metin = INDEX.read_text(encoding="utf-8")
    hedef = "\n<!-- ── PLANNER TAB ── -->"
    assert hedef in metin
    bozuk = _ayristir(metin.replace(hedef, "\n</div>" + hedef, 1))
    assert bozuk.erken_kapanan
    assert not bozuk.ata["tab-hq"] and not bozuk.ata["tab-yedek"]
