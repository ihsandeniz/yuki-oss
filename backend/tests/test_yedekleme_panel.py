"""YEDEKLEME paneli — davranış ( panel 12, taslak B "korunan yerler").

Panel `node` ile GERÇEK dosya üzerinde koşturulur (DOM + `authFetch` sahtesi, Google'a/Drive'a istek yok);
node yoksa atlanır. Her test bir kusuru ölçer ve mutasyonla kırmızıya döndüğü görüldü.

Kapanan kusurlar (BAGLAM.md): `_yetkiFetch` tanımsız · yalan yeşil (token = bağlı) · 401 "okunamadı" ·
çift tık · yoklama formu/mesajı siliyor · kapalıyken "kuruldu" · ham Drive metni · ölü "sınırı büyüt" vaadi ·
sabit Linux yer tutucusu · boş geçen sır testi.
"""
from __future__ import annotations

import glob
import json
import os
import re
import shutil
import subprocess
from datetime import datetime, timedelta, timezone

import pytest

from yardim import FRONTEND, sozluk, yorumsuz

JS = FRONTEND / "js" / "yedekleme.js"


def _node() -> str | None:
    yol = shutil.which("node")
    if yol:
        return yol
    adaylar = sorted(glob.glob(os.path.expanduser("~/.nvm/versions/node/*/bin/node")))
    return adaylar[-1] if adaylar else None


_KOSUM = r"""
const fs = require('fs');
const S = JSON.parse(process.argv[process.argv.length - 1]);
const cagri = [], cizimler = [];
global.window = global;
window.YukiDil = { t: (k, d) => k + (d ? JSON.stringify(d) : ''), yerel: () => 'tr-TR' };
const dinleyici = {};
window.addEventListener = (t, f) => { dinleyici[t] = f; };
if (S.yukiDosya) window.yukiDosya = { klasorSec: async () => S.yukiDosya };
global.confirm = () => { throw new Error('confirm() cagrildi'); };
let surum = 0, stub = {};
const el = {
  _h: '', dinle: {}, offsetParent: {},
  get innerHTML() { return this._h; },
  set innerHTML(v) { this._h = v; surum++; stub = {}; cizimler.push(v); },
  addEventListener(t, f) { this.dinle[t] = f; }, contains() { return true; },
};
function alan(id) {   // her çizimde YENİ nesne; değeri HTML'deki value'dan gelir (kullanıcı yazısı = nesne üstünde)
  if (!el._h.includes('id="' + id + '"')) return null;
  if (!stub[id]) { const m = new RegExp('id="' + id + '"[^>]*?value="([^"]*)"').exec(el._h);
    stub[id] = { id, value: m ? m[1] : '', focus() {}, dataset: {} }; }
  return stub[id];
}
global.document = { hidden: false, addEventListener() {},
  getElementById(id) { return id === 'yedek-kok' ? el : (id === 'y-mesaj' ? mesajEl() : alan(id)); } };
function mesajEl() { return el._h.includes('id="y-mesaj"') ? { set innerHTML(v) { }, dataset: {} } : null; }
function yanit(kod, govde) { return { status: kod, ok: kod >= 200 && kod < 300, headers: { get: () => null }, json: async () => govde }; }
if (!S.authFetchYok) window.authFetch = (url, o) => { const y = (o && o.method) || 'GET'; cagri.push(y + ' ' + url);
  let c = S.yanit[y + ' ' + url] || S.yanit[url] || [404, {}];
  if (S.yanitDizi && S.yanitDizi[y + ' ' + url]) { const d = S.yanitDizi[y + ' ' + url]; c = d.length > 1 ? d.shift() : d[0]; }
  return new Promise(r => setTimeout(() => r(yanit(c[0], c[1])), 5)); };
window.open = () => {};
window.switchHqTab = (t) => cagri.push('SEKME ' + t);
// 11-13 : panel YEDEK sekmesinde; Google düğmesi önce HQ sekmesine geçer, hedef paneli _hqHedefPanel taşır.
window.switchTab = (t) => cagri.push('SEKME ' + (t === 'hq' ? window._hqHedefPanel : t));
const gercek = setInterval; global.setInterval = (f, ms) => gercek(f, 15);
eval(fs.readFileSync(S.dosya, 'utf8'));
const bekle = ms => new Promise(r => setTimeout(r, ms));
(async () => {
  window.yedeklemePanelAc(); await bekle(120);
  const acilis = el.innerHTML, acilisCagri = cagri.slice(); cagri.length = 0;
  for (const a of (S.adimlar || [])) {
    if (a.tik) { const t = a.tik; el.dinle.click({ target: { closest: () => ({ dataset: { y: t.y, id: t.id }, disabled: false }) } }); }
    if (a.yaz) for (const k in a.yaz) { const e = alan(k); if (e) e.value = a.yaz[k]; }
    if (a.degis) el.dinle.change({ target: { id: a.degis.id, checked: a.degis.checked } });
    if (a.dil) dinleyici['yuki-dil-degisti']();
    await bekle(a.bekle || 40);
  }
  await bekle(S.son || 150);
  const saat = alan('y-saat');
  console.log(JSON.stringify({ acilis, acilisCagri, son: el.innerHTML, cagri, cizimler: cizimler.length, saat: saat ? saat.value : null }));
  process.exit(0);
})();
"""


def _panel(yanit: dict, adimlar=None, **ek) -> dict:
    node = _node()
    if not node:
        pytest.skip("node yok — panel davranışı ölçülemedi")
    s = {"dosya": str(JS), "yanit": yanit, "adimlar": adimlar or [], **ek}
    r = subprocess.run([node, "-e", _KOSUM, json.dumps(s)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout.strip().splitlines()[-1])


_D, _CAL, _AYAR, _DRIVE = "/api/yedekleme/durum", "POST /api/yedekleme/calistir", "POST /api/yedekleme/ayar", "/api/yedekleme/drive-kullanim"


def _simdi(**fark):
    return (datetime.now(timezone.utc) - timedelta(**fark)).isoformat()


def _kay(ad="Belgeler", id="k1", **ek):
    k = {"id": id, "ad": ad, "yol": f"C:\\Users\\a\\{ad}", "dosya": 120, "bayt": 4_100_000, "kaynakta_yok": 0,
         "sistem": False, "yol_var": True, "son_yedek": _simdi(hours=2), "tur": {"durum": "tamam"}, "canli": None}
    k.update(ek)
    return k


def _tur(**ek):
    t = {"tetik": "elle", "bitti": _simdi(hours=2), "saniye": 4.0, "yuklenen": 12, "guncellenen": 3, "atlanan": 100,
         "bayt": 214_000_000, "kaynakta_yok": 0, "buyuk_atlandi": [], "hata": None, "tam": True, "kaynaklar": []}
    t.update(ek)
    return t


def _d(**ek):
    d = {"acik": True, "yuki_verisi": True, "zamanlama": "03:00", "zamanlama_bilgi": {"kurulu": True, "sonraki": _simdi(hours=-20)},
         "tavanlar": {"tek_dosya_mb": 200, "tur_mb": 2048},
         "kaynaklar": [_kay("Yuki verisi", "yuki", sistem=True, yol="/x"), _kay()], "tum_kaynaklar": [],
         "calisiyor": False, "canli": None, "son_tur": _tur(), "son_yedek": _simdi(hours=2),
         "baglanti": {"token": True, "kimlik": True, "durum": "bagli", "sebep": None,
                      "son_deneme": {"ok": True, "zaman": _simdi(minutes=3)}}}
    d.update(ek)
    return d


def _g(durum, sebep=None, token=True):
    return {"token": token, "kimlik": True, "durum": durum, "sebep": sebep, "son_deneme": None}


def _ac(d, **ek):
    return _panel({_D: [200, d], _DRIVE: [200, {"limit": 15e9, "kullanilan": 6e9}], **ek})["acilis"]


def _j(html):
    """Sahte `YukiDil.t` değerleri JSON olarak ekler; HTML kaçışını geri al."""
    return html.replace("&quot;", '"')


def _ilk(html):
    """Hüküm şeridinin başlık anahtarı."""
    return re.search(r'<section class="yb-serit[^"]*".*?<h4>(.*?)</h4>', html, re.S).group(1)


# ── ① Yetkili fetch ──────────────────────────────────────────────────────────

def test_panel_authFetch_ile_konusur_cipla_fetche_DUSMEZ():
    """🔴 `window._yetkiFetch` tanımsızdı → çıplak `fetch`; uygulama kilidi kuruluyken her istek 401.
    Burada `fetch` YOK: eski kod ya patlar ya "okunamadı" çizer."""
    s = _panel({_D: [200, _d()]})
    assert s["acilisCagri"][0] == "GET /api/yedekleme/durum", s["acilisCagri"]
    assert "yedek.okunamadi-baslik" not in s["acilis"]
    assert "_yetkiFetch" not in yorumsuz(JS.read_text(encoding="utf-8"))


# ── ② Hüküm matrisi: 12 hâl, her biri kendi cümlesiyle ───────────────────────

HALLER = {
    "bagsiz": (_d(baglanti=_g("yok", token=False), son_tur=None, son_yedek=None), "yedek.bagsiz-baslik", "kurulum"),
    "bagsiz-hazir": (_d(baglanti=_g("hazir", token=False)), "yedek.bagsiz-baslik", "kurulum"),
    "kopuk": (_d(baglanti=_g("kopuk", "invalid_grant")), "yedek.kopuk-baslik", "kritik"),
    "kopuk-kimlik": (_d(baglanti=_g("kopuk", "invalid_client")), "yedek.kopuk-baslik-kimlik", "kritik"),
    "kapali": (_d(acik=False), "yedek.kapali-baslik", "uyari"),
    "ilk": (_d(son_tur=None, son_yedek=None), "yedek.ilk-baslik", "kurulum"),
    "iyi": (_d(), "yedek.iyi-baslik", "iyi"),
    "uyarili": (_d(son_tur=_tur(tavan_doldu=True, tam=False, tavan_atlanan=4,
                                kaynaklar=[{"id": "k1", "durum": "yarim", "tavan_atlanan": 4}]),
                   kaynaklar=[_kay("Yuki verisi", "yuki", sistem=True), _kay(tur={"durum": "yarim", "tavan_atlanan": 4})]),
                "yedek.uyarili-baslik", "uyari"),
    "bayat": (_d(son_yedek=_simdi(days=6), son_tur=_tur(bitti=_simdi(days=6)),
                 kaynaklar=[_kay("Yuki verisi", "yuki", sistem=True, son_yedek=_simdi(days=6)), _kay(son_yedek=_simdi(days=6))]),
              "yedek.bayat-baslik", "uyari"),
    "suruyor": (_d(calisiyor=True, canli={"yuklenen": 5, "guncellenen": 0, "bayt": 1000}), "yedek.yedekleniyor", "olculemedi"),
    "hatali": (_d(son_tur=_tur(hata="Yedekleme yarida kaldi", hata_tur="ag", tam=False, teknik="Server disconnected",
                               kaynaklar=[{"id": "k1", "durum": "yarida"}])), "yedek.yarida-baslik", "kritik"),
    "dolu": (_d(son_tur=_tur(hata="Drive dolu", hata_tur="dolu", tam=False)), "yedek.dolu-baslik", "kritik"),
    "api": (_d(son_tur=_tur(hata="Drive API kapali", hata_tur="api-kapali", tam=False)), "yedek.api-baslik", "kritik"),
}


@pytest.mark.parametrize("ad", list(HALLER))
def test_hukum_matrisi(ad):
    d, baslik, isik = HALLER[ad]
    h = _ac(d)
    assert _ilk(h) == f"<b>{baslik}" or baslik in _ilk(h), (ad, _ilk(h))
    sert = re.search(r'<section class="yb-serit[^"]*".*?</section>', h, re.S).group(0)
    assert f"durum-isik {isik}" in sert, (ad, sert[:300])


def test_KOPUK_baglanti_token_dosyasi_olsa_da_YESIL_yanmaz_ve_simdi_dugmesi_yok():
    """Yalan yeşil: eski panel `baglanti.token`'a bakıyordu — token dosyası aylar önce iptal edilmiş
    izinle de diskte durur, "Şimdi yedekle" açık kalır, basınca tur hatayla biterdi."""
    h = _ac(_d(baglanti=_g("kopuk", "invalid_grant")))
    sert = re.search(r'<section class="yb-serit.*?</section>', h, re.S).group(0)
    assert "durum-isik iyi" not in sert and "yedek.iyi-baslik" not in h
    assert 'data-y="simdi"' not in h, "Google koptuysa yedeklemeyi başlatan düğme sunulmamalı"
    assert 'data-y="google"' in h
    assert "google.neden-grant" in h, "sebep söylenmedi"


def test_KAPALI_hukmu_ac_dugmesiyle_ve_son_yedek_tarihiyle():
    h = _ac(_d(acik=False))
    assert 'data-y="ac"' in h and "yedek.kapali-alt" in h and 'data-y="simdi"' not in h.split("yb-ana")[0]


def test_ILK_alt_cumlesi_saat_kuruluysa_saati_soyler_degilse_soylemez():
    assert "yedek.ilk-alt-saat" in _ac(_d(son_tur=None, son_yedek=None))
    h = _ac(_d(son_tur=None, son_yedek=None, zamanlama=None, zamanlama_bilgi={"kurulu": False, "sonraki": None}))
    assert "yedek.ilk-alt-saat" not in h and "yedek.ilk-alt" in h


def test_SURUYOR_canli_sayac_ve_belirsiz_cubuk_ve_pasif_dugme():
    h = _ac(HALLER["suruyor"][0])
    assert "yb-belirsiz" in h and 'role="progressbar"' in h and "yedek.suruyor-sayac" in h
    assert re.search(r'data-y="simdi"[^>]*disabled', h)


def test_HATALI_ham_istisna_ana_metinde_degil_yalniz_TEKNIK_AYRINTIda():
    h = _ac(HALLER["hatali"][0])
    ana, _, teknik = h.partition("<details>")
    assert "Server disconnected" not in ana and "Server disconnected" in teknik and "yedek.teknik" in teknik


def test_DOLU_ne_yapmali_cumlesi_ve_tekrar_dene():
    h = _ac(HALLER["dolu"][0])
    assert "yedek.dolu-ne-yapmali" in h and "yedek.tekrar-dene" in h


def test_UYARILI_tavan_dolunca_basari_gibi_gorunmez():
    """Tur "başarılı" bitti ama dosyaların kalanı yedekte değil — eski panel "Son yedekleme ✓" derdi."""
    h = _ac(HALLER["uyarili"][0])
    assert "yedek.iyi-baslik" not in h and "yedek.et-yarim" in h and "yedek.kart-yarim" in h
    assert 'data-y="simdi"' in _kart(h, "Belgeler"), "yarım klasörde 'Kalanını yedekle' yok"


def test_BAYAT_son_yedek_kac_gun_once_ve_ipucu():
    h = _ac(HALLER["bayat"][0])
    assert '"n":6' in _j(h) and "yedek.bayat-ipucu" in h


def test_BAYAT_klasorler_de_yedekte_diye_YESIL_yanmaz():
    h = _ac(HALLER["bayat"][0])
    k = _kart(h, "Belgeler")
    assert "durum-isik uyari" in k and "yedek.et-yedekte" not in k
    assert 'yedek.gun-once{"n":6}' in _j(k), "etiket kaç gün önce olduğunu söylemiyor"


def test_BAYAT_saat_kurulu_degilse_yalniz_elle_calisana_dayatma_YAPMAZ():
    d = _d(zamanlama=None, zamanlama_bilgi={"kurulu": False, "sonraki": None},
           son_yedek=_simdi(days=6), son_tur=_tur(bitti=_simdi(days=6)))
    assert "yedek.bayat-baslik" not in _ac(d)


# ── ③ Kapı hâlleri ───────────────────────────────────────────────────────────

def test_401_OTURUM_KILITLI_der_okunamadi_demez_429_COK_SIK_500_AYRI():
    h = _panel({_D: [401, {"detail": "Unauthorized"}]})["acilis"]
    assert "hq.oturum-kilitli" in h and "Unauthorized" not in h and "yedek.durum-hata" not in h
    h = _panel({_D: [429, {"detail": "Rate limit"}]})["acilis"]
    assert "google.cok-sik" in h and "Rate limit" not in h
    h = _panel({_D: [500, {"detail": "Internal Server Error"}]})["acilis"]
    assert "yedek.durum-hata" in h and "google.yukiye-ulasilamadi" not in h, "Yuki cevap verdi ama 'ulaşılamadı' dendi"
    h = _panel({})["acilis"]            # 404 → ok değil
    assert "yedek.okunamadi-baslik" in h


def test_PRO_kartinda_panelin_geri_kalani_cizilmez():
    h = _panel({_D: [403, {}]})["acilis"]
    assert "yb-yan" not in h and "yb-kartlar" not in h and 'id="y-saat"' not in h


# ── ④ Klasör kartları: her klasörün KENDİ durumu ─────────────────────────────

def _kart(html, ad):
    return re.search(r'<article class="yb-kart[^"]*">(?:(?!</article>).)*?<h5>' + ad + r'</h5>.*?</article>', html, re.S).group(0)


def test_kart_YOL_YOK_kritik_bulunamadi():
    h = _ac(_d(kaynaklar=[_kay("Yuki verisi", "yuki", sistem=True), _kay("Fotolar", "k2", yol_var=False)]))
    k = _kart(h, "Fotolar")
    assert "yedek.et-bulunamadi" in k and "durum-isik kritik" in k and "yedek.kart-bulunamadi" in k


def test_kart_buyuk_dosya_SINIRIN_DEGERIYLE_soylenir_ve_sinir_buyut_vaadi_YOK():
    t = _tur(buyuk_atlandi=[{"yol": "tatil.mp4", "mb": 640.0, "kaynak": "k1"}, {"yol": "b.mp4", "mb": 300.0, "kaynak": "k1"}],
             tam=True)
    h = _ac(_d(son_tur=t, tavanlar={"tek_dosya_mb": 200, "tur_mb": 2048}))
    k = _kart(h, "Belgeler")
    assert 'yedek.et-atlandi{"n":"2"}' in _j(k) and '"mb":200' in _j(k) and "tatil.mp4" in k
    for dil in ("tr", "en"):
        s = sozluk(dil)
        for anahtar in ("yedek.kart-buyuk", "yedek.kart-buyuk-ornek"):
            assert not re.search(r"büyüt|raise|increase|yükselt", s[anahtar], re.I), f"{dil}: ölü vaat geri geldi"


def test_kart_hata_sonrasi_YARIDA_ile_SIRA_GELMEDI_ayri_cumlelerdir():
    t = _tur(hata="x", hata_tur="ag", tam=False)
    d = _d(son_tur=t, kaynaklar=[_kay("Yuki verisi", "yuki", sistem=True, tur={"durum": "tamam"}),
                                 _kay("Belgeler", "k1", tur={"durum": "yarida"}),
                                 _kay("Resimler", "k2", tur={"durum": "sira-gelmedi"})])
    h = _ac(d)
    assert "yedek.et-yarida" in _kart(h, "Belgeler") and "yedek.et-sira-gelmedi" in _kart(h, "Resimler")
    assert "yedek.et-yedekte" in _kart(h, "Yuki verisi"), "tamamlanan klasör de kırmızıya boyandı"


def test_kart_Drive_dolu_klasore_Drivea_yer_kalmadi_der():
    d = _d(son_tur=_tur(hata="d", hata_tur="dolu", tam=False), kaynaklar=[_kay("Belgeler", "k1", tur={"durum": "yarida"})])
    assert "yedek.kart-dolu" in _ac(d)


def test_kart_KOPUK_ve_KAPALI_klasorler_son_yedek_tarihini_gosterir_YEDEKTE_demez():
    h = _ac(_d(baglanti=_g("kopuk", "invalid_grant")))
    assert "yedek.kart-kopuk" in _kart(h, "Belgeler") and "yedek.et-yedekte" not in _kart(h, "Belgeler")
    h = _ac(_d(acik=False))
    assert "yedek.kart-kapali" in _kart(h, "Belgeler") and "yedek.et-yedekte" not in _kart(h, "Belgeler")


def test_kart_SURERKEN_canli_durum_okunur():
    d = _d(calisiyor=True, canli={"yuklenen": 1, "guncellenen": 0, "bayt": 5},
           kaynaklar=[_kay("Yuki verisi", "yuki", sistem=True, canli={"durum": "tamam"}),
                      _kay("Belgeler", "k1", canli={"durum": "suruyor"}), _kay("Resimler", "k2", canli={"durum": "sirada"})])
    h = _ac(d)
    assert "yedek.et-suruyor" in _kart(h, "Belgeler") and "yedek.et-sirada" in _kart(h, "Resimler")


def test_yuki_verisi_KAPALIYSA_geri_acma_yolu_var():
    h = _ac(_d(yuki_verisi=False, kaynaklar=[_kay()]))
    assert 'data-y="yuki-ac"' in h


# ── ⑤ Eylemler ───────────────────────────────────────────────────────────────

def test_UC_hizli_tik_TEK_istek_ve_bitince_dugme_ACILIR():
    s = _panel({_D: [200, _d()], _CAL: [200, {"ok": True}]},
               [{"tik": {"y": "simdi"}, "bekle": 1}, {"tik": {"y": "simdi"}, "bekle": 1}, {"tik": {"y": "simdi"}}], son=250)
    assert s["cagri"].count("POST /api/yedekleme/calistir") == 1, s["cagri"]
    assert not re.search(r'data-y="simdi"[^>]*disabled', s["son"]) or "yedek.yedekleniyor" in s["son"]


def test_Google_KOPUKken_tur_baslatilamaz_dugme_yok_ama_google_paneline_gider():
    s = _panel({_D: [200, _d(baglanti=_g("kopuk", "invalid_grant"))]}, [{"tik": {"y": "google"}}])
    assert "SEKME google" in s["cagri"] and "POST /api/yedekleme/calistir" not in s["cagri"]


def test_KALDIR_iki_adim_confirm_YOK_ve_ikinci_tik_DELETE_atar():
    d = _d()
    s = _panel({_D: [200, d], "DELETE /api/yedekleme/kaynak/k1": [200, {"ok": True, "durum": _d(kaynaklar=[_kay("Yuki verisi", "yuki", sistem=True)])}]},
               [{"tik": {"y": "sil", "id": "k1"}}])
    assert [c for c in s["cagri"] if c.startswith("DELETE")] == [], "ilk tık kaynağı kaldırdı — onay adımı yok"
    assert "yedek.emin-misin" in s["son"] and "yedek.kaldir-not" in s["son"]
    s = _panel({_D: [200, d], "DELETE /api/yedekleme/kaynak/k1": [200, {"ok": True, "durum": _d(kaynaklar=[_kay("Yuki verisi", "yuki", sistem=True)])}]},
               [{"tik": {"y": "sil", "id": "k1"}}, {"tik": {"y": "sil", "id": "k1"}}])
    assert s["cagri"].count("DELETE /api/yedekleme/kaynak/k1") == 1
    assert ">Belgeler<" not in s["son"], "kaldırıldı ama kart durdu"


def test_KALDIR_basarisiz_olursa_SESSIZ_gecmez_kart_kalir():
    s = _panel({_D: [200, _d()], "DELETE /api/yedekleme/kaynak/k1": [500, {}]},
               [{"tik": {"y": "sil", "id": "k1"}}, {"tik": {"y": "sil", "id": "k1"}}])
    assert "yedek.kaldirilamadi" in s["son"] and ">Belgeler<" in s["son"]


def test_SAAT_kuruldu_yalani_yok_kapaliyken_kurulu_degil_kurulamadiysa_SOYLER():
    def saat(d, deger="03:30"):
        return _panel({_D: [200, _d()], _AYAR: [200, d]}, [{"yaz": {"y-saat": deger}}, {"tik": {"y": "saat"}}])["son"]
    assert "yedek.saat-kapali" in saat(_d(acik=False)) and "yedek.saat-kuruldu" not in saat(_d(acik=False))
    kurulamadi = saat(_d(zamanlama_bilgi={"kurulu": False, "sonraki": None}))
    assert "yedek.saat-kurulamadi" in kurulamadi and "yedek.saat-kuruldu" not in kurulamadi, "zamanlayıcı yokken 'kuruldu' denildi"
    assert "yedek.saat-kuruldu" in saat(_d())
    assert "yedek.saat-elle" in saat(_d(zamanlama=None), "")


def test_ACIK_onay_kutusu_ayar_yazar_basarisizsa_kutu_ESKI_duruma_doner():
    s = _panel({_D: [200, _d(acik=False)], _AYAR: [500, {}]}, [{"degis": {"id": "y-acik", "checked": True}}])
    assert s["cagri"].count("POST /api/yedekleme/ayar") == 1
    assert 'id="y-acik" checked' not in s["son"] and "yedek.kaydedilemedi" in s["son"], \
        "kayıt başarısız ama kutu yeni durumda kaldı (sunucu eskide)"


def test_HAM_hata_ekrana_cikmaz_400_detail_musteri_cumlesidir_gerisi_degil():
    def dene(kod, govde):
        return _panel({_D: [200, _d()], _CAL: [kod, govde]}, [{"tik": {"y": "simdi"}}])["son"]
    assert "yedek.ham" in dene(400, {"detail": "Yedekleme kapalı — önce panelden aç."})
    h = dene(401, {"detail": "Unauthorized"})
    assert "google.oturum-kilitli-eylem" in h and "Unauthorized" not in h
    h = dene(500, {"detail": "Traceback boom"})
    assert "yedek.baslatilamadi" in h and "Traceback" not in h
    h = dene(429, {"detail": "Rate limit exceeded: 10 per 1 minute"})
    assert "google.cok-sik" in h and "Rate limit" not in h


def test_KLASOR_ekle_hatasi_backend_cumlesini_gosterir():
    s = _panel({_D: [200, _d()], "POST /api/yedekleme/kaynak": [400, {"detail": "Bu klasör zaten ekli."}]},
               [{"yaz": {"y-yol": "C:\\x"}}, {"tik": {"y": "ekle-yol"}}])
    assert "yedek.ham" in s["son"] and "zaten ekli" in s["son"]


def test_NATIVE_secici_varsa_diyalogla_ekler_yol_yazdirmaz():
    s = _panel({_D: [200, _d()], "POST /api/yedekleme/kaynak": [200, {"ok": True, "durum": _d()}]},
               [{"tik": {"y": "ekle"}}], yukiDosya={"yol": "C:\\Belgeler"})
    assert "POST /api/yedekleme/kaynak" in s["cagri"] and 'id="y-yol"' not in s["acilis"]


def test_YER_TUTUCU_i18n_anahtardan_gelir_sabit_Linux_yolu_degil():
    h = _ac(_d())
    m = re.search(r'id="y-yol"[^>]*placeholder="([^"]*)"', h)
    assert m and m.group(1).startswith("yedek.yol-ornek"), m and m.group(1)
    assert "/ev/kullanici" not in JS.read_text(encoding="utf-8")


# ── ⑥ Yoklama formu/mesajı SİLMEZ ────────────────────────────────────────────

def test_YOKLAMA_yeniden_cizimi_saat_taslagini_ve_mesaji_KORUR():
    """Tur sürerken 2 sn'de bir çizim: eskiden yazılan saat ve "Klasör eklenemedi" mesajı kayboluyordu."""
    d = _d(calisiyor=True, canli={"yuklenen": 1, "guncellenen": 0, "bayt": 5})
    s = _panel({_D: [200, d], "POST /api/yedekleme/kaynak": [400, {"detail": "Bu klasör zaten ekli."}]},
               [{"yaz": {"y-yol": "C:\\x"}}, {"tik": {"y": "ekle-yol"}, "bekle": 30}, {"yaz": {"y-saat": "04:15"}, "bekle": 120}], son=200)
    assert s["cizimler"] > 4, "yoklama çizmedi — test bir şey ölçmüyor"
    assert s["saat"] == "04:15", f"yoklama saat alanını sildi: {s['saat']!r}"
    assert "zaten ekli" in s["son"], "yoklama mesajı sildi"


def test_DIL_degisimi_mesaji_ve_taslagi_korur():
    s = _panel({_D: [200, _d()], _CAL: [400, {"detail": "Kapalı."}]},
               [{"tik": {"y": "simdi"}}, {"yaz": {"y-saat": "05:45"}}, {"dil": True}])
    assert "Kapalı." in s["son"] and s["saat"] == "05:45"


def test_YOKLAMA_tur_bitince_durur_ve_BITTI_mesaji_yazar():
    bitis = _d(son_tur=_tur(yuklenen=7, guncellenen=1))
    s = _panel({_D: [200, _d()], _CAL: [200, {"ok": True}]}, [{"tik": {"y": "simdi"}}], son=300,
               yanitDizi={"GET " + _D: [[200, _d()], [200, _d(calisiyor=True)], [200, _d(calisiyor=True)], [200, bitis]]})
    assert "yedek.bitti" in s["son"] and '"yeni":7' in _j(s["son"])


# ── ⑦ Drive alanı ────────────────────────────────────────────────────────────

def test_DRIVE_alani_acilista_BIR_kez_okunur_kopukken_hic_sorulmaz():
    s = _panel({_D: [200, _d()], _DRIVE: [200, {"limit": 15e9, "kullanilan": 6e9}]})
    assert s["acilisCagri"].count("GET /api/yedekleme/drive-kullanim") == 1 and "yedek.drive-oran" in s["acilis"]
    s = _panel({_D: [200, _d(baglanti=_g("kopuk", "invalid_grant"))], _DRIVE: [200, {}]})
    assert "GET /api/yedekleme/drive-kullanim" not in s["acilisCagri"]
    assert "yedek.drive-yeniden-baglaninca" in s["acilis"]


def test_DRIVE_409_google_dususu_401_gibi_oturum_kilitli_DEMEZ():
    s = _panel({_D: [200, _d()], _DRIVE: [409, {"detail": "kopuk"}]})
    assert "yedek.drive-yeniden-baglaninca" in s["acilis"] and "hq.oturum-kilitli" not in s["acilis"]


def test_DRIVE_dolmak_uzere_iyi_hukmun_altina_uyari_koyar_dolu_kritik_olcu():
    h = _ac(_d(), **{_DRIVE: [200, {"limit": 15e9, "kullanilan": 14.2e9}]})
    assert "yedek.drive-dolmak-uzere" in h and "yb-olcu uyari" in h
    h = _ac(_d(), **{_DRIVE: [200, {"limit": 15e9, "kullanilan": 15e9}]})
    assert "yb-olcu kritik" in h and "yedek.drive-dolu" in h


# ── ⑧ Sözlük ve ekrandaki sözler ─────────────────────────────────────────────

def test_kullanilan_ANAHTARLAR_iki_dilde_ve_olu_anahtar_yok():
    tr, en = sozluk("tr"), sozluk("en")
    js = yorumsuz(JS.read_text(encoding="utf-8"))
    kullanilan = set(re.findall(r"'((?:yedek|google|hq|saglik)\.[a-z0-9.-]+)'", js))
    # BULUTTA/AYARLAR/Kontrol/Kuru (11-15) ayrı modülde; anahtarlarının bir kısmı ÖNEKLE kurulur
    # (`'yedek.r-neden-' + kod`). Önekle kurulan anahtar, önek JS'te geçiyorsa kullanılıyor sayılır.
    rjs = yorumsuz((FRONTEND / "js" / "yedek-rclone.js").read_text(encoding="utf-8"))
    rkul = set(re.findall(r"'(yedek\.r-[a-z0-9-]+)'", rjs))
    onekler = {k for k in rkul if k.endswith("-")}
    kullanilan |= rkul - onekler
    kullanilan |= {k for k in sozluk("tr") if any(k.startswith(o) for o in onekler)}
    eksik = [f"{d}: {k}" for k in sorted(kullanilan) for d, s in (("tr", tr), ("en", en)) if k not in s]
    assert not eksik, eksik
    yedek_anahtarlar = {k for k in tr if k.startswith("yedek.")}
    assert yedek_anahtarlar == {k for k in en if k.startswith("yedek.")}, "tr/en yedek.* anahtar kümeleri ayrışmış"
    olu = sorted(k for k in yedek_anahtarlar if k not in kullanilan)
    assert not olu, f"JS'in kullanmadığı sözlük anahtarları: {olu}"


def test_sirlarin_yedege_girmedigi_EKRANDA_soyleniyor_ve_DOGRU():
    """Eski test `"API anahtarın" in PANEL_JS` bir yorum satırını + anahtar adını yakalıyordu (boş geçiyordu).
    Burada ölçülen şey üç şey: ① cümle panelde GERÇEKTEN çizilir ② cümle iki dilde sırların adını verir
    ③ cümlenin ANLATTIĞI şey doğru — motor o dosyaları gerçekten dışlıyor."""
    h = _ac(_d())
    guven = re.search(r'<p class="yb-guven">(.*?)</p>', h, re.S)
    assert guven and "yedek.anahtar-girmez" in guven.group(1) and "yedek.silmez" in guven.group(1)
    tr, en = sozluk("tr"), sozluk("en")
    assert "API anahtar" in tr["yedek.anahtar-girmez"] and "girmez" in tr["yedek.anahtar-girmez"]
    assert "API keys" in en["yedek.anahtar-girmez"] and "Not included" in en["yedek.anahtar-girmez"]
    assert "silmez" in tr["yedek.silmez"] and "never deletes" in en["yedek.silmez"]
    from app.services.yedekleme import VARSAYILAN_ISTISNALAR
    for sir in (".env", "planner_tokens.json", "vapid_private.pem"):
        assert sir in VARSAYILAN_ISTISNALAR, f"ekranda 'girmez' deniyor ama {sir} dışlanmıyor"


def test_panel_satir_ici_stil_ve_confirm_yok_ama_olcu_cubugu_DOM_ile_boyanir():
    kod = yorumsuz(JS.read_text(encoding="utf-8"))
    assert 'style="' not in kod and "style='" not in kod and "confirm(" not in kod
    h = _ac(_d(), **{_DRIVE: [200, {"limit": 15e9, "kullanilan": 6e9}]})
    assert 'style=' not in h and 'data-oran="40"' in h


def test_panelde_ikinci_menu_YOK():
    """Panel içinde ikinci gezinme (sekme/menü) yasak — HQ menüsü tek gezinme."""
    h = _ac(_d())
    assert not re.search(r'role="tab(list)?"|<nav\b|class="[^"]*\b(sekme|tabs?)\b', h)


# ── göz tur 1 (2026-10-01) ───────────────────────────────────────────────────

def _yan_html(h):
    return re.search(r'<aside class="yb-yan">.*?</aside>', h, re.S).group(0)


APIK = _d(son_tur=_tur(hata="Drive API kapali", hata_tur="api-kapali", tam=False, teknik="accessNotConfigured"),
          kaynaklar=[_kay("Yuki verisi", "yuki", sistem=True, tur={"durum": "yarida"}), _kay(tur={"durum": "sira-gelmedi"})])


def test_goz1_1_API_KAPALIYKEN_yan_sutun_Google_icin_YESIL_demez():
    yan = _yan_html(_ac(APIK))
    assert "yedek.g-drive-kapali" in yan and "yedek.g-bagli" not in yan, "şerit kırmızı, yan sütun yeşil 'bağlı'"
    assert "yb-hap iyi" not in yan.split("Google")[-1]
    yan = _yan_html(_ac(_d(son_tur=_tur(hata="x", hata_tur="kopuk", tam=False))))
    assert "yedek.g-izin-yok" in yan and "yedek.g-bagli" not in yan
    assert "yedek.g-bagli" in _yan_html(_ac(_d())), "sağlıklı bağlantı yine 'bağlı' demeli"


def test_goz1_2_YEDEKLEME_DURMUSKEN_siradaki_yedek_vaat_edilmez():
    for d in (APIK, _d(baglanti=_g("kopuk", "invalid_grant")), _d(son_tur=_tur(hata="x", hata_tur="kopuk", tam=False))):
        yan = _yan_html(_ac(d))
        assert "yedek.saat-duruyor" in yan and "yedek.saat-sonraki" not in yan
    assert "yedek.saat-sonraki" in _yan_html(_ac(_d()))
    assert "yedek.saat-sonraki" in _yan_html(_ac(_d(son_tur=_tur(hata="x", hata_tur="ag", tam=False)))), "geçici ağ hatasında tekrar denenir"


def test_goz1_3_AG_hatasinda_serit_ile_kutu_ayni_cumleyi_tekrarlamaz_ne_yapmali_var():
    h = _ac(HALLER["hatali"][0])
    sert = re.search(r'<section class="yb-serit.*?</section>', h, re.S).group(0)
    assert "yedek.ag-sebep" in sert
    assert "yedek.ag-ne-yapmali" in h and "Yedekleme yarida kaldi" not in h


def test_goz1_4_API_KAPALIYKEN_ana_dugme_REHBER_tekrar_dene_ikincil():
    h = _ac(APIK)
    sert = re.search(r'<section class="yb-serit.*?</section>', h, re.S).group(0)
    assert 'data-y="rehber"' in sert and 'dg-birincil' in sert.split('data-y="rehber"')[0].rsplit("<button", 1)[1]
    assert 'data-y="simdi"' not in sert and 'data-y="simdi"' in h.split('class="yb-neden kritik"')[1].split('</aside>')[0].split('yb-ana')[0]


def test_goz1_5_KALDIR_onay_aciklamasi_KARTIN_ICINDE():
    s = _panel({_D: [200, _d()]}, [{"tik": {"y": "sil", "id": "k1"}}])["son"]
    kart = _kart(s, "Belgeler")
    assert "yedek.kaldir-not" in kart and "yedek.emin-misin" in kart


def test_goz1_6_SAAT_mesaji_Kaydet_in_yaninda_yan_sutunda():
    s = _panel({_D: [200, _d(acik=False)], _AYAR: [200, _d(acik=False)]},
               [{"yaz": {"y-saat": "03:30"}}, {"tik": {"y": "saat"}}])["son"]
    assert "yedek.saat-kapali" in _yan_html(s)
    assert "yedek.saat-kapali" not in re.search(r'<p id="y-mesaj" class="ak-mesaj.*?</p>', s, re.S).group(0)


def test_goz1_7_EN_AGIR_klasor_ilk_gelir_telefonda_kirmizi_ilk_ekranda():
    d = _d(son_tur=_tur(tavan_doldu=True, tam=False),
           kaynaklar=[_kay("Yuki verisi", "yuki", sistem=True), _kay("Belgeler", "k1"),
                      _kay("Fotolar", "k3", yol_var=False), _kay("Resimler", "k2", tur={"durum": "yarim", "tavan_atlanan": 3})])
    h = _ac(d)
    sira = re.findall(r"<h5>(.*?)</h5>", h)
    assert sira == ["Fotolar", "Resimler", "Yuki verisi", "Belgeler"], sira


def test_goz1_9_TURKCE_sayi_biçimi_ondalikta_virgul_binlikte_nokta_birim_bolunmez():
    h = _ac(_d(son_tur=_tur(yuklenen=1840, guncellenen=0, bayt=2_000_000_000, tavan_doldu=True, tam=False,
                            kaynaklar=[{"id": "k1", "durum": "yarim", "tavan_atlanan": 3000}]),
               kaynaklar=[_kay("Yuki verisi", "yuki", sistem=True), _kay(dosya=3402, bayt=4_100_000_000, tur={"durum": "yarim", "tavan_atlanan": 3000})]))
    assert "4,1\u00a0GB" in h and "3.402" in h and "2,0\u00a0GB" in _j(h)
    assert '"yeni":"1.840"' in _j(h) and '"n":"3.000"' in _j(h)


def test_goz1_13_KOPUKKEN_Google_paneline_TEK_giris_var():
    assert _ac(_d(baglanti=_g("kopuk", "invalid_grant"))).count('data-y="google"') == 1


def test_goz1_14_DRIVE_dolmak_uzereyken_baslik_YESIL_kalmaz():
    h = _ac(_d(), **{_DRIVE: [200, {"limit": 15e9, "kullanilan": 14.2e9}]})
    sert = re.search(r'<section class="yb-serit.*?</section>', h, re.S).group(0)
    assert "durum-isik uyari" in sert and "durum-isik iyi" not in sert and 'class="yb-serit uyari"' in sert


def test_goz1_15_SURERKEN_yedeklenen_klasorun_KALDIR_dugmesi_pasif():
    d = _d(calisiyor=True, canli={"yuklenen": 1, "guncellenen": 0, "bayt": 5},
           kaynaklar=[_kay("Yuki verisi", "yuki", sistem=True, canli={"durum": "tamam"}), _kay("Belgeler", "k1", canli={"durum": "suruyor"}),
                      _kay("Resimler", "k2", canli={"durum": "sirada"})])
    h = _ac(d)
    assert re.search(r'data-y="sil" data-id="k1"[^>]*disabled', h) and not re.search(r'data-y="sil" data-id="k2"[^>]*disabled', h)


def test_goz1_10_11_DRIVE_degeri_hep_ayni_punto_ve_kapali_ipucu_olmayan_dugmeye_gondermez():
    h = _ac(_d(), **{_DRIVE: [200, {"limit": 15e9, "kullanilan": 15e9}]})
    assert re.search(r'<span class="yb-kucuk kritik">', h) or 'class="yb-kucuk kritik"' in h
    for dil in ("tr", "en"):
        assert "Şimdi yedekle" not in sozluk(dil)["yedek.saat-not"] and "Back up now" not in sozluk(dil)["yedek.saat-not"]


def test_goz1_ag_hatasinda_saglam_baglantiya_Google_paneli_dugmesi_ONERILMEZ():
    assert 'data-y="google"' not in _yan_html(_ac(HALLER["hatali"][0]))
    assert 'data-y="google"' in _yan_html(_ac(APIK))
