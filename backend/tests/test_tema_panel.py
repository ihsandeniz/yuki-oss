"""TEMA paneli ( panel 14, ORTAM SEÇ) — davranış kapıları.

`tema.js` gerçekten KOŞTURULUR (node + sahte pencere): Sistem kilidi ve message kapısı
kaynak metnine değil davranışa bakar. Panel kaynağı (klavye, yerinde güncelleme) metinsel.
Node yoksa koşu testleri atlanır (CI'da node var).
"""
from __future__ import annotations

import glob
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from yardim import FRONTEND, sozluk, yorumsuz

TEMA = FRONTEND / "js" / "tema.js"
PANEL = FRONTEND / "js" / "tema-panel.js"


def _node() -> str | None:
    yol = shutil.which("node")
    if yol:
        return yol
    adaylar = sorted(glob.glob(os.path.expanduser("~/.nvm/versions/node/*/bin/node")))
    return adaylar[-1] if adaylar else None


_HARNESS = r"""
const fs = require('fs'), vm = require('vm');
const kod = fs.readFileSync(process.argv[1], 'utf8');
const sen = JSON.parse(process.argv[2]);
const depo = Object.assign({}, sen.depo || {});
const dinleyici = {}; const mesajlar = [];
const attr = {};
const iframeMesaj = [];
const pencere = {
  location: { origin: 'http://127.0.0.1:8001' },
  localStorage: { getItem: k => (k in depo ? depo[k] : null), setItem: (k, v) => { depo[k] = String(v); }, removeItem: k => { delete depo[k]; } },
  matchMedia: () => ({ get matches() { return sen.os === 'acik'; }, addEventListener: (_, f) => { dinleyici.__mq = f; } }),
  addEventListener: (ad, f) => { (dinleyici[ad] = dinleyici[ad] || []).push(f); },
  dispatchEvent: () => true, CustomEvent: function (a, b) { this.type = a; this.detail = b && b.detail; },
};
const ust = sen.cerceve ? { id: 'ebeveyn' } : pencere;
pencere.parent = ust; pencere.window = pencere;
pencere.document = {
  documentElement: { setAttribute: (k, v) => { attr[k] = v; }, removeAttribute: k => { delete attr[k]; }, getAttribute: k => (k in attr ? attr[k] : null) },
  getElementById: id => (id === 'planner-iframe' && sen.iframe ? { contentWindow: { postMessage: (m, o) => iframeMesaj.push([m, o]) } } : null),
};
pencere.CustomEvent = pencere.CustomEvent;
vm.createContext(pencere); vm.runInContext(kod, pencere);
const sonuc = {};
for (const adim of sen.adimlar) {
  if (adim.t === 'mesaj') (dinleyici.message || []).forEach(f => f({ data: adim.veri, source: adim.kaynak === 'ebeveyn' ? ust : (adim.kaynak === 'kendi' ? pencere : { x: 1 }), origin: adim.origin || pencere.location.origin }));
  if (adim.t === 'ayarla') pencere.YukiTema.ayarla(adim.v);
  if (adim.t === 'sistem') pencere.YukiTema.sistemeBirak();
  if (adim.t === 'yenile') pencere.YukiTema.yenile();
  if (adim.t === 'depo') { if (adim.v === null) delete depo.yukiTema_v1; else depo.yukiTema_v1 = adim.v; }
  if (adim.t === 'osdegis') { sen.os = adim.v; dinleyici.__mq({}); }
}
console.log(JSON.stringify({ depo, tema: attr['data-tema'] || null, iframeMesaj, secimVar: pencere.YukiTema.secimVar(), sistemde: pencere.YukiTema.sistemde(), os: pencere.YukiTema.os() }));
"""


def kos(**sen) -> dict:
    node = _node()
    if not node:
        pytest.skip("node yok")
    sen.setdefault("adimlar", [])
    c = subprocess.run([node, "-e", _HARNESS, str(TEMA), json.dumps(sen)], capture_output=True, text=True, timeout=30)
    assert c.returncode == 0, c.stderr
    return json.loads(c.stdout)


# ── 🔴 Sistem kilidi ──────────────────────────────────────────────────────────

def test_cerceve_mesajdan_gelen_tema_KAYDEDILMEZ():
    """Eski kusur: PLAN iframe'i mesajdaki temayı localStorage'a yazıyor, 'Sistem' 1 sn'de koyuya kilitleniyordu."""
    s = kos(cerceve=True, os="koyu", adimlar=[{"t": "mesaj", "veri": {"type": "tema", "tema": "koyu"}, "kaynak": "ebeveyn"}])
    assert s["depo"] == {}, "iframe mesajdan gelen temayı kaydetti → Sistem seçimi kilitlenir"
    assert not s["secimVar"]


def test_cerceve_ebeveynden_gelen_gecerli_tema_UYGULANIR():
    s = kos(cerceve=True, os="koyu", adimlar=[{"t": "mesaj", "veri": {"type": "tema", "tema": "acik"}, "kaynak": "ebeveyn"}])
    assert s["tema"] == "acik"


def test_sistem_secimi_ebeveynde_sistem_kaydi_yazar_ve_iframe_e_COZULMUS_degeri_yollar():
    s = kos(os="acik", iframe=True, depo={"yukiTema_v1": "koyu"}, adimlar=[{"t": "sistem"}])
    assert s["depo"] == {"yukiTema_v1": "sistem"} and not s["secimVar"] and s["sistemde"] and s["tema"] == "acik"
    assert s["iframeMesaj"][-1][0] == {"type": "tema", "tema": "acik"}


def test_iframe_mesaji_hedef_origin_belirli():
    s = kos(os="koyu", iframe=True, adimlar=[{"t": "ayarla", "v": "orta"}])
    assert s["iframeMesaj"][-1][1] == "http://127.0.0.1:8001", "postMessage hedefi '*' — her pencere duyar"


def test_os_degisince_Sistemde_tema_izlenir_kayit_yazilmaz():
    s = kos(os="koyu", depo={"yukiTema_v1": "sistem"}, adimlar=[{"t": "osdegis", "v": "acik"}])
    assert s["tema"] == "acik" and s["depo"] == {"yukiTema_v1": "sistem"}


# ── 🔴 İlk açılış HEP KOYU (tasarım kararı 2026-11-12) ──────────────────

def test_ilk_acilis_bilgisayar_acik_temadayken_bile_KOYU():
    """Kayıt yok + bilgisayar açık tema → Yuki koyu açılır; kayıt yazılmaz, Sistem takibi kapalı görünür."""
    s = kos(os="acik")
    assert s["tema"] is None, f"ilk açılış koyu değil: {s['tema']}"
    assert s["depo"] == {} and not s["sistemde"] and not s["secimVar"]


def test_ilk_acilista_os_degisimi_izlenmez():
    s = kos(os="koyu", adimlar=[{"t": "osdegis", "v": "acik"}])
    assert s["tema"] is None and s["depo"] == {}


def test_kullanici_secimi_korunur_os_ne_derse_desin():
    assert kos(os="acik", depo={"yukiTema_v1": "orta"})["tema"] == "orta"
    assert kos(os="koyu", depo={"yukiTema_v1": "acik"})["tema"] == "acik"
    s = kos(os="acik", depo={"yukiTema_v1": "koyu"}, adimlar=[{"t": "osdegis", "v": "acik"}])
    assert s["tema"] is None and s["depo"] == {"yukiTema_v1": "koyu"}


def test_bilinmeyen_kayit_koyuya_duser_os_izlenmez():
    assert kos(os="acik", depo={"yukiTema_v1": "zzz"})["tema"] is None


def test_yenile_ortak_kaydi_okur_yazmaz():
    """mini HUD `storage` olayında `yenile()` çağırır: kayıt silinince koyu, 'sistem' olunca OS."""
    s = kos(os="acik", depo={"yukiTema_v1": "orta"}, adimlar=[{"t": "depo", "v": None}, {"t": "yenile"}])
    assert s["tema"] is None and s["depo"] == {}
    s = kos(os="acik", adimlar=[{"t": "depo", "v": "sistem"}, {"t": "yenile"}])
    assert s["tema"] == "acik" and s["depo"] == {"yukiTema_v1": "sistem"}


# ── message kapısı ────────────────────────────────────────────────────────────

def test_ust_pencere_kendi_postMessage_ine_uymaz():
    s = kos(cerceve=False, os="koyu", adimlar=[{"t": "mesaj", "veri": {"type": "tema", "tema": "acik"}, "kaynak": "kendi"}])
    assert s["tema"] is None and s["depo"] == {}


def test_yabanci_kaynak_ve_origin_reddedilir():
    s = kos(cerceve=True, os="koyu", adimlar=[
        {"t": "mesaj", "veri": {"type": "tema", "tema": "acik"}, "kaynak": "yabanci"},
        {"t": "mesaj", "veri": {"type": "tema", "tema": "orta"}, "kaynak": "ebeveyn", "origin": "https://kotu.example"},
    ])
    assert s["tema"] is None


def test_gecersiz_deger_yok_sayilir_koyuya_dusmez():
    s = kos(cerceve=True, os="acik", depo={"yukiTema_v1": "sistem"},
            adimlar=[{"t": "mesaj", "veri": {"type": "tema", "tema": "zzz"}, "kaynak": "ebeveyn"}])
    assert s["tema"] == "acik" and s["depo"] == {"yukiTema_v1": "sistem"}, "geçersiz değer temayı 'koyu'ya çevirdi / kaydetti"


def test_ayarla_gecersiz_degeri_kaydetmez():
    s = kos(os="acik", adimlar=[{"t": "ayarla", "v": "zzz"}])
    assert s["depo"] == {}


def test_os_tercihi_kayittan_bagimsiz():
    assert kos(os="acik", depo={"yukiTema_v1": "koyu"})["os"] == "acik"
    assert kos(os="koyu")["os"] == "koyu"


# ── panel: kaynak sözleşmesi ──────────────────────────────────────────────────

def _panel() -> str:
    return yorumsuz(PANEL.read_text(encoding="utf-8"))


def test_klavye_ok_tuslari_roving_tabindex_Home_End():
    k = _panel()
    for tus in ("ArrowRight", "ArrowDown", "ArrowLeft", "ArrowUp", "'Home'", "'End'"):
        assert tus in k, f"{tus} işlenmiyor"
    assert "setAttribute('tabindex'" in k and "'0' : '-1'" in k, "roving tabindex yok (4 Tab durağı arızası)"
    assert re.search(r"n\.focus\(\)", k), "seçimden sonra odak yeni karta verilmiyor"


def test_kartlar_yerinde_guncellenir_yeniden_cizilmez():
    k = _panel()
    assert k.count("innerHTML") == 3, "kart/anahtar yalnız kurulumda (+durum satırı) innerHTML yazmalı — her seçimde yeniden çizim odağı BODY'ye düşürür"
    govde = k.split("function guncelle()", 1)[1]
    assert "kap.innerHTML" not in govde


def test_panel_takip_durumunu_sistem_kaydindan_okur():
    """Kayıt yokken (ilk açılış = koyu) panel 'Sistem açık' DEMEMELİ; takip yalnız açık 'sistem' kaydı."""
    k = _panel()
    assert "var takip = T.sistemde();" in k
    assert "if (T.sistemde()) T.ayarla(T.al()); else T.sistemeBirak();" in k


def test_mini_hud_storage_olayinda_yenile_kullanir():
    m = yorumsuz((FRONTEND / "js" / "mini-hud.js").read_text(encoding="utf-8"))
    blok = m.split("e.key === 'yukiTema_v1'", 1)[1].split("}", 1)[0]
    assert "YukiTema.yenile()" in blok and "sistemeBirak" not in blok, "kayıt silinince mini HUD 'sistem' yazıp OS'a dönerdi"


def test_dil_ve_tema_olaylarinda_tazelenir():
    k = _panel()
    assert "addEventListener('yuki-dil-degisti', guncelle)" in k
    assert "addEventListener('yuki-tema-degisti', guncelle)" in k


def test_panel_her_acilista_tazelenir_menu_koprusu():
    ic = (FRONTEND / "js" / "intro-sequences.js").read_text(encoding="utf-8")
    assert "window.temaPanelAc" in ic and "_loaded.tema" not in yorumsuz(ic)


def test_degismez_sozlesme_korundu():
    html = (FRONTEND / "index.html").read_text(encoding="utf-8")
    assert 'id="tema-secenekler"' in html and 'role="radiogroup"' in html and 'id="tema-sistem"' in html
    tema = yorumsuz(TEMA.read_text(encoding="utf-8"))
    for uye in ("al:", "ayarla:", "secimVar:", "sistemde:", "sistemeBirak:", "yenile:", "get secenekler()"):
        assert uye in tema
    assert "'yukiTema_v1'" in tema


def test_anahtar_role_switch_ve_adli():
    k = _panel()
    assert 'role="switch"' in k and "aria-labelledby" in k and "aria-checked" in k


def test_panelin_her_anahtari_iki_sozlukte_var_ve_EN_Turkce_degil():
    k = _panel()
    anahtarlar = set(re.findall(r"_tpt\('([a-z0-9][\w.-]*)'", k))
    assert len(anahtarlar) >= 14
    tr, en = sozluk("tr"), sozluk("en")
    for a in anahtarlar:
        assert a in tr and a in en, a
        assert not re.search(r"[çğıöşüÇĞİÖŞÜ]", en[a]), f"EN sözlükte Türkçe harf: {a}"
    for a in ("tema.sistem.acik-durum", "tema.sistem.kapali-durum"):
        assert "{os}" in tr[a] and "{tema}" in tr[a] and "{os}" in en[a] and "{tema}" in en[a]


def test_css_eski_kartlar_gitti_yeni_dosya_bagli():
    html = (FRONTEND / "index.html").read_text(encoding="utf-8")
    assert "css/hq-tema.css" in html and "js/tema-panel.js" in html
    assert ".tema-kart" not in yorumsuz((FRONTEND / "css" / "hq.css").read_text(encoding="utf-8"))


def test_onbellek_damgalari_birlikte():
    html = (FRONTEND / "index.html").read_text(encoding="utf-8")
    plan = (FRONTEND / "planner.html").read_text(encoding="utf-8")
    sw = (FRONTEND / "sw.js").read_text(encoding="utf-8")
    ver = lambda m, p: re.search(p + r"\?v=(\d+)", m).group(1)  # noqa: E731
    for dil in ("tr", "en"):
        v = ver(html, rf"diller/{dil}\.js")
        assert ver(plan, rf"diller/{dil}\.js") == v == ver(sw, rf"diller/{dil}\.js")
    assert ver(html, r"js/tema\.js") == ver(plan, r"js/tema\.js")


# ── goz tur1 ──────────────────────────────────────────────────────────────────

def _css(ad: str) -> str:
    return yorumsuz((FRONTEND / "css" / ad).read_text(encoding="utf-8"))


def test_tema_odasi_ekstra_dolgu_tasimaz_kapat_dugmesine_binmez():
    """Duvar açıkken cam başlık ✕'in altında kalıyordu: `#hq-panel-tema{padding:22px 26px}` başlığı içeri çekiyordu."""
    m = re.search(r"#hq-panel-tema \{([^}]*)\}", _css("hq.css"))
    assert m and "padding" not in m.group(1)


def test_pasif_oda_resmi_opacity_ile_degil_filtreyle_soner():
    """opacity açık sayfada koyu sahneyi beyaza yıkıyordu."""
    css = _css("hq-tema.css")
    blok = re.search(r"\.tm-izgara\.takipte \.tm-oda:not\(\.takip\) \.tm-sahne \{([^}]*)\}", css)
    assert blok and "filter" in blok.group(1) and "opacity" not in blok.group(1)
    assert "color: var(--ink-2)" in css.split(".tm-izgara.takipte", 1)[1]


def test_anahtar_dokunma_alani_44_ustu():
    css = _css("hq-tema.css")
    m = re.search(r"\.tm-sw::before \{[^}]*inset: -(\d+)px -(\d+)px", css)
    assert m and 30 + 2 * int(m.group(1)) >= 44 and 52 + 2 * int(m.group(2)) >= 44


def test_ok_glifi_buyutulur_ve_durum_satiri_dul_birakmaz():
    assert "tm-ok" in PANEL.read_text(encoding="utf-8")
    assert "text-wrap: pretty" in _css("hq-tema.css")
