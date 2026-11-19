"""Ölü uç kapısı — arayüzün çağırdığı her `/api` yolu backend'de VAR MI? (2026-08-11)

NEDEN VAR: `frontend/modes/hud-ring.js:1555` yayındaki v0.6.1'de `/api/map/stocks`
çağırıyor; o uç backend'de **hiç yok**. HALKA modunun FİNANS sekmesine basan her
müşteri (free/Pro/Ultra fark etmez) *"finans verisi alınamadı"* görüyor ve widget
açık kaldıkça istek 30 sn'de bir tekrarlanıyor. Kimse fark etmedi çünkü arayüzün
`catch` dalı hatayı yutup ekrana kibar bir cümle yazıyordu.

Bu, projede tekrar eden bir sınıf — *"kod var ama ULAŞILAMIYOR"* / *"ilan edilen
ama uygulanmamış özellik"*: TAM BOY (MODES listesinde yoktu) · karakter kilidi
(arayüz kapıya bakmıyordu) · `ocr_image` (köprü yoktu) · şimdi FİNANS.
🔑 Ortak ders: **bir çağrının yazılmış olması, karşılığının var olduğunu
göstermez.** Yorum ya da belge değil, ancak mekanik bir kapı bunu tutabilir.

KAPININ ŞEKLİ — cırcır (ratchet), tek atış temizlik değil:
  · Arayüzde geçen, backend'de karşılığı OLMAYAN her yol hata verir.
  · `BILINEN_OLU` içindekiler bilinçli istisnadır ve **gerekçe taşımak zorundadır**.
  · Bir istisna artık ölü değilse (uç yazıldıysa) test yine kırılır — listenin
    bayatlaması da bir kusurdur. *"Borcun AÇIK olduğu da doğrulanır"* dersi.

YANLIŞ ALARM ELEME KURALI: gerçek bir rotanın ÖN EKİ olan literal bir çağrı değil,
taban sabittir (`const API = '/api/todo'` → `${API}/lists`). Bunlar elenir.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.main import app

KOK = Path(__file__).resolve().parents[2]
FRONTEND = KOK / "frontend"

# ── Bilinçli istisnalar ────────────────────────────────────────────────────────
# Anahtar: arayüzde geçen yol · Değer: neden hâlâ duruyor.
# 🔴 Yeni satır eklemek bir KARAR'dır: "bu uç yok ve olmayacağını biliyoruz" demektir.
BILINEN_OLU: dict[str, str] = {
    # ⏳ G7 (2026-11-12, dal oss/gen-dosya): güvenli dosya işlemleri yönlendiricisi
    #    `app/api/guvenli_dosya_api.py` yazıldı ve testli (`tests/test_guvenli_dosya.py`), ama
    #    `main.py` ortak dosya olduğu için kaydı G4 entegre şeridinde yapılacak:
    #    `app.include_router(guvenli_dosya_api.router)`. Kaydedilince bu satır bayatlar ve
    #    `test_bilinen_olu_listesi_bayatlamasin` kırmızı yanar → satırı sil.
    #    Kayıtsızken ön yüz zararsız: `/durum` 404 → kilit düz etiket kalır, menüye satır eklenmez.
    # ✅ `/api/map/stocks` 2026-08-12'de KAPANDI (D1 = B): FİNANS sekmesi artık ağa hiç
    #    çıkmıyor, durumunu söyleyip bugün çalışan yolu (sohbetten döviz/kripto) gösteriyor.
    #    Satır bu kapının kendi kuralıyla silindi — `test_bilinen_olu_listesi_bayatlamasin`
    #    çağrı kalkar kalkmaz kırmızı yandı. Cırcır çalışıyor.
    # ✅ `/api/fitness` 2026-08-23'te CANLANDI — satır bu kapının kendi kuralıyla silindi.
    #    Router `main.py`'ye kaydedildi + Postgres'siz kurulum için `fitness_store.py`
    #    (todo_store deseni) yazıldı. Cırcır ikinci kez çalıştı: uç yazılır yazılmaz
    #    `test_bilinen_olu_listesi_bayatlamasin` kırmızı yandı.
    #    📏 Buradaki eski gerekçe DOĞRUYDU ve bir teşhis hatasını düzeltti: ekran
    #    "0 kcal" gösterdiği için önce "sessiz başarısızlık" sanıldı; oysa veri
    #    localStorage'daydı ve ekran ÇALIŞIYORDU — eksik olan yalnız sunucu senkronuydu.
    #    Kazanılan şey: veri artık sunucuda kalıcı, cihaz değişince kaybolmuyor,
    #    Yuki sohbetten görebiliyor. ("doğrulamadan 'bozuk' deme" — ledger adayı)
    # ── Sistem izleme paneli: 2026-08-28'de arayüz kodu da SÖKÜLDÜ ─────
    # Eskiden burada 6 monitor ucu listeliydi: panel kaldırılmıştı ama JS'i duruyordu,
    # yani "ölü ama ulaşılamaz" idiler. 08-28'de o 211 satır silindi → artık bu uçları
    # ÇAĞIRAN kod yok, dolayısıyla "çağrılan ölü uç" listesinde de yerleri yok.
    # 🔑 Bu testin bayatlama kapısı tam bunun için var: silme işini kendisi yakaladı
    #    ve listeden düşürülmesi gereken satırları tek tek saydı.
    # Kalan tek girdi `snapshot`, çünkü onun İKİNCİ bir çağıranı var (game-mode.js).
    # ⚠️ `processes` ve `snapshot` LİSTEDE KALDI: monitor paneli silinince
    # çağıranları bitti sanılmıştı, ama `game-mode.js` de ikisini çağırıyor.
    # OYUN modu mod seçicide yok (uykuda) → ulaşılamaz, ama kod duruyor.
    # 📏 "Çağıran kalmadı" demeden önce TÜM çağıranları say; bir modülü silmek
    #    ötekinin çağrısını silmez. Bu satır ölçümle geri kondu, tahminle değil.
    # ✅ 2026-09-10 (Dalga 3): `/api/monitor/{snapshot,processes}` LİSTEDEN DÜŞTÜ.
    # `api/monitor.py` main.py'ye kaydedildi ve dört builder yml'deki paket
    # filtresinden çıkarıldı → uçlar artık canlı. HQ → SİSTEM paneli onları
    # tüketecek; `game-mode.js` çağrıları da (uykuda olsalar bile) artık gerçek
    # bir uca gidiyor.
    # 🔑 Bu satırları BU TEST düşürttü: uç uyandırılınca kendisi kırmızı yandı
    # ve hangi girdilerin bayatladığını tek tek saydı. Bayatlama kapısının
    # değeri tam burada — kayıt, gerçeği geriden takip edemiyor.
}

# Arayüzde tırnak içinde geçen `/api/...` literalleri. `${...}` şablonları jokerleşir.
# ⚠️ Sorgu dizesi (`?sort=…`) de yakalanmalı: ilk sürüm `?` içermiyordu ve
# `/api/monitor/processes?sort=` gibi ÖLÜ çağrıların 4'ünü hiç görmüyordu —
# kapı sessizce eksik ölçüyordu.
CAGRI = re.compile(r"""['"`](/api/[A-Za-z0-9_\-/{}$.:?&=]*)['"`]""")


def _rota_desenleri() -> list[tuple[str, re.Pattern[str]]]:
    """FastAPI rota tablosu → eşleştirilebilir desenler (`/api/todo/{id}` → `/api/todo/[^/]+`)."""
    desenler = []
    for r in app.routes:
        yol = getattr(r, "path", "")
        if not yol.startswith("/api"):
            continue
        desenler.append((yol, re.compile("^" + re.sub(r"\{[^}]+\}", "[^/]+", re.escape(yol).replace(r"\{", "{").replace(r"\}", "}")) + "$")))
    return desenler


def _frontend_cagrilari() -> dict[str, list[str]]:
    bulunan: dict[str, list[str]] = {}
    for f in sorted(FRONTEND.rglob("*")):
        if f.suffix not in (".js", ".html") or "assets" in f.parts:
            continue
        for i, satir in enumerate(f.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
            for m in CAGRI.finditer(satir):
                bulunan.setdefault(m.group(1), []).append(f"{f.relative_to(KOK)}:{i}")
    return bulunan


def _olu_uclar() -> dict[str, list[str]]:
    """Backend'de karşılığı olmayan arayüz çağrıları."""
    desenler = _rota_desenleri()
    rotalar = [y for y, _ in desenler]
    olu: dict[str, list[str]] = {}
    for yol, yerler in _frontend_cagrilari().items():
        test = re.sub(r"\$\{[^}]*\}", "X", yol).split("?")[0].rstrip("/")
        if any(d.match(test) or d.match(test + "/") for _, d in desenler):
            continue
        # Taban sabit mi? (gerçek bir rotanın ön eki) → çağrı değil, yanlış alarm.
        # `const API = '/api/todo'` → `${API}/lists`; `sw.js`'teki `startsWith('/api/')` de böyle elenir.
        if any(r.startswith(test + "/") or r.startswith(test) for r in rotalar if test):
            continue
        olu.setdefault(test, []).extend(yerler)   # anahtar sorgu dizesiz taban yol
    return olu


def test_rota_tablosu_okunabiliyor():
    """Kapının kendisi çalışıyor mu — boş tablo her şeyi 'ölü' gösterir, sessiz felaket."""
    desenler = _rota_desenleri()
    assert len(desenler) > 50, f"beklenenden az /api rotası ({len(desenler)}) — kapı kör olabilir"


def test_frontend_taramasi_bir_sey_buluyor():
    """Regex bozulursa hiçbir çağrı bulunmaz ve test SESSİZCE yeşil kalırdı."""
    cagrilar = _frontend_cagrilari()
    assert len(cagrilar) > 30, f"arayüzde yalnız {len(cagrilar)} /api çağrısı bulundu — tarama bozuk"


def test_eslestirme_calisiyor():
    """Çağrıların BÜYÜK ÇOĞUNLUĞU gerçek rotalara oturmalı.

    Eşleştirme bozulsaydı (ör. `{id}` deseni) her şey 'ölü' görünür, kapı
    gürültüye boğulur ve ilk kırmızıda devre dışı bırakılırdı — sessiz ölümün
    en yaygın biçimi.
    """
    toplam = len(_frontend_cagrilari())
    olu = len(_olu_uclar())
    assert olu / toplam < 0.25, f"çağrıların %{100 * olu // toplam}'i eşleşmiyor — eşleştirme bozuk olabilir"


def test_yeni_olu_uc_yok():
    """Arayüz, backend'de olmayan bir uca YENİ bağlanmasın."""
    olu = _olu_uclar()
    yeni = {y: k for y, k in olu.items() if y not in BILINEN_OLU}
    assert not yeni, (
        "Arayüz backend'de OLMAYAN uçlara bağlanıyor:\n"
        + "\n".join(f"  {y}  ←  {', '.join(k[:3])}" for y, k in sorted(yeni.items()))
        + "\n\nYa ucu yaz, ya çağrıyı kaldır. Bilinçli bir istisnaysa gerekçesiyle "
          "BILINEN_OLU'ya ekle — 'kod var ama arkasında hiçbir şey yok' bu üründe "
          "dört kez müşteriye gitti."
    )


def test_bilinen_olu_listesi_bayatlamasin():
    """Uç sonradan yazıldıysa istisna satırı SİLİNMELİ — bayat liste kapıyı körleştirir."""
    olu = _olu_uclar()
    artik_yasayan = sorted(set(BILINEN_OLU) - set(olu))
    assert not artik_yasayan, (
        "BILINEN_OLU'daki şu yollar artık ÖLÜ DEĞİL (uç yazılmış ya da çağrı kaldırılmış) — "
        f"satırları sil: {artik_yasayan}"
    )


@pytest.mark.parametrize("yol", sorted(BILINEN_OLU))
def test_istisnalar_gerekce_tasiyor(yol: str):
    """Gerekçesiz istisna, istisna değil sessiz kabuldür.

    ℹ️ 2026-09-10'dan beri `BILINEN_OLU` **boş** → pytest bu testi "empty
    parameter set" diye ATLIYOR. Atlama bir arıza değil, **iyi haber**:
    çağrılan ölü uç kalmadı. Liste yeniden dolarsa test kendiliğinden koşar.
    """
    assert len(BILINEN_OLU[yol].strip()) > 40, f"{yol} için gerekçe çok kısa/boş"
