"""11-15 üç işlev farkı — ön yüz kapıları (statik).

1. Galeri "+ KÖK KLASÖR EKLE" + klasör seçici + kökü listeden çıkar
2. Yedek › YEDEK/BULUTTA/AYARLAR + Kontrol et / Kuru çalıştır (js/yedek-rclone.js)
3. Avatar düğmesi iki durum: göster ↔ gizle (eski 'kucuk' kaydı → göster)

Davranış ölçümü (1280 + 390, demo arka uç, Playwright) depo dışında tutulur.
    python -m pytest -q frontend/tests/test_islev_farklari.py
"""
from __future__ import annotations

import re
from pathlib import Path

FE = Path(__file__).resolve().parents[1]


def _oku(yol: str) -> str:
    return (FE / yol).read_text("utf-8")


def _sozluk(dil: str) -> set[str]:
    return set(re.findall(r"^\s*'([a-z0-9.\-]+)':", _oku(f"js/diller/{dil}.js"), re.M))


# ── 1. Galeri ────────────────────────────────────────────────────────────────

def test_galeri_kok_ekle_dugmesi_ve_secici_var():
    html = _oku("galeri.html")
    for id_ in ("gl-ekle", "gl-secici", "gl-secici-yol", "gl-secici-liste", "gl-secici-bilgi", "gl-secici-ekle", "gl-secici-kapat"):
        assert f'id="{id_}"' in html, id_
    assert "KÖK KLASÖR EKLE" in html
    # Düğme ray'de, kök listesinin hemen altında (kişiseldeki yer)
    assert html.index('id="gl-kokler"') < html.index('id="gl-ekle"') < html.index('class="gl-salt"')


def test_galeri_js_secici_baglari():
    js = _oku("js/galeri.js")
    assert "$('gl-ekle').addEventListener('click'" in js
    assert "$('gl-secici-ekle').addEventListener('click', seciliKlasoruEkle)" in js
    assert "'gl-secici'" in js.split("var MODALLAR")[1].split(";")[0]          # Esc ile kapanır
    assert "json('/gozat'" in js and "json('/kok'" in js and "json('/kok/' + k.id, { method: 'DELETE' })" in js
    assert "gl-kok-sil" in js
    assert "alert(" not in js.split("async function seciciAc")[1].split("// ══")[0]   # hata satırda, dialog yok


# ── 2. Yedek ─────────────────────────────────────────────────────────────────

def test_yedek_rclone_yuklenir_ve_sirasi_dogru():
    html = _oku("index.html")
    assert '/ui/css/yedek-rclone.css?v=' in html
    i_r, i_y = html.index('/ui/js/yedek-rclone.js?v='), html.index('/ui/js/yedekleme.js?v=')
    assert i_r < i_y


def test_yedekleme_rclone_modulune_devreder():
    js = _oku("js/yedekleme.js")
    assert "_R().ustCubuk()" in js and "_R().pencere()" in js and "_R().govde()" in js
    assert "y.indexOf('r-') === 0" in js
    assert "window.yedeklemeCiz" in js


def test_yedek_rclone_sekmeler_ve_dugmeler():
    js = _oku("js/yedek-rclone.js")
    assert "['yedek', 'bulutta', 'ayarlar']" in js
    for y in ("r-kontrol", "r-kuru", "r-sekme", "r-git", "r-ayar-kaydet", "r-kapat"):
        assert f"'{y}'" in js or f'"{y}"' in js, y
    # kişisel uzak/hesap adı kodda yok
    for yasak in ("gdrive", "Pc " + "ih" + "san", "ih" + "san", "rclone-backup"):
        assert yasak not in js, yasak


def test_yedek_rclone_anahtarlari_sozlukte():
    js = _oku("js/yedek-rclone.js")
    sabit = set(re.findall(r"t\('(yedek\.r-[a-z0-9\-]+)'", js)) | set(re.findall(r"'(yedek\.r-[a-z0-9\-]+)'", js))
    nedenler = ["kurulu-degil", "uzak-yok", "uzak-secilmedi", "uzak-bulunamadi", "ulasilamadi", "okunamadi",
                "zaman-asimi", "klasor-yok", "yuki-atlandi", "yerel-yok", "yol", "genel"]
    dinamik = {f"yedek.r-neden-{n}" for n in nedenler} | {f"yedek.r-neden-{n}-alt" for n in nedenler}
    dinamik |= {f"yedek.r-sekme-{s}" for s in ("yedek", "bulutta", "ayarlar")}
    dinamik |= {f"yedek.r-hata-{h}" for h in ("uzak", "uzak-bulunamadi", "yol", "bant", "desen", "genel")}
    gerekli = {k for k in sabit if not k.endswith('-')} | dinamik
    assert len(sabit) >= 25
    for dil in ("tr", "en"):
        eksik = gerekli - _sozluk(dil)
        assert not eksik, (dil, sorted(eksik))


def test_backend_neden_kodlari_on_yuzde_karsilikli():
    """Arka ucun döndürdüğü her neden kodunun ön yüzde cümlesi var (aksi hâlde ham anahtar görünür)."""
    kaynak = (FE.parent / "backend" / "app" / "services" / "rclone_yedek.py").read_text("utf-8")
    kodlar = set(re.findall(r'"neden":\s*"([a-z\-]+)"', kaynak)) | set(re.findall(r'neden = "([a-z\-]+)"', kaynak))
    kodlar |= set(re.findall(r'AyarHatasi\("([a-z\-]+)"\)', kaynak))
    assert {"kurulu-degil", "uzak-yok", "yuki-atlandi"} <= kodlar
    tr = _sozluk("tr")
    for k in kodlar:
        assert f"yedek.r-neden-{k}" in tr or f"yedek.r-hata-{k}" in tr, k


# ── 3. Avatar ────────────────────────────────────────────────────────────────

def test_avatar_iki_durum():
    js = _oku("js/core.js")
    assert "const _AVATAR_AYARLARI = ['buyuk', 'gizli'];" in js
    assert "return kayitli === 'gizli' ? 'gizli' : 'buyuk';" in js        # eski 'kucuk' → göster
    assert "avatar.gizle-eylem" in js and "avatar.goster-eylem" in js
    for dil in ("tr", "en"):
        assert {"avatar.gizle-eylem", "avatar.goster-eylem"} <= _sozluk(dil)


def test_avatar_statik_etiket_eylem_soyler():
    html = _oku("index.html")
    blok = html[html.index('id="avatar-toggle"'):][:400]
    assert 'aria-label="Karakteri gizle"' in blok and 'title="Karakteri gizle"' in blok
    assert "Sonraki: Küçük" not in html
