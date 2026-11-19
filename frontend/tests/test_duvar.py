"""Duvar kâğıdı — SINIF değil PİKSEL ölçer (ürün sürümü).

Çalıştırma (sunucu gerekli):
    YUKI_DATA_DIR=<geçici> backend/venv/bin/python -m uvicorn app.main:app --port 8001
    backend/venv/bin/python frontend/tests/test_duvar.py

🔴 **Bu dosyanın varlık sebebi iki ayrı kusur, ikisi de 2026-09-08'de yaşandı:**

**① Sınıf doğru, piksel yanlış.** Kişiselde `duvar-acik` sınıfı vardı, `<img>`
`.acik` sınıfındaydı, katman tam ekrandı — ve duvar HİÇ görünmüyordu, çünkü opak
arka planı içerideki kap taşıyordu. Sınıf kontrolü bunu yakalamaz.

**② Ölçüm aracı renk biçimine kör olabilir.** Ürüne taşırken ilk tarayıcım
`rgba()` arıyordu; ürünün token sistemi **`oklch()`** döndürüyor. Sonuç: her opak
kap "şeffaf" sayıldı ve araç *"duvar hiçbir noktada örtülmüyor"* dedi — ekran ise
bembeyazdı. Kusur, YEŞİL BİR TESTLE BİRLİKTE teslim edilecekti; yalnız ekran
görüntüsüne bakıldığı için yakalandı.
📏 Ders: bir ölçüm aracı "temiz" diyorsa önce **aracın o şeyi görebildiğini**
kanıtla. (Ledger'da kardeşi yazılı: *"renk regex'i oklch'te 0,0,0 verir"*.)

⚠️ `elementsFromPoint` duvar katmanını DÖNDÜRMEZ — katman `pointer-events:none`.
Bu yüzden "katmana ulaşana kadar" gibi bir döngü koşulu yazma; ilk taramam tam
bunu yaptı ve zincir `body`de bitince "engel yok" sandı.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request

from perdesiz import PERDESIZ_JS   # ilk kurulum perdesi (opak .ik-kart) duvarı örter

BASE = os.getenv("YUKI_URL", "http://127.0.0.1:8001")
VIEWPORT = {"width": 1400, "height": 900}

# Renk biçiminden BAĞIMSIZ opaklık ölçütü. Alfa yalnız `/ a` (oklch/hsl) ya da
# 4. bileşen (rgba) ile gelir; hiçbiri yoksa renk TAM OPAKTIR.
OPAK_JS = r"""
  const opak = (c) => {
    if (!c || c === 'transparent') return false;
    const egik = c.match(/\/\s*([0-9.]+%?)\s*\)/);
    if (egik) { let a = egik[1]; a = a.endsWith('%') ? parseFloat(a) / 100 : parseFloat(a); return a >= 0.98; }
    const r = c.match(/rgba?\(([^)]+)\)/);
    if (r) { const p = r[1].split(',').map(parseFloat); return p.length < 4 || p[3] >= 0.98; }
    return true;
  };
"""

TARA_JS = """() => {
  %s
  const nokta = [[innerWidth*0.5, innerHeight*0.55], [innerWidth*0.75, innerHeight*0.7]];
  const kat = document.getElementById('duvar-katman');
  const im = kat ? kat.querySelector('img') : null;
  const vd = kat ? kat.querySelector('video') : null;
  const out = { katmanVar: !!kat, engeller: [], gorselHazir: null, videoOynuyor: null };
  if (im && im.classList.contains('acik')) out.gorselHazir = im.complete && im.naturalWidth > 0;
  if (vd && vd.classList.contains('acik')) out.videoOynuyor = !vd.paused;
  for (const [x, y] of nokta) {
    for (const el of document.elementsFromPoint(x, y)) {
      /* ⚠️ `body` ve `html` DIŞARIDA — arka planları tuvalin kendisidir ve
         ÇOCUKLARININ ALTINA boyanır, yani duvar katmanını (body'nin çocuğu)
         örtemezler. İlk sürüm bunları da sayıyordu ve düzeltme doğruyken test
         kırmızı kalıyordu: yanlış pozitif, gerçek kusur kadar zararlıdır —
         bir süre sonra "zaten hep kırmızı" denip bakılmaz olur. */
      if (el === document.documentElement || el === document.body) continue;
      const bg = getComputedStyle(el).backgroundColor;
      if (opak(bg)) out.engeller.push(
        (el.id ? '#' + el.id : el.tagName.toLowerCase() + '.' +
         (el.className || '').toString().trim().split(' ')[0]) + ' ← ' + bg);
    }
  }
  return out;
}""" % OPAK_JS


def _api(yol: str, veri=None, metot="GET"):
    istek = urllib.request.Request(
        BASE + yol, method=metot,
        data=json.dumps(veri).encode() if veri is not None else None,
        headers={"Content-Type": "application/json"} if veri is not None else {})
    with urllib.request.urlopen(istek, timeout=15) as r:
        return json.loads(r.read())


def main() -> int:
    # 🔴 Bu test sunucunun GERÇEK duvar ayarını ve kitaplığını değiştiriyor. Eskiden ikisini
    # de geri koymuyordu: her koşu kullanıcının tercihini "tek duvar" ile eziyor, örnekleri
    # kitaplıkta bırakıyordu (kişisel AliceAi c41cb0a/1183976'daki kusurun ürün karşılığı,
    # 09-27). Başta okunur, sonda — hata olsa bile — geri konur.
    try:
        import playwright.sync_api  # noqa: F401 — yoksa sunucuya hiç dokunmadan çık
    except ImportError:
        print("playwright yok — test ATLANDI")
        return 0
    onceki_ayar = _api("/api/duvar/ayar")["ayar"]
    onceki_idler = {d["id"] for d in _api("/api/duvar/liste")["duvarlar"]}
    try:
        return _olc()
    finally:
        for d in _api("/api/duvar/liste")["duvarlar"]:
            if d["id"] not in onceki_idler:
                _api(f"/api/duvar/{d['id']}", metot="DELETE")
        _api("/api/duvar/ayar", onceki_ayar, "PUT")
        print("duvar ayarı ve kitaplık geri kondu")


def _olc() -> int:
    from playwright.sync_api import sync_playwright

    # Denemelik veri: ürünün kendi karakter görselleri (resim + video yolu birlikte)
    _api("/api/duvar/ornek-yukle", {}, "POST")
    liste = _api("/api/duvar/liste")
    resimler = [d for d in liste["duvarlar"] if d["tip"] == "resim"]
    if not resimler:
        print("🔴 denemelik duvar yüklenemedi — ölçüm yapılamıyor")
        return 1

    kusur = 0
    with sync_playwright() as p:
        tar = p.chromium.launch(args=["--no-sandbox"])
        sf = tar.new_page(viewport=VIEWPORT, device_scale_factor=1)
        sf.add_init_script(PERDESIZ_JS)

        # ── ① Duvar KAPALIYKEN katman görünmemeli ──────────────────────────
        _api("/api/duvar/ayar", {"mod": "kapali", "tek": None, "sekmeler": {},
                                 "perde": 55, "bulanik": 0, "sessiz": True}, "PUT")
        sf.goto(f"{BASE}/ui", wait_until="networkidle", timeout=45000)
        time.sleep(4)
        if sf.evaluate("document.body.classList.contains('duvar-acik')"):
            print("🔴 mod=kapali iken body.duvar-acik duruyor")
            kusur += 1

        # ── ② Duvar AÇIKKEN gerçekten görünmeli ───────────────────────────
        _api("/api/duvar/ayar", {"mod": "tek", "tek": resimler[0]["id"], "sekmeler": {},
                                 "perde": 55, "bulanik": 0, "sessiz": True}, "PUT")
        sf.reload(wait_until="networkidle")
        time.sleep(4)
        r = sf.evaluate(TARA_JS)
        if not r["katmanVar"]:
            print("🔴 duvar katmanı DOM'da yok")
            kusur += 1
        if r["gorselHazir"] is not True:
            print(f"🔴 görsel yüklenmedi (gorselHazir={r['gorselHazir']})")
            kusur += 1
        if r["engeller"]:
            print("🔴 duvarı örten OPAK eleman(lar):")
            for e in dict.fromkeys(r["engeller"]):
                print("   ·", e)
            kusur += 1

        # ── ③ Kendi kendini sınama: araç opak kabı GERÇEKTEN görüyor mu ────
        # Bu kapı olmasaydı "engel yok" çıktısı kanıt sayılamazdı (bkz. modül başlığı).
        # ⚠️ `setProperty(..., 'important')` ŞART: `duvar.css`'te
        # `body.duvar-acik .kabuk{background-color:transparent !important}` var ve
        # `!important` DÜZ satır içi stili EZER. İlk denemem `style.background=`
        # ile yazdı, kural onu geçersiz kıldı ve öz-sınama "araç kör" diye
        # kırmızı yandı — araç sağlamdı, MUTASYON etkisizdi.
        # 📏 Mutasyon testi yazarken: mutasyonun gerçekten uygulandığını da doğrula.
        sf.evaluate("document.querySelector('.kabuk').style"
                    ".setProperty('background-color', 'oklch(0.2 0 0)', 'important')")
        time.sleep(0.3)
        kontrol = sf.evaluate(TARA_JS)
        if not kontrol["engeller"]:
            print("🔴 ÖLÇÜM ARACI KÖR: kasten opak yapılan .kabuk'u görmedi "
                  "(oklch okunamıyor olabilir) — 'engel yok' çıktısı kanıt değil")
            kusur += 1
        sf.evaluate("document.querySelector('.kabuk').style.removeProperty('background-color')")

        tar.close()

    print("\n" + ("✅ duvar kâğıdı: 0 kusur" if not kusur else f"🔴 {kusur} kusur"))
    return 1 if kusur else 0


if __name__ == "__main__":
    sys.exit(main())
