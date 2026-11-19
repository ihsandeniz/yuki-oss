"""Öneri motoru + genel bildirim kapılarının mutasyon sınavı — her kapıyı bir kez bilerek kırar, testin
yakaladığını ölçer. Doğrudan koşulur (pytest toplamaz):

    venv/bin/python tests/mutasyon_gorev_onerici.py

Çıkış 0 = bütün mutasyonlar yakalandı. Dosyalar her adımdan sonra geri yüklenir.
"""
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
MOTOR = "app/services/gorev_onerici.py"
API = "app/api/gorev.py"
BILDIRIM = "app/services/gorev_bildirim.py"
SERVIS = "app/services/gorev.py"
MUTASYONLAR = [
    ("günlük tavan", MOTOR, 'if int(v.get("yazilan") or 0) >= a["gunluk"]:', "if False:"),
    ("açık öneri tavanı", MOTOR, "ACIK_AZAMI = 3", "ACIK_AZAMI = 99"),
    ("red susması", MOTOR, "RED_SUSMA = 7 * 24 * 3600", "RED_SUSMA = 0"),
    ("düşme susması", MOTOR, "DUSME_SUSMA = 24 * 3600", "DUSME_SUSMA = 0"),
    ("pencere kapısı", MOTOR, "if not _kapi.pencerede_mi(simdi):", "if False:"),
    ("tümünü durdur", MOTOR, "if self.kapali():", "if False:"),
    ("bozuk defter dolu", MOTOR, '"yazilan": 10 ** 9, "bozuk": True', '"yazilan": 0, "bozuk": True'),
    ("bozuk defter ezilmez", MOTOR, 'if v.get("bozuk"):\n            return', 'if False:\n            return'),
    ("yarım penceresi", MOTOR, "YARIM_PENCERE = 48 * 3600", "YARIM_PENCERE = 10 ** 9"),
    ("yarım nedeni", MOTOR, 'd.get("neden") not in YARIM_NEDENLERI', "False"),
    ("rutin eşiği", MOTOR, "TEKRAR_ESIGI = 3", "TEKRAR_ESIGI = 2"),
    ("süren iş", MOTOR, "(ad.devam_gid and ad.devam_gid in suren)", "False"),
    ("sessiz saat", MOTOR, "if _bildirim.sessiz_mi(datetime.fromtimestamp(simdi), a[\"sessiz\"]):", "if False:"),
    ("bildirim aralığı", MOTOR, 'if son and simdi - float(son) < a["aralik_sn"]:', "if False:"),
    ("bildirim kapalı", MOTOR, 'if not a["bildirim"]:', "if False:"),
    ("içerik bildirime çıkmaz", MOTOR, '"Yeni bir iş önerisi var — Atölye\'de ONAYLA ya da GEÇ.")',
     'sonuc["yazilan"] and self.kuyruk_liste()[-1]["istek"])'),
    ("tür sezgisi", MOTOR, "        if tur and g.get(\"id\"):", "        if g.get(\"id\"):\n            tur = tur or \"site\""),
    ("bitiş: kullanıcı durdurması", BILDIRIM, '(durum == "durdu" and neden == "durdur")', "False"),
    ("bitiş: kapalı ayar", BILDIRIM, '.strip() == "0":\n            return', '.strip() == "x":\n            return'),
    ("bitiş: sessiz saat", BILDIRIM, "if sessiz_mi(datetime.fromtimestamp(_zaman()), sessiz_aralik()):", "if False:"),
    ("bitiş: içerik", BILDIRIM, 'return f"{tur} görevi {_SONUC[durum]}"', 'return f"{kayit.get(\'ad\')} {_SONUC[durum]}"'),
    ("bitiş: hata yutulur", BILDIRIM, "        except Exception as e:\n            logger.warning(\"[bildirim]", "        except ZeroDivisionError as e:\n            logger.warning(\"[bildirim]"),
    ("bitiş: sessiz aralık bozuk", BILDIRIM, "if m and all(0 <= int(x) <= 23 for x in m.groups()):", "if m:"),
    ("bitiş: üretim bağlantısı", SERVIS, "_servis.bitis_kancasi_ekle(BitisBildirimi())", "pass"),
    ("uç dış 403", API, '    if dis:\n        raise HTTPException(403, "öneri turu yalnız bu bilgisayardan")', ""),
]


def kos() -> int:
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:warnings",
                        "-p", "no:cacheprovider", "tests/test_gorev_onerici.py", "tests/test_gorev_bildirim.py"],
                       cwd=BACKEND, capture_output=True, text=True)
    return r.returncode


def main() -> int:
    if kos() != 0:
        print("🔴 taban kırmızı — önce testleri yeşile çek")
        return 1
    kacan = []
    for ad, dosya, eski, yeni in MUTASYONLAR:
        yol = BACKEND / dosya
        asil = yol.read_text(encoding="utf-8")
        if asil.count(eski) != 1:
            print(f"🔴 {ad}: hedef metin {asil.count(eski)} kez bulundu")
            kacan.append(ad)
            continue
        try:
            yol.write_text(asil.replace(eski, yeni), encoding="utf-8")
            yakalandi = kos() != 0
        finally:
            yol.write_text(asil, encoding="utf-8")
        print(f"{'✅' if yakalandi else '🔴'} {ad}")
        if not yakalandi:
            kacan.append(ad)
    print(f"mutasyon {len(MUTASYONLAR) - len(kacan)}/{len(MUTASYONLAR)} yakalandı")
    return 1 if kacan else 0


if __name__ == "__main__":
    sys.exit(main())
