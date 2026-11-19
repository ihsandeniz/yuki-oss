"""Mutasyon turu — kamera görüşü + ses kimliği koruma kapıları.

Her kapı tek tek bilerek kırılır, ilgili test koşulur; test KIRMIZI olmalı (mutasyon yakalandı).
Dosya her mutasyondan sonra geri yazılır. Çalıştırma (backend/ içinden):
    python tests/mutasyon_gorus.py          # çıkış 0 = hepsi yakalandı
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parents[2]
BE = KOK / "backend"
PY = sys.executable

# (ad, dosya, eski, yeni, koşucu, test seçici)
MUTASYONLAR = [
    ("bayrak HTTP 404", "backend/app/api/gorus_api.py",
     'raise HTTPException(status_code=404, detail="Not Found")', "pass", "py", "tests/test_gorus.py -k kapaliyken_her_uc"),
    ("bayrak WS 4404", "backend/app/api/gorus_api.py",
     'if not bayrak_acik():\n        return 4404', 'if False:\n        return 4404', "py", "tests/test_gorus.py -k kapaliyken_ws"),
    ("config bayrağı önce", "backend/app/api/gorus_api.py",
     'if deger is not None:\n        return bool(deger)', 'if False:\n        return bool(deger)', "py", "tests/test_gorus.py -k config_bayragi"),
    ("rıza yalnız yerel", "backend/app/api/gorus_api.py",
     'if not loopback_istemci(request.client.host if request.client else None):\n        raise HTTPException(status_code=403',
     'if False:\n        raise HTTPException(status_code=403', "py", "tests/test_gorus.py -k uzaktan_riza"),
    ("WS yalnız yerel", "backend/app/api/gorus_api.py",
     'if not loopback_istemci(ws.client.host if ws.client else None):', 'if False:', "py", "tests/test_gorus.py -k uzaktan_ws"),
    ("WS erişim anahtarı", "backend/app/api/gorus_api.py",
     'return 4401, "Unauthorized"', 'pass', "py", "tests/test_gorus.py -k token_yanlissa"),
    ("WS rıza (bağlanırken)", "backend/app/api/gorus_api.py",
     'if not biyometrik_riza.var_mi("gorus"):\n        return 4409', 'if False:\n        return 4409', "py", "tests/test_gorus.py -k riza_yokken_ws"),
    ("WS rıza (her karede)", "backend/app/api/gorus_api.py",
     'if not bayrak_acik() or not biyometrik_riza.var_mi("gorus"):\n                await ws.close',
     'if False:\n                await ws.close', "py", "tests/test_gorus.py -k geri_cekilince_ws"),
    ("bakış rıza 409", "backend/app/api/gorus_api.py",
     'raise HTTPException(status_code=409, detail="Kamera görüşü için rıza verilmedi")', "pass", "py", "tests/test_gorus.py -k riza_yokken_bak"),
    ("rıza açık onay", "backend/app/api/gorus_api.py",
     'if not g.kabul:\n        raise HTTPException(status_code=400, detail="Rıza için açık onay gerekir")\n    try:\n        biyometrik_riza.ver("gorus"',
     'if False:\n        raise HTTPException(status_code=400, detail="Rıza için açık onay gerekir")\n    try:\n        biyometrik_riza.ver("gorus"',
     "py", "tests/test_gorus.py -k kabul_false"),
    ("rıza metin sürümü (ver)", "backend/app/services/biyometrik_riza.py",
     "if surum != SURUM[ozellik]:", "if False:", "py", "tests/test_gorus.py -k eski_surumle"),
    ("rıza metin sürümü (okuma)", "backend/app/services/biyometrik_riza.py",
     'kayit.get("surum") == SURUM[ozellik] and ', "", "py", "tests/test_gorus.py -k surumu_degisirse"),
    ("rıza dosyası 600", "backend/app/services/biyometrik_riza.py",
     "os.O_TRUNC, 0o600)", "os.O_TRUNC, 0o644)", "py", "tests/test_gorus.py -k ilk_yazimda_600"),
    ("model adresi yalnız loopback", "backend/app/services/gorus_bak.py",
     "    return ip.is_loopback\n\n\ndef _adres_denetle", "    return True\n\n\ndef _adres_denetle", "py", "tests/test_gorus.py -k yerel_adres_mi"),
    ("kare istemeden önce adres", "backend/app/services/gorus_bak.py",
     "            _adres_denetle()              # kareyi", "            pass              # kareyi", "py", "tests/test_gorus.py -k kare_hic_istenmez"),
    ("model durumu bulut adrese gitmez", "backend/app/services/gorus_bak.py",
     'if not yerel_adres_mi(url):\n        return {"hazir": False', 'if False:\n        return {"hazir": False', "py",
     "tests/test_gorus.py -k bulut_adresine_istek"),
    ("JPEG kuyruğu", "backend/app/services/gorus_bak.py",
     ' and veri[-2:] == b"\\xff\\xd9"', "", "py", "tests/test_gorus.py -k kare_gecerli"),
    ("bekleyen yoksa kare tutulmaz", "backend/app/services/gorus_bak.py",
     "    if not _bekleyenler:\n        return\n    for f in _bekleyenler:",
     "    if not _bekleyenler:\n        _bekleyenler.append(veri)\n        return\n    for f in _bekleyenler:", "py",
     "tests/test_gorus.py -k bekleyen_yokken"),
    ("gövde gönderimden sonra temizlenir", "backend/app/services/gorus_bak.py",
     "        govde.clear()", "        pass", "py", "tests/test_gorus.py -k bak_yerel_modelle"),
    ("araç rıza", "backend/app/services/tools/gorus_tools.py",
     'if not biyometrik_riza.var_mi("gorus"):', "if False:", "py", "tests/test_gorus.py -k arac_kapali"),
    ("varlık: tek kare geldi yapmaz", "backend/app/services/gorus_varlik.py",
     "if self._ardisik >= GEL_KARE:", "if self._ardisik >= 1:", "py", "tests/test_gorus_varlik.py -k tek_yanlis"),
    ("varlık: histerezis", "backend/app/services/gorus_varlik.py",
     "t - self._son_yuz >= YOK_SN", "t - self._son_yuz >= 0", "py", "tests/test_gorus_varlik.py -k kisa_kayip"),
    ("selam süreç tavanı", "backend/app/services/gorus_varlik.py",
     "if not self.defter.izin_ver(t):\n            return []", "if False:\n            return []", "py",
     "tests/test_gorus_varlik.py -k tavani_surec"),
    ("selam yalnız adla", "backend/app/services/gorus_varlik.py",
     "if not ad or self.durum", "if self.durum", "py", "tests/test_gorus_varlik.py -k yalniz_adla"),
    ("GORUS_SES=0 susturur", "backend/app/services/gorus_ses.py",
     'if not ses_acik():\n            self.sayac["kapali"]', 'if False:\n            self.sayac["kapali"]', "py",
     "tests/test_gorus_varlik.py -k ses_kapali"),
    ("ses: bayrak 404", "backend/app/api/ses_kimlik_api.py",
     'raise HTTPException(status_code=404, detail="Not Found")', "pass", "py", "tests/test_ses_kimlik.py -k kapaliyken_her_uc"),
    ("ses: yalnız yerel", "backend/app/api/ses_kimlik_api.py",
     "if not loopback_istemci(", "if False and not loopback_istemci(", "py", "tests/test_ses_kimlik.py -k uzaktan"),
    ("ses: kayıt rıza 409", "backend/app/api/ses_kimlik_api.py",
     'raise HTTPException(status_code=409, detail="Ses kimliği için rıza verilmedi")', "pass", "py",
     "tests/test_ses_kimlik.py -k rizasiz_kayit"),
    ("ses: geri çekince iz silinir", "backend/app/api/ses_kimlik_api.py",
     "    ses_kimlik.riza_geri_cekildi()\n", "", "py", "tests/test_ses_kimlik.py -k ses_izi_silinir"),
    ("ses: doğrulama rıza ister", "backend/app/services/ses_kimlik.py",
     "if not bayrak_acik() or not _riza_var():\n        return None", "if not bayrak_acik():\n        return None", "py",
     "tests/test_ses_kimlik.py -k rizasiz_dogrula"),
    ("ses: kapalıyken model yüklemez", "backend/app/services/ses_kimlik.py",
     "if not bayrak_acik() or not _riza_var():\n        return None", "if False:\n        return None", "py",
     "tests/test_ses_kimlik.py -k kapaliyken_dogrula"),
    ("ses: kaydet rıza ister", "backend/app/services/ses_kimlik.py",
     "if not bayrak_acik() or not _riza_var():\n        raise RizaYok", "if False:\n        raise RizaYok", "py",
     "tests/test_ses_kimlik.py -k dogrudan_cagrida"),
    ("ses: iz dosyası 600", "backend/app/services/ses_kimlik.py",
     "    os.chmod(yol, 0o600)\n    _onbellek_temizle()", "    os.chmod(yol, 0o644)\n    _onbellek_temizle()", "py",
     "tests/test_ses_kimlik.py -k yalniz_gomme"),
    ("ses: sessizlik konuşma sayılmaz", "backend/app/services/ses_kimlik.py",
     "esik = max(0.01, 0.2 * float(np.percentile(rms, 95)))", "esik = -1.0", "py", "tests/test_ses_kimlik.py -k sessizlik"),
    ("ses: başka model izi", "backend/app/services/ses_kimlik.py",
     'if d.get("model") != MODEL_ADI or ', "if ", "py", "tests/test_ses_kimlik.py -k baska_model"),
    ("ses: klip boyutu", "backend/app/api/ses_kimlik_api.py",
     "if len(veri) > EN_COK_BAYT:", "if False:", "py", "tests/test_ses_kimlik.py -k buyuk_klip"),
    ("JS: gizli sekmede kamera kapanır", "frontend/js/gorus.js",
     "if (gizliMs >= GIZLI_SINIR_MS) { durdur('gizli'); return; }", "", "node", "frontend/tests/test_gorus.mjs"),
    ("JS: geri basınç", "frontend/js/gorus.js",
     "|| bekliyor || !video) return;", "|| !video) return;", "node", "frontend/tests/test_gorus.mjs"),
    ("JS: 4409 → riza nedeni", "frontend/js/gorus.js",
     "4409: 'riza', ", "", "node", "frontend/tests/test_gorus.mjs"),
    ("JS: kamera ses istemez", "frontend/js/gorus.js",
     "{ video: { width: 640, height: 480 }, audio: false }", "{ video: { width: 640, height: 480 }, audio: true }", "node",
     "frontend/tests/test_gorus.mjs"),
    ("UI: kutusuz onay yok", "frontend/js/gorus-panel.js",
     "onay.disabled = true; ", "", "pw", "frontend/tests/test_gorus_panel.py -k gorus_riza_akisi"),
    ("UI: Esc istek göndermez", "frontend/js/gorus-panel.js",
     "if (e.key === 'Escape') { e.preventDefault(); bitir(false); }", "if (e.key === 'Escape') { e.preventDefault(); bitir(true); }",
     "pw", "frontend/tests/test_gorus_panel.py -k gorus_riza_akisi"),
    ("UI: 404 ise kart yok", "frontend/js/gorus-panel.js",
     "if (s[0].ok) kapsayici.appendChild(gorusKarti(s[0].veri));", "kapsayici.appendChild(gorusKarti(s[0].veri || {}));",
     "pw", "frontend/tests/test_gorus_panel.py -k kapaliyken_panel"),
    ("UI: geri çekince kamera durur", "frontend/js/gorus-panel.js",
     "      if (istemci) istemci.durdur();\n      json('/api/gorus/riza', 'DELETE')", "      json('/api/gorus/riza', 'DELETE')",
     "pw", "frontend/tests/test_gorus_panel.py -k gorus_riza_akisi"),
]


def _kos(kosucu: str, secici: str) -> int:
    if kosucu == "node":
        return _zamanli(["node", "--test", str(KOK / secici)], KOK)
    yol, *ek = secici.split(" ")
    cwd = BE if kosucu == "py" else KOK
    return _zamanli([PY, "-m", "pytest", "-q", "-x", "-p", "no:warnings", "-p", "no:cacheprovider", yol, *ek], cwd)


def _zamanli(komut: list[str], cwd: Path) -> int:
    """Asılan test tur'u kilitlemesin: zaman aşımı ayrı raporlanır (yakalandı sayılmaz)."""
    try:
        return subprocess.run(komut, cwd=cwd, capture_output=True, timeout=120).returncode
    except subprocess.TimeoutExpired:
        return -999


YEDEK = Path(__file__).with_suffix(".yedek")


def _yarim_kalani_geri_yaz() -> None:
    """Önceki tur öldürüldüyse (finally koşmaz) mutasyonlu dosyayı yedekten geri yaz."""
    if YEDEK.exists():
        hedef, _, icerik = YEDEK.read_text(encoding="utf-8").partition("\n")
        (KOK / hedef).write_text(icerik, encoding="utf-8")
        YEDEK.unlink()
        print(f"↩️  yarım kalan mutasyon geri yazıldı: {hedef}")


def main() -> int:
    _yarim_kalani_geri_yaz()
    kacan = []
    for ad, dosya, eski, yeni, kosucu, secici in MUTASYONLAR:
        yol = KOK / dosya
        asil = yol.read_text(encoding="utf-8")
        if asil.count(eski) != 1:
            print(f"⚠️  {ad}: hedef metin {asil.count(eski)} kez bulundu (1 olmalı)")
            kacan.append(ad)
            continue
        YEDEK.write_text(dosya + "\n" + asil, encoding="utf-8")
        try:
            yol.write_text(asil.replace(eski, yeni), encoding="utf-8")
            kod = _kos(kosucu, secici)
        finally:
            yol.write_text(asil, encoding="utf-8")
            YEDEK.unlink(missing_ok=True)
        if kod == -999:
            print(f"🔴 ASILDI  {ad} (test 120 sn'de bitmedi)")
            kacan.append(ad)
        elif kod == 0:
            print(f"🔴 KAÇTI   {ad}")
            kacan.append(ad)
        else:
            print(f"🟢 yakalandı {ad}")
    print(f"\nyakalandı {len(MUTASYONLAR) - len(kacan)} · kaçtı {len(kacan)}")
    return 1 if kacan else 0


if __name__ == "__main__":
    raise SystemExit(main())
