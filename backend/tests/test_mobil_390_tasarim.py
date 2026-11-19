"""Telefon (390) tasarım düzeltmeleri bekçisi — bakım taraması 10-11 § Tasarım T1 + T3.

T1 · AYAR'ın yatay sekme şeridi 390'da kayıyor ama bunu yalnız kenar solması söylüyordu: goz
     "Sağlık"ı yarım + soluk gördü, kaydırılabildiği belli değildi → solan kenarın üstünde ok
     (o tarafta etiket varken görünür, basınca kayar).
T3 · 390'da alt kısayol çipleri yazısız ~36px'ti (dokunma hedefi 44), mikrofonun ▾ rozeti
     ~16px'ti ve mikrofonun köşesine biniyordu → çipler/haplar 44px, dar kabukta rozet yok,
     cihaz seçimi ⋯ menüsündeki "Mikrofon seç"ten.
Piksel ölçümü 2026-10-11 bakım turunda (Playwright 390/1280);
burada kuralın KAYNAKTA durduğu kilitlenir (her kapı mutasyonla bir kez kırıldı).
"""
from __future__ import annotations

import re
from pathlib import Path

from yardim import yorumsuz

KOK = Path(__file__).resolve().parents[2]
FE = KOK / "frontend"
HQ = yorumsuz((FE / "css" / "hq.css").read_text(encoding="utf-8"))
SAHNE = yorumsuz((FE / "modes" / "sohbet-sahne.css").read_text(encoding="utf-8"))
SOHBET = yorumsuz((FE / "css" / "sohbet.css").read_text(encoding="utf-8"))
INTRO = yorumsuz((FE / "js" / "intro-sequences.js").read_text(encoding="utf-8"))
MIC = yorumsuz((FE / "js" / "mic-devices.js").read_text(encoding="utf-8"))
INDEX = (FE / "index.html").read_text(encoding="utf-8")


def _bloklar(css: str, bas: str) -> str:
    """`bas` ile açılan blokların gövdeleri (iç içe süslüyü sayarak)."""
    out = []
    for m in re.finditer(re.escape(bas) + r"\s*\{", css):
        i, d = m.end(), 1
        while d and i < len(css):
            d += {"{": 1, "}": -1}.get(css[i], 0)
            i += 1
        out.append(css[m.end():i - 1])
    return "\n".join(out)


HQ_DAR = _bloklar(HQ, "@media (max-width: 720px)")
SAHNE_DAR = _bloklar(SAHNE, "@container kabuk (max-width: 619px)")
SOHBET_DAR = _bloklar(SOHBET, "@container kabuk (max-width: 619px)")


# ── T1 · şerit okları ────────────────────────────────────────────────────────

def test_serit_oklari_markupta_ve_klavye_disinda():
    for kimlik, yon in (("hq-serit-geri", "-1"), ("hq-serit-ileri", "1")):
        m = re.search(r'<button id="' + kimlik + r'"[^>]*>', INDEX)
        assert m, f"{kimlik} markup'ta olmalı"
        etiket = m.group(0)
        assert f"hqSeritKaydir({yon})" in etiket, f"{kimlik} doğru yöne kaydırmalı"
        assert 'tabindex="-1"' in etiket and 'aria-hidden="true"' in etiket, \
            "ok yalnız işaretçi kolaylığı — odaklanan sekme zaten kendiliğinden görünür alana kayar"
    assert INDEX.index('id="hq-subnav"') < INDEX.index('id="hq-serit-ileri"'), "oklar şeridin kardeşi (#tab-hq içinde)"


def test_oklar_masaustunde_yok_telefonda_bayrakla():
    ust = HQ.replace(HQ_DAR, "")
    assert re.search(r"\.hq-serit-ok \{ display: none; \}", ust), "masaüstünde (dikey menü) ok çizilmez"
    assert "#tab-hq.active[data-serit-sag] #hq-serit-ileri" in HQ_DAR, "ileri oku yalnız sağda etiket varken"
    assert "#tab-hq.active[data-serit-sol] #hq-serit-geri" in HQ_DAR, "geri oku yalnız solda etiket varken"
    assert re.search(r"#hq-serit-ileri \{[^}]*inset-inline-end: var\(--oda-sag-guvenli", HQ_DAR), \
        "ileri oku şeridin sağ ucunda, ✕ payının solunda"


def test_sol_ok_acikken_solma_okun_altinda_biter():
    """goz: sol ok açıkken önceki etiketin son harfi ☰'nin köşesinde soluk görünüyordu."""
    m = re.search(r"#tab-hq\.active\[data-serit-sol\] #hq-subnav \{([^}]*)\}", HQ_DAR)
    assert m, "sol bayrakta şeridin maskesi değişmeli"
    # 11-13 sekme başlığı: şerit artık ☰ + köşe başlığından sonra başlar (--hq-serit-sol); solma
    # yine okun başladığı yerde biter: eski sabit 56px = 60 − 4, şimdi şerit başlangıcı − 4px.
    assert re.search(r"(?<!-webkit-)mask-image: linear-gradient\(to right, transparent "
                     r"(56px|calc\(var\(--hq-serit-sol, 60px\) - 4px\))", m.group(1))


def test_oklar_gorunur_hap_ve_44_genis():
    assert re.search(r"\.hq-serit-ok \{[^}]*inline-size: 44px", HQ_DAR)
    assert re.search(r"\.hq-serit-ok svg \{[^}]*border: 1px solid var\(--kenar\)[^}]*background: var\(--yuzey-2\)", HQ_DAR), \
        "çıplak 7px ok değil, basılacak yeri gösteren hap"


def test_ok_hoverda_palet_disi_golge_yok():
    assert re.search(r"\.hq-serit-ok:hover[^{]*\{[^}]*box-shadow: none", HQ_DAR), \
        "genel düğme hover'ının mavi gölgesi oku kutuya çeviriyordu"


def test_bayraklar_kaydirma_konumundan_yazilir():
    m = re.search(r"function _seritOk\(\)\{.*?\n  \}", INTRO, re.S)
    assert m, "_seritOk tanımlı olmalı"
    g = m.group(0)
    assert "'data-serit-sol'" in g and "'data-serit-sag'" in g
    assert "scrollWidth" in g and "clientWidth" in g and "scrollLeft" in g, "bayrak ölçüden doğar, sabit değil"
    assert re.search(r"addEventListener\('scroll', _seritOk", INTRO), "kaydırınca bayrak tazelenir"
    assert "ResizeObserver(_seritOk)" in INTRO, "gizli sekme açılınca (ölçü 0 → gerçek) tazelenir"
    isaretle = re.search(r"window\.hqMenuIsaretle = function\(\)\{.*?\n  \};", INTRO, re.S).group(0)
    assert "_seritOk();" in isaretle, "etkin sekmeye kaydırma sonrası oklar güncellenir"


def test_kaydirma_hareket_azaltmaya_uyar():
    m = re.search(r"window\.hqSeritKaydir = function\(yon\)\{.*?\n  \};", INTRO, re.S)
    assert m
    assert "prefers-reduced-motion: reduce" in m.group(0) and "'auto'" in m.group(0)


# ── T3 · dokunma hedefleri + mikrofon rozeti ────────────────────────────────

def test_dar_kabukta_durum_dugmeleri_44px():
    # 10-11: çip satırı kalktı, yerine ince "model · dil · küçült" satırı geldi.
    # Görsel 26px, dokunma alanı ::after ile 44×44 — kural her genişlikte geçerli (dar kabuk dahil).
    assert "hizli-cip" not in SAHNE_DAR, "dar kabukta çip kuralı kalmış (çipler ⋯ menüsünde)"
    assert re.search(r"\.hizli-hap::after \{[^}]*inset-block: calc\(\(26px - var\(--hedef\)\) / 2\)", SAHNE), \
        "durum düğmesinin dokunma alanı 44px (--hedef)"


def test_dar_kabukta_mikrofon_rozeti_yok_genis_kabukta_var():
    assert re.search(r"\.mic-dev-hint \{ display: none; \}", SOHBET_DAR), "rozet dar kabukta gizli"
    assert re.search(r"body:not\(\.hud-ring-mode\) #menu-mik-sec \{ display: flex; \}", SOHBET_DAR), \
        "menü girdisi dar kabukta görünür"
    assert re.search(r"body:not\(\.hud-ring-mode\) #menu-mik-sec \{ display: none; \}", SOHBET.replace(SOHBET_DAR, "")), \
        "geniş kabukta girdi gizli: menü 620px tavanında, bir satır daha 'Arayüz dili'ni kaydırmaya iterdi (goz)"
    # 10-11: AKTAR çipi kalktı → menüdeki eş tek yol, dar kabukta da görünür.
    # "Arayüz dili"nin ulaşılabilirliği tarayıcıda ölçülür (frontend/tests/test_birebir_konsol.py).
    assert not re.search(r"#menu-aktar \{ display: none; \}", SOHBET_DAR), "AKTAR menüde gizlenemez"
    assert 'id="cip-aktar"' not in INDEX
    assert "display: none" not in SOHBET.replace(SOHBET_DAR, "").split(".mic-dev-hint {", 1)[1].split("}", 1)[0], \
        "geniş kabukta rozet duruyor"


def test_mikrofon_secimi_menude_ve_calisan_kancaya_bagli():
    m = re.search(r'<button id="menu-mik-sec"[^>]*>.*?</button>', INDEX, re.S)
    assert m, "⋯ menüsünde 'Mikrofon seç' girdisi olmalı (rozetsiz kabukta tek görünür yol)"
    assert 'class="more-item"' in m.group(0), "more-item: tıklanınca ⋯ menüsü kapanır (core.js)"
    # 11-14: araç yayında kısa ad (girdi.yay.mikrofon), tam ad title/aria'da (mik.sec)
    assert 'onclick="micCihazMenusuAc()"' in m.group(0) and 'data-i18n-title="mik.sec"' in m.group(0)
    sec = INDEX.split('id="input-secondary-btns"', 1)[1].split('id="hizli', 1)[0]
    assert 'id="menu-mik-sec"' in sec, "girdi ⋯ menüsünün içinde"
    assert re.search(r"window\.micCihazMenusuAc = function \(\) \{[^}]*openMenu\(btn\)", MIC), \
        "kanca mic-devices.js'in kendi menüsünü açar (ikinci menü yazılmaz)"


def test_degisen_dosyalarin_surumu_artti():
    for yol, asgari in (("css/hq.css", 29), ("modes/sohbet-sahne.css", 3), ("css/sohbet.css", 19),
                        ("js/mic-devices.js", 3), ("js/intro-sequences.js", 73)):
        m = re.search(re.escape(yol) + r"\?v=(\d+)", INDEX)
        assert m and int(m.group(1)) >= asgari, f"{yol} ?v= artmalı (önbellek eski CSS/JS'i vermesin)"
