"""F2 doğruluk taşıması — mutasyon sınavı: her koruma kapısı bilerek kırılır, test yakalamalı.

Koşum: backend/ içinde `python tests/mutasyon_f2_dogruluk.py` (pytest toplamaz: ad test_ ile başlamaz).
Her mutasyon dosyayı değiştirir, ilgili testi koşar, dosyayı geri yazar. Çıkış 0 = hepsi yakalandı.
"""
import subprocess
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
FRONT = KOK.parent / "frontend"

M = [
    ("M1 hafıza: içerik değişince vektör yazılmaz", KOK / "app/services/memory.py",
     'sets.append(f"embedding = ${len(params)}::vector")', "pass",
     "tests/test_hafiza_guncelleme_vektor.py"),
    ("M2 hafıza: gömme düşünce eski vektörle yazılır", KOK / "app/services/memory.py",
     "log.error(\"Anı güncellemesinde gömme başarısız, güncelleme yapılmadı: %s\", e)\n                return False",
     "vec_str = None", "tests/test_hafiza_guncelleme_vektor.py"),
    ("M3 bütçe: gün UTC'den", KOK / "app/api/todo.py",
     "    return datetime.now().date()", "    return datetime.now(timezone.utc).date()",
     "tests/test_butce_yerel_gun.py"),
    ("M5 pencere: başka mesaj yutulur", KOK / "app/api/websocket.py",
     "        bekleyen.append(veri)\n    return orijinal, False", "        pass\n    return orijinal, False",
     "tests/test_ses_duzenleme_penceresi.py"),
    ("M5b pencere: ikinci ses karesi yutulur", KOK / "app/api/websocket.py",
     "        if not (isinstance(veri, dict) and veri.get(\"text\")):\n            bekleyen.append(veri)",
     "        if not (isinstance(veri, dict) and veri.get(\"text\")):\n            pass",
     "tests/test_ses_duzenleme_penceresi.py"),
    ("M6 pencere: DURDUR yok sayılır", KOK / "app/api/websocket.py",
     "        if tip == \"cancel\":\n            return orijinal, True", "        if tip == \"cancel\":\n            return orijinal, False",
     "tests/test_ses_duzenleme_penceresi.py"),
    ("M7 onay payı sıfır", KOK / "app/services/tools/approval_gate.py",
     "        return float(APPROVAL_TIMEOUT_SECONDS)\n    return 0.0", "        return 0.0\n    return 0.0",
     "tests/test_arac_onay_payi.py"),
    ("M8 Anthropic yolu sabit 10 sn", KOK / "app/services/llm.py",
     "timeout=arac_suresi(tu.name))", "timeout=10.0)", "tests/test_arac_onay_payi.py"),
    ("M9 harita: satır içi opaklık 1", FRONT / "js/map-engine.js",
     "document.getElementById('leaflet-map').style.opacity = '';", "document.getElementById('leaflet-map').style.opacity = '1';",
     str(FRONT / "tests/test_harita_3d_opaklik.py")),
    ("M10 rutin: hafta tek harfe düşer", KOK / "app/services/scheduler.py",
     '    ("hafta", "weeks"), ("week", "weeks"),\n    ("ay", None), ("month", None), ("yıl", None), ("yil", None), ("year", None),\n',
     "", "tests/test_rutin_hafta_ay.py"),
    ("M11 rutin: hafta gün katına çevrilmez", KOK / "app/services/scheduler.py",
     '            field, n = "days", n * 7', '            field, n = "days", n', "tests/test_rutin_hafta_ay.py"),
    ("M12 todo: 2 haftada klonlanmaz", KOK / "app/services/todo_store.py",
     '    if repeat == "biweekly":\n        return due + timedelta(weeks=2)\n', "", "tests/test_todo_tekrar_turleri.py"),
    ("M13 todo: yıllık klonlanmaz", KOK / "app/services/todo_store.py",
     '    if repeat == "yearly":', '    if repeat == "yillik-yok":', "tests/test_todo_tekrar_turleri.py"),
    ("M14 todo: Yuki aracı klonlamaz", KOK / "app/services/tools/todo_tools.py",
     "            await _clone_recurring(row)", "            pass", "tests/test_todo_tekrar_turleri.py"),
    ("M15 todo: PG ucu eski kural", KOK / "app/api/todo.py",
     'todo_store.sonraki_tarih(due, row["repeat"] or "none")', 'todo_store.sonraki_tarih(due, "daily")',
     "tests/test_todo_tekrar_turleri.py"),
]


def main() -> int:
    kacan = 0
    for ad, yol, eski, yeni, test in M:
        metin = yol.read_text("utf-8")
        if metin.count(eski) != 1:
            print(f"?? {ad}: hedef metin {metin.count(eski)} kez bulundu"); kacan += 1; continue
        try:
            yol.write_text(metin.replace(eski, yeni, 1), "utf-8")
            r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", test],
                               cwd=KOK, capture_output=True, text=True, timeout=120)
        finally:
            yol.write_text(metin, "utf-8")
        ok = r.returncode != 0
        kacan += not ok
        print(("YAKALANDI " if ok else "KAÇTI     ") + ad)
    print(f"mutasyon: {len(M) - kacan}/{len(M)} yakalandı")
    return 1 if kacan else 0


if __name__ == "__main__":
    sys.exit(main())
