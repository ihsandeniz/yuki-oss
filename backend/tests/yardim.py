"""Test yardımcıları — frontend kaynaklarını okuyan kapılar için ortak zemin.

Neden ayrı dosya: sözlük okuma ve yorum sıyırma bu dizinde ZATEN üç-dört kez
kopyalanmıştı (`test_faz2_dil_iskelesi` · `test_faz3_metin_cevirisi` ·
`test_ayar_gorunurlugu` · `test_google_panel_kapisi`). Bu depoda o desenin
bedeli ödendi: `esc()` 3 kopya, `af()` 2 kopya, `start.sh` komşu projeden
fotokopi. Beşinci kopyayı yazmak yerine ortak yer açıldı.

⚠️ Mevcut kopyalar BU TURDA taşınmadı — çalışan kapıları i18n dalgasının
ortasında yeniden düzenlemek, kırmızı yandıklarında sebebi belirsizleştirirdi.
Yeni kapılar buradan besleniyor; eskiler sıradaki temizlik turunda gelir.
"""
from __future__ import annotations

import re
from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
DILLER = FRONTEND / "js" / "diller"

_SATIR = re.compile(r"^\s*'((?:[^'\\]|\\.)*)':\s*'((?:[^'\\]|\\.)*)',\s*$", re.M)


def sozluk(kod: str) -> dict[str, str]:
    """`js/diller/<kod>.js` → {anahtar: değer}.

    Sözlük JSON değil JS (senkron yüklenmek zorunda — `dil.js` başlığındaki
    FOUT gerekçesi), o yüzden ayrıştırma metinseldir. Gövde `= {`'ten sonra
    başlar; başlıktaki yorum bloğu içinde de tırnaklı satırlar var ve onlar
    anahtar sayılmamalı.
    """
    metin = (DILLER / f"{kod}.js").read_text(encoding="utf-8")
    govde = metin.split("= {", 1)[1]
    coz = lambda s: s.replace("\\'", "'").replace("\\\\", "\\")  # noqa: E731
    return {coz(k): coz(v) for k, v in _SATIR.findall(govde)}


def menu_anahtari(panel_id: str) -> str:
    """`HQ_MENU`'deki bir panelin etiket ANAHTARINI döndürür.

    FAZ 3 · Dalga 2'den (2026-09-19) beri tablo metin değil anahtar taşıyor:
    `etiket:'hq.menu.cihazlar'`. Panel kapıları eskiden `etiket:'Cihazlar'`
    diye ham metin arıyordu; her biri ayrı ayrı düzeltilirse aynı desen
    dördüncü, beşinci kez kopyalanır (bu depoda `esc()` böyle üçlendi).

    Anahtarı bulamazsa `AssertionError` atar — yani "girdi menüde var mı"
    sorusunu da bu fonksiyon cevaplıyor.
    """
    kod = yorumsuz((FRONTEND / "js" / "intro-sequences.js").read_text(encoding="utf-8"))
    m = re.search(rf"id:\s*'{re.escape(panel_id)}'.*?etiket:\s*'([^']+)'", kod, re.S)
    assert m, f"HQ_MENU'de '{panel_id}' girdisi ya da etiketi yok — panele ULAŞILAMAZ"
    anahtar = m.group(1)
    assert anahtar.startswith("hq.menu."), (
        f"'{panel_id}' etiketi çeviri anahtarı değil: {anahtar!r} — ham metin "
        "İngilizce müşteride Türkçe kalır (FAZ 3 · Dalga 2)"
    )
    return anahtar


def menu_adi(panel_id: str, dil: str) -> str:
    """Panelin bir dilde GÖRÜNEN adı. Sözlükte karşılığı yoksa yanar —
    `dil.js::t` bilinmeyen anahtarda anahtarı döndürdüğü için o durumda
    menüde `hq.menu.cihazlar` yazardı."""
    anahtar = menu_anahtari(panel_id)
    s = sozluk(dil)
    assert anahtar in s, f"{dil} sözlüğünde '{anahtar}' yok"
    return s[anahtar]


def yorumsuz(js: str) -> str:
    """`//` ve `/* */` sıyırıcı.

    Gerekçe ölçülmüş ve bu depoda üç kez ödendi: kaldırılan bir kalıbın geri
    gelmediğini ölçen test, o kalıbı ANLATAN yorumu bulup kırmızı yanıyor.
    """
    js = re.sub(r"/\*.*?\*/", " ", js, flags=re.S)
    return "\n".join(s for s in js.splitlines() if not s.lstrip().startswith("//"))


def lisans_merdiveni() -> dict[str, dict]:
    """HQ › LİSANS paket merdiveni (`intro-sequences.js::_LIC_MERDIVEN`) → {kademe: basamak}.

    Basamak = {'ad', 'fiyat', 'olcu', 'dahil'?, 'gor'?, 'maddeler': [{'ozellik'|'araclar', 'ad', 'ne'}]}.
    Merdiven 09-28'den beri (panel 9, taslak B) kademe vaadinin TEK yeri — eskiden index.html'de
    tek satırlık "Ultra: + semantik hafıza…" cümlesiydi. Ayrıştırma metinsel: veri tek satırlık
    `anahtar:'değer'` çiftleri, iç içe yapı yalnız `maddeler:[…]`.
    """
    kod = yorumsuz((FRONTEND / "js" / "intro-sequences.js").read_text(encoding="utf-8"))
    assert "var _LIC_MERDIVEN=[" in kod, "_LIC_MERDIVEN bulunamadı — lisans paneli yeniden yazıldıysa ayrıştırıcıyı güncelle"
    blok = kod[kod.index("var _LIC_MERDIVEN=["):]
    blok = blok[: blok.index("\n  ];")]
    sonuc: dict[str, dict] = {}
    for parca in re.split(r"\{kademe:'", blok)[1:]:
        kademe = parca[: parca.index("'")]
        bas = parca[: parca.index("maddeler:[")]
        basamak: dict = dict(re.findall(r"(\w+):'([^']*)'", bas))
        basamak.pop("kademe", None)
        basamak["maddeler"] = [dict(re.findall(r"(\w+):'([^']*)'", m))
                               for m in re.findall(r"\{((?:ozellik|araclar):[^{}]*)\}", parca)]
        sonuc[kademe] = basamak
    return sonuc
