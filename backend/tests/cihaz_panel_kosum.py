"""CİHAZLAR panelini `node` ile GERÇEK dosya üzerinde koşturan ortak zemin (DOM sahtesi).

Test dosyası DEĞİL (adı `test_` ile başlamıyor) — `test_cihaz_rafi.py` ve `test_cihaz_panel_kapisi.py` buradan beslenir.
Neden node: panelin davranışı (ağ kapalıyken pasif · çift tık = 1 POST · eşleşmeyi yoklama · süre dolunca) metin
aramayla ölçülemez; "uyari" kelimesinin kodda geçmesi ağ uyarısının GÖSTERİLDİĞİNİ kanıtlamaz (başka sınıf adında da geçer).

Senaryo (JSON): {"yanit": {"GET /api/devices/ag": [200, {...}], ...}, "adimlar": [{"op": ...}]}
Adımlar:  tikla {g, id?, aria?}  ·  yanit {url, deger}  ·  tik {n, sn}  (setInterval geri çağrısını n kez, her biri sn saniye
ileri)  ·  bekle {ms}  ·  ac  (cihazlarPanelAc)
Çıktı: {adimlar: [{html, cagri}], cagri, diyalog}
"""
from __future__ import annotations

import glob
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
DOSYA = FRONTEND / "js" / "cihazlar.js"


def node() -> str | None:
    yol = shutil.which("node")
    if yol:
        return yol
    adaylar = sorted(glob.glob(os.path.expanduser("~/.nvm/versions/node/*/bin/node")))
    return adaylar[-1] if adaylar else None


_KOSUM = r"""
const fs = require('fs');
const S = JSON.parse(process.argv[process.argv.length - 1]);
global.window = global;
const cagri = [], aralik = [], cizim = [], pano = [], govde = [];
window.yukiSistem = S.masaustu ? { yenidenBaslat() {} } : undefined;
window.yenidenBaslatCalistir = (b) => { cagri.push('YENIDEN-BASLAT'); if (b.dataset && !b.dataset.onay) b.dataset.onay = '1'; };
let ofs = 0; const gercek = Date.now.bind(Date); Date.now = () => gercek() + ofs;
global.setInterval = (f) => { aralik.push(f); return aralik.length; };
global.clearInterval = (i) => { if (i) aralik[i - 1] = null; };
window.YukiDil = { t: (k, d) => k + (d ? JSON.stringify(d) : ''), yerel: () => 'tr-TR' };
window.addEventListener = () => {};
const el = { _h: '', get innerHTML() { return this._h; }, set innerHTML(v) { this._h = v; cizim.push(v); },
  offsetParent: {}, dinle: {}, addEventListener(t, f) { this.dinle[t] = f; },
  querySelector() { return null; }, querySelectorAll() { return []; } };
global.document = { activeElement: null, hidden: false, getElementById(id) { return id === 'hq-panel-cihazlar' ? el : null; },
  createElement() { return { setAttribute() {}, select() {} }; }, body: { appendChild() {}, removeChild() {} },
  execCommand() { return true; } };
Object.defineProperty(global, 'navigator', { value: { clipboard: { writeText: async (t) => { pano.push(t); } } }, configurable: true });
const Y = S.yanit;
window.authFetch = (url, o) => { const m = (o && o.method) || 'GET'; cagri.push(m + ' ' + url); if (o && o.body) govde.push(m + ' ' + url + ' ' + o.body);
  let c = Y[m + ' ' + url] || Y[url] || [404, {}];
  if (c === 'ag-hatasi') return Promise.reject(new Error('Failed to fetch'));
  return new Promise(r => setTimeout(() => r({ status: c[0], ok: c[0] >= 200 && c[0] < 300, json: async () => c[1] }), 5)); };
window.hqGoto = (t, i) => cagri.push('GOTO ' + t + ' ' + i);
eval(fs.readFileSync(S.dosya, 'utf8'));
const bekle = ms => new Promise(r => setTimeout(r, ms));
const dugme = (g, id, aria) => ({ getAttribute: a => a === 'data-cz' ? g : a === 'data-id' ? (id || null) : a === 'aria-checked' ? (aria || null) : null, disabled: false,
  dataset: {}, classList: { add(c) { cagri.push('CLASS ' + c); }, remove() {} }, set textContent(v) { cagri.push('TEXT ' + v); }, get textContent() { return 'eski'; } });
(async () => {
  const adimlar = [];
  for (const a of S.adimlar) {
    if (a.op === 'ac') { window.cihazlarPanelAc(); await bekle(a.ms || 120); }
    else if (a.op === 'tikla') { for (let i = 0; i < (a.kez || 1); i++) el.dinle.click({ target: { closest: () => dugme(a.g, a.id, a.aria) } }); await bekle(a.ms || 100); }
    else if (a.op === 'yanit') { Y[a.url] = a.deger; }
    else if (a.op === 'tik') { for (let i = 0; i < a.n; i++) { ofs += (a.sn || 1) * 1000; for (const f of aralik.slice()) if (f) f(); await bekle(15); } await bekle(60); }
    else if (a.op === 'bekle') await bekle(a.ms);
    else if (a.op === 'gizle') el.offsetParent = null;
    adimlar.push({ html: el.innerHTML, cagri: cagri.slice() });
  }
  console.log(JSON.stringify({ adimlar, cagri, pano, govde, cizim: cizim.length }));
})();
"""


def kos(senaryo: dict) -> dict:
    yol = node()
    if not yol:
        pytest.skip("node yok — panel davranışı ölçülemedi")
    senaryo = {"dosya": str(DOSYA), **senaryo}
    r = subprocess.run([yol, "-e", _KOSUM, json.dumps(senaryo)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout.strip().splitlines()[-1])


# ── ortak sahte cevaplar ─────────────────────────────────────────────────────

_SUNUCU = {"port": 8001, "yerel_ip": "192.168.1.104", "uyari": None, "ortamdan": False, "kilit_dustu": False}
# Sunucunun `ag_durum` hâlleri (backend/app/services/ag_ayari.py::durum_ozeti). Panel YALNIZ bunlara bakar.
AG_ACIK = {**_SUNUCU, "host": "0.0.0.0", "ws_adres": "ws://192.168.1.104:8001/ws/agent", "agda_erisilebilir": True,
           "ag_ayari": True, "ag_durum": "acik-dinliyor", "dinleniyor": True, "kilit_kurulu": True, "yeniden_baslat_gerek": False}
AG_KAPALI = {**_SUNUCU, "host": "127.0.0.1", "ws_adres": "ws://127.0.0.1:8001/ws/agent", "agda_erisilebilir": False, "uyari": "x",
             "ag_ayari": False, "ag_durum": "kapali", "dinleniyor": False, "kilit_kurulu": True, "yeniden_baslat_gerek": False}
AG_KILITSIZ = {**AG_KAPALI, "kilit_kurulu": False}
AG_BEKLIYOR = {**AG_KAPALI, "ag_ayari": True, "ag_durum": "acik-bekliyor", "yeniden_baslat_gerek": True}
AG_ULASILAMIYOR = {**AG_ACIK, "ag_durum": "acik-ulasilamiyor", "dinleniyor": False}
AG_KAPANIS = {**AG_ACIK, "ag_ayari": False, "ag_durum": "kapanis-bekliyor", "yeniden_baslat_gerek": True}
KOD = {"kod": "K7MQ4X2P", "omur_sn": 300, "adres": "ws://192.168.1.104:8001/ws/agent",
       "baglanti": "ws://192.168.1.104:8001/ws/agent?eslestirme=K7MQ4X2P", "ag": AG_ACIK}
C1 = {"id": "a1", "ad": "ofis-pc", "eklendi": 1.0, "son_gorulme": 2.0, "bagli": True}
C2 = {"id": "b2", "ad": "mutfak-laptop", "eklendi": 1.0, "son_gorulme": None, "bagli": False}
C3 = {"id": "c3", "ad": "yeni-pc", "eklendi": 5.0, "son_gorulme": 5.0, "bagli": True}

AG = "GET /api/devices/ag"
LISTE = "GET /api/devices/eslestirilmis"
PUT_AG = "PUT /api/devices/ag"
POST_KOD = "POST /api/devices/eslestirme"
DEL_KOD = "DELETE /api/devices/eslestirme"


def yanit(ag=AG_ACIK, liste=(C1, C2), **ek) -> dict:
    d = {AG: [200, ag], LISTE: [200, list(liste)], POST_KOD: [200, KOD], DEL_KOD: [200, {"ok": True}]}
    d.update(ek)
    return d
