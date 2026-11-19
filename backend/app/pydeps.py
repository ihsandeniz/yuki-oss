"""İndirilen Python paket ağaçlarını (`pydeps`) `sys.path`'e bağla.

🔑 NEDEN VAR ( Dalga 2, 2026-09-05):

Yüz tanıma modeli `model-manager.js` katmanıyla inebiliyor, ama modeli OKUYACAK
Python paketleri (`insightface` + `onnx` + `scikit-image` zinciri) kutuda yok.
Onları `pybundle`'a koymak paketi ~64 MB (indirme) büyütürdü ve bu yük **yüz
tanımayı hiç açmayan kullanıcıya da** giderdi. geliştirici kararı (B): kütüphane de
talep üzerine insin. Electron indirilen ağacın yolunu `YUKI_PYDEPS` ile geçirir,
burası `sys.path`'e bağlar.

⚠️ **SONA ekleniyor, başa DEĞİL.** İndirilen ağaç kutunun kendi paketlerini
(numpy · onnxruntime · opencv) gölgelememeli — kutudaki sürüm ürünün test
edildiği sürümdür. Ledger'da kayıtlı tuzağın aynısı: *pybundle python'u
`~/.local`'ı kendi site-packages'ından ÖNCE görüyor; `PYTHONNOUSERSITE=1`
olmadan bundle testi `cryptography` 50.0.0 kuruluyken 46.0.6 raporlamıştı.*
Sıra yanlışsa hata **çok sonra**, anlaşılmaz bir yerde çıkar.

⚠️ **Bu modül ASLA yükseltmez (raise).** Açılış yolundadır: bozuk bir ortam
değişkeni yüzünden uygulama açılmamalı. Sorun sessizce yutulmaz da — `durum()`
neyin neden atlandığını **veri olarak** taşır (bkz. `kullanilabilir()`).
"""
from __future__ import annotations

import importlib
import importlib.util
import os
import sys
from pathlib import Path

ENV = "YUKI_PYDEPS"

# Son `kur()` çağrısının sonucu — dürüst bildirim için saklanır.
_baglanan: list[str] = []
_atlanan: list[tuple[str, str]] = []   # (yol, sebep)


def _dolu(p: Path) -> bool:
    """Var olmak yetmez, DOLU olmalı.

    Boş dizin, yarıda kalmış bir indirmenin artığı olabilir; onu `sys.path`'e
    eklemek "kütüphane kurulu" yanılsaması üretir ve hata import anına ertelenir.
    (Aynı kural `electron/model-manager.js::_dolu` içinde de var — orada
    2026-09-05'te boş arşivin "kuruldu" sayılmasına yol açmıştı.)
    """
    try:
        return p.is_dir() and any(p.iterdir())
    except OSError:
        return False


def kur(deger: str | None = None, *, sifirla: bool = False) -> list[str]:
    """`YUKI_PYDEPS`'teki dizinleri `sys.path`'in SONUNA ekler.

    Birden çok kez çağrılabilir: kullanıcı uygulama **açıkken** kütüphaneyi
    indirdiğinde yeniden bağlanır (ölçüldü — yeniden başlatma gerekmiyor).

    ⚠️ Kayıt **birikir**, sıfırlanmaz. İlk sürümü her çağrıda `durum()`'u
    sıfırlıyordu: açılışta *"dizin yok"* yazan kayıt, indirmeden sonraki ikinci
    çağrıda silinip **hiç olmamış** gibi görünüyordu. Bir arıza tablosunun geçmişi
    silmesi, arızayı gizlemesidir. Bilerek sıfırlamak için `sifirla=True`.

    Args:
        deger: `os.pathsep` ile ayrılmış dizin listesi. Yoksa ortamdan okunur.
        sifirla: önceki kaydı temizle (varsayılan: birikir).
    Returns:
        Bu çağrıda fiilen eklenen dizinler (sırayla).
    """
    global _baglanan, _atlanan
    if sifirla:
        _baglanan, _atlanan = [], []

    ham = deger if deger is not None else os.getenv(ENV, "")
    if not ham.strip():
        return []

    eklenen_bu_cagri: list[str] = []

    for parca in ham.split(os.pathsep):
        yol = parca.strip()
        if not yol:
            continue
        try:
            p = Path(yol).expanduser()
        except (OSError, ValueError) as e:                  # pragma: no cover
            _atlanan.append((yol, f"geçersiz yol: {e}"))
            continue

        if not p.exists():
            _atlanan.append((yol, "dizin yok (kütüphane inmemiş)"))
            continue
        if not p.is_dir():
            # Sebep DOĞRU olmalı: dosyaya "boş dizin" demek, sonraki hata
            # ayıklamayı yanlış yere gönderir. Yanlış teşhis, teşhissizlikten kötü.
            _atlanan.append((yol, "dizin değil (dosya gösterilmiş)"))
            continue
        if not _dolu(p):
            _atlanan.append((yol, "dizin BOŞ (yarım kalmış indirme)"))
            continue

        mutlak = str(p.resolve())
        if mutlak in sys.path:
            _atlanan.append((yol, "zaten sys.path'te"))
            continue

        sys.path.append(mutlak)     # ← SONA. Kutunun paketleri kazanmalı.
        _baglanan.append(mutlak)
        eklenen_bu_cagri.append(mutlak)

    if eklenen_bu_cagri:
        # Çalışma zamanında `sys.path` değiştiğinde import mekanizmasının
        # önbelleği tazelenmelidir (Python belgelerinin açık şartı). Sondamızda
        # bayatlık ÜRETİLEMEDİ, ama sözleşme bu ve maliyeti yok — "bende olmadı"
        # bir garanti değil, yalnız bir gözlem.
        importlib.invalidate_caches()

    return eklenen_bu_cagri


#: `models-cache` içinde pydeps ağaçlarının kökü. Electron `extractTo` ile
#: buraya açar (`electron/models-manifest.json` → `"extractTo": "pydeps/face"`).
KOK_ALT_YOL = ("models-cache", "pydeps")


def kesfet() -> list[str]:
    """Diskte **fiilen duran** pydeps ağaçlarını bul.

    🔑 NEDEN VAR: `YUKI_PYDEPS` backend süreci **başlarken** hesaplanır
    (`electron/uygulama.js:442` → `modelManager.pydepsDirs()`) ve o an yalnız
    ZATEN KURULU olanları listeler. Kullanıcı uygulama **açıkken** kütüphaneyi
    indirirse o değişken boş kalır; `kur()`'u tekrar çağırmak hiçbir işe yaramaz.
    Eksik olan halka buydu: mekanizma çalışıyordu ama devreye alan uç yoktu.

    ⚠️ **Yol dışarıdan ALINMAZ, burada TÜRETİLİR.** Bir uca "şu dizini
    `sys.path`'e ekle" dedirtmek, uzaktan kod çalıştırma kapısı açmaktır —
    o dizine yazabilen herkes `import` edilen her adı ele geçirir. Bu yüzden
    yalnızca Electron'un açtığı bilinen kök taranır.
    """
    kok = Path(os.getenv("YUKI_DATA_DIR") or ".").expanduser()
    for parca in KOK_ALT_YOL:
        kok = kok / parca
    if not kok.is_dir():
        return []
    try:
        return sorted(str(p.resolve()) for p in kok.iterdir() if _dolu(p))
    except OSError as e:                                    # pragma: no cover
        _atlanan.append((str(kok), f"taranamadı: {e}"))
        return []


def tazele() -> dict:
    """Ortam + diskteki ağaçları yeniden bağla — indirme bittikten sonra çağrılır.

    `kur()` gibi **asla yükseltmez**. Dönen sözlük ne olduğunu veri olarak taşır;
    çağıran uç bunu kullanıcıya gösterebilir.

    ⚠️ Yeni bağlanan bir ağaç varsa modül önbelleğinin tazelenmesi yetmez:
    `insightface_havuzu` daha önce "kütüphane yok" diye reddetmiş olabilir ve
    kurulmuş bir örneği bayat yollara tutunuyor olabilir. Onu da düşürüyoruz —
    bu, "indirdim ama hâlâ çalışmıyor" şikâyetinin tam karşılığı.
    """
    onceki = set(_baglanan)
    eklenen = kur()                       # ortamdan (YUKI_PYDEPS)
    for yol in kesfet():                  # diskten (uygulama açıkken inen)
        eklenen += kur(yol)

    if eklenen:
        try:
            from app.services import insightface_havuzu
            insightface_havuzu.unut()
        except Exception:                 # pragma: no cover - servis yoksa sorun değil
            pass

    return {
        "eklenen": eklenen,
        "zaten_bagliydi": sorted(onceki),
        "durum": durum(),
    }


def durum() -> dict:
    """Son `kur()` çağrısının sonucu — günlüğe/uca basılabilir veri."""
    return {
        "baglanan": list(_baglanan),
        "atlanan": [{"yol": y, "sebep": s} for y, s in _atlanan],
    }


def kullanilabilir(*moduller: str) -> tuple[bool, str | None]:
    """Bu modüller import edilebilir mi? **Import ETMEDEN** bakar.

    📏 Ledger dersi (`ui/yetenek-sorusu-hata-koduyla-sorulmaz`): bir yeteneğin
    varlığı 4xx/5xx ile sorulmaz — tarayıcı her hata kodu için kendi konsol
    satırını yazar ve "özellik yok" ile "sistem bozuk" ayırt edilemez hâle gelir.
    Yetenek **veri** olarak sorulur: `(available, unavailable_reason)`.

    `find_spec` kullanılır çünkü gerçek import 300 MB'lık ağacı belleğe alır ve
    yan etki üretir; burada sorulan tek şey "var mı".
    """
    eksik = []
    for m in moduller:
        try:
            if importlib.util.find_spec(m) is None:
                eksik.append(m)
        except (ImportError, ValueError):
            eksik.append(m)
    if not eksik:
        return True, None
    # 🔴 Bu cümle KULLANICIYA gidiyor: `/api/pydeps/status` → `faces.js` ve
    #    `settings_api` → AYAR satırları. Blok 6B'de ölçüldü — GÜVENLİK odası
    #    İngilizce'ye alındığında ekranda kalan dört Türkçe kalemden biri
    #    buydu. Modül ADI çevrilmez (`insightface`), cümle çevrilir.
    #    İçe aktarma fonksiyonun içinde: `pydeps` çok erken yükleniyor ve
    #    `app.mesajlar` → `app.config` zincirini açılış sırasına sokmanın
    #    bir sebebi yok.
    from app.mesajlar import M

    return False, M("pydeps.eksik", moduller=", ".join(eksik))
