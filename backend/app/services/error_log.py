"""Kullanıcıya görünür hata günlüğü — tarih/saat/neden/kaynak.

🔴 Neden var (2026-08-01): geliştiricinin Windows kurulumunda "konuşma algılanmıyor" ve
`401 Missing Authentication header` şikâyetleri geldi ve elimizde **hiçbir kayıt**
yoktu. Ürün hatalarını `logger.debug`e yazıp yutuyordu; kullanıcı da bize yalnız
"çalışmıyor" diyebiliyordu. Bu modül o boşluğu kapatır:

- Her kayıt: **ne zaman · nereden · neden · ayrıntı**
- Dosya `YUKI_DATA_DIR` altında (paketlenmiş üründe userData = **yazılabilir**;
  kod dizinine yazmak ADIM 24'te dört ayrı bug'a yol açmıştı)
- JSONL, append-only, döner (satır tavanı) — sınırsız büyüyüp diski doldurmaz
- `disari_aktar()` tek tıkla paylaşılabilir düz metin üretir; **kimlik bilgileri
  temizlenir** (`credential_scrubber`), yoksa kullanıcı anahtarını bize gönderir
"""

from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

MAX_KAYIT = 500          # dosyada tutulacak en fazla satır
_KIRP_PAYI = 100         # tavan aşılınca bir defada atılacak en eski kayıt sayısı

_kilit = threading.RLock()


def _dosya() -> Path:
    from app.config import DATA_DIR
    return Path(DATA_DIR) / "hata-gunlugu.jsonl"


def evi_kisalt(metin: str) -> str:
    """Ev dizinini `~` yap: `/home/<ad>/…` kullanıcı adını ekrana ve desteğe
    gönderilen kopyaya taşıyordu (SAĞLIK veri klasörü satırı, 2026-09-28)."""
    try:
        ev = str(Path.home())
    except Exception:
        return metin
    if not ev or ev in ("/", "\\"):
        return metin
    return metin.replace(ev, "~")


def _temizle(metin: str) -> str:
    """Anahtar/token sızıntısını maskele — günlük paylaşılabilir olmalı."""
    try:
        from app.services.credential_scrubber import scrub
        metin = scrub(metin)
    except Exception:
        pass
    return evi_kisalt(metin)


def kaydet(kaynak: str, neden: str, ayrinti: str = "", seviye: str = "error") -> None:
    """Bir hatayı günlüğe ekle.

    kaynak: nereden geldi — "ses", "llm", "lisans", "ag", "paket" ...
    neden : kısa makine-okur kod — "stt_yuklenemedi", "401_yetkisiz" ...
    ayrinti: serbest metin (istisna mesajı vb.) — maskelenir
    """
    kayit = {
        "zaman": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "kaynak": kaynak,
        "neden": neden,
        "ayrinti": _temizle(str(ayrinti))[:600],
        "seviye": seviye,
    }
    try:
        yol = _dosya()
        with _kilit:
            yol.parent.mkdir(parents=True, exist_ok=True)
            with yol.open("a", encoding="utf-8") as f:
                f.write(json.dumps(kayit, ensure_ascii=False) + "\n")
            _kirp(yol)
    except Exception as e:  # günlük yazamamak ürünü ASLA durdurmamalı
        logger.debug("hata günlüğü yazılamadı: %s", e)


def kaydet_tekil(kaynak: str, neden: str, ayrinti: str = "", seviye: str = "error",
                 pencere_sn: int = 24 * 3600) -> bool:
    """Aynı (kaynak, neden, ayrıntı) son `pencere_sn` içinde zaten yazıldıysa YAZMA.

    🔴 SAĞLIK denetimi bir GET ve panel her açılışta koşuyor; kritik bulgu her seferinde
    yeniden yazılınca tek bir kalıcı sorun günlüğü aynı satırla dolduruyordu (canlıda 415
    kayıt, "son 24 saatte N hata" sayısı da şişiyordu). Çözülüp geri gelen sorun pencere
    dolunca yeniden yazılır. Döner: yazıldı mı.
    """
    temiz = _temizle(str(ayrinti))[:600]
    simdi = datetime.now(timezone.utc).astimezone()
    for k in son_kayitlar(MAX_KAYIT):
        if k.get("kaynak") != kaynak or k.get("neden") != neden:
            continue
        # En yeni eşleşme belirleyicidir: ayrıntı değiştiyse yeni bir bulgudur
        if k.get("ayrinti") != temiz:
            break
        try:
            yas = (simdi - datetime.fromisoformat(k.get("zaman", ""))).total_seconds()
        except (TypeError, ValueError):
            break
        if 0 <= yas < pencere_sn:
            return False
        break
    kaydet(kaynak, neden, ayrinti, seviye)
    return True


def _kirp(yol: Path) -> None:
    """Dosya tavanı aşarsa en eski kayıtları at (kilit ÇAĞIRAN tarafından tutulur)."""
    try:
        satirlar = yol.read_text(encoding="utf-8").splitlines()
        if len(satirlar) <= MAX_KAYIT:
            return
        kalan = satirlar[-(MAX_KAYIT - _KIRP_PAYI):]
        gecici = yol.with_suffix(yol.suffix + ".tmp")
        gecici.write_text("\n".join(kalan) + "\n", encoding="utf-8")
        os.replace(gecici, yol)
    except Exception as e:
        logger.debug("hata günlüğü kırpılamadı: %s", e)


def son_kayitlar(adet: int = 50) -> list[dict]:
    """En yeni kayıtlar önce."""
    try:
        yol = _dosya()
        if not yol.exists():
            return []
        satirlar = yol.read_text(encoding="utf-8").splitlines()
    except Exception:
        return []
    sonuc = []
    for s in reversed(satirlar[-adet:]):
        try:
            sonuc.append(json.loads(s))
        except Exception:
            continue
    return sonuc


def ozet() -> dict:
    """Kaç hata var, en sık hangisi — panel rozetleri için."""
    kayitlar = son_kayitlar(MAX_KAYIT)
    sayac: dict[str, int] = {}
    for k in kayitlar:
        anahtar = f"{k.get('kaynak', '?')}/{k.get('neden', '?')}"
        sayac[anahtar] = sayac.get(anahtar, 0) + 1
    en_sik = sorted(sayac.items(), key=lambda x: -x[1])[:5]

    # Son 24 saat — panelin hata günlüğü kartı "şu an" sorusunu cevaplar; 500 satırlık
    # toplam günler öncesinden çözülmüş hataları da sayar (bkz. `disari_aktar` yaş etiketi).
    simdi = datetime.now().astimezone()
    taze = [k for k in kayitlar if _yas_etiketi(k.get("zaman"), simdi) is None and k.get("zaman")]
    sayac24: dict[str, list] = {}
    for k in taze:   # en yeni önce → her grubun ilk kaydı o grubun en son örneği
        sayac24.setdefault(f"{k.get('kaynak', '?')}/{k.get('neden', '?')}", []).append(k)
    en_sik24 = None
    if sayac24:
        anahtar, grup = max(sayac24.items(), key=lambda x: len(x[1]))
        en_sik24 = {"anahtar": anahtar, "adet": len(grup),
                    "ornek": (grup[0].get("ayrinti") or "")[:160]}
    return {
        "toplam": len(kayitlar),
        "en_son": kayitlar[0] if kayitlar else None,
        "en_sik": [{"anahtar": a, "adet": n} for a, n in en_sik],
        "son_24s": len(taze),
        "en_sik_24s": en_sik24,
    }


def disari_aktar(adet: int = 100) -> str:
    """Tek tıkla paylaşılabilir düz metin. Kimlik bilgileri maskelenmiştir."""
    from app.services.health import APP_VERSION
    import platform
    import sys

    basliklar = [
        "# Yuki hata günlüğü",
        f"Sürüm : {APP_VERSION}",  # i18n-istisna: destek için kopyalanan hata günlüğü dökümü, kullanıcı mesajı değil
        f"Sistem: {platform.system()} {platform.release()} ({platform.machine()})",
        f"Python: {sys.version.split()[0]}",
        f"Zaman : {datetime.now().astimezone().isoformat(timespec='seconds')}",
        "",
        "(Anahtarlar ve tokenlar otomatik maskelenmiştir.)",  # i18n-istisna: destek için kopyalanan hata günlüğü dökümü, kullanıcı mesajı değil
        "",
    ]
    kayitlar = son_kayitlar(adet)
    if not kayitlar:
        basliklar.append("Kayıtlı hata yok.")  # i18n-istisna: destek için kopyalanan hata günlüğü dökümü, kullanıcı mesajı değil
        return "\n".join(basliklar)

    # Günlük 500 satır tutar → günler öncesinden çözülmüş hatalar listenin başında
    # kalabiliyor ve rapora bakan (biz dahil) "şu an bozuk" sanıyor. 2026-08-03 saha
    # raporunda tam bu oldu: 08-01'in onnxruntime/DLL hatası en üstteydi, oysa aynı
    # dosyanın taze bölümünde motor sorunsuz yükleniyordu. Yaş artık YAZILI.
    simdi = datetime.now().astimezone()
    eski_basligi_yazildi = False
    for k in kayitlar:
        yas = _yas_etiketi(k.get("zaman"), simdi)
        if yas is not None and not eski_basligi_yazildi:
            basliklar.append("")
            basliklar.append("--- 24 saatten ESKİ kayıtlar (çözülmüş olabilir) ---")  # i18n-istisna: destek için kopyalanan hata günlüğü dökümü, kullanıcı mesajı değil
            eski_basligi_yazildi = True
        basliklar.append(
            f"[{k.get('zaman', '?')}]{yas or ''} {k.get('seviye', '?').upper()} "
            f"{k.get('kaynak', '?')}/{k.get('neden', '?')}"
        )
        if k.get("ayrinti"):
            basliklar.append(f"    {k['ayrinti']}")
    return "\n".join(basliklar)


def _yas_etiketi(zaman: str | None, simdi: datetime) -> str | None:
    """24 saatten eski kayıtlar için ' (N gün önce)' etiketi; taze kayıtta None.

    Kayıtlar en yeniden eskiye sıralı gelir → ilk None-olmayan sonuç, eski bölümün
    başladığı yerdir.
    """
    if not zaman:
        return None
    try:
        t = datetime.fromisoformat(zaman)
    except (TypeError, ValueError):
        return None
    if t.tzinfo is None:
        t = t.astimezone()
    saat = (simdi - t).total_seconds() / 3600
    if saat < 24:
        return None
    gun = int(saat // 24)
    return f" ({gun} gün önce)" if gun >= 1 else None  # i18n-istisna: destek için kopyalanan hata günlüğü dökümü, kullanıcı mesajı değil


def temizle_gunluk() -> int:
    """Günlüğü sıfırla; silinen kayıt sayısını döner.

    🔴 Silemezse İSTİSNA fırlatır (eskiden 0 dönüyordu ve uç `ok:true` + "0 kayıt
    silindi" yazıyordu — kayıtlar yerinde dururken). Çağıran `ok:false` döner.
    """
    with _kilit:
        yol = _dosya()
        n = len(son_kayitlar(MAX_KAYIT))
        yol.unlink(missing_ok=True)
        return n


# ── Otomatik yakalama: WARNING+ log kayıtlarını günlüğe düşür ────────────────

class GunlukHandler(logging.Handler):
    """WARNING ve üstü her log kaydını hata günlüğüne yazar.

    Böylece ileride eklenen her `logger.warning` ayrıca bir şey yapmadan
    kullanıcıya görünür olur — 2026-08-01'de kaynağı bulunamayan
    `401 Missing Authentication header` gibi bir hata bir daha izsiz kalmaz.
    """

    _YOK_SAY = ("app.services.error_log",)   # kendini loglama → sonsuz döngü

    def emit(self, record: logging.LogRecord) -> None:
        if record.name.startswith(self._YOK_SAY):
            return
        try:
            kaydet(
                kaynak=record.name.replace("app.services.", "").replace("app.api.", ""),
                neden=record.levelname.lower(),
                ayrinti=record.getMessage(),
                seviye="error" if record.levelno >= logging.ERROR else "warning",
            )
        except Exception:
            pass


def kur() -> None:
    """Kök logger'a handler'ı bir kez tak."""
    kok = logging.getLogger()
    if any(isinstance(h, GunlukHandler) for h in kok.handlers):
        return
    h = GunlukHandler(level=logging.WARNING)
    kok.addHandler(h)
    logger.info("Hata günlüğü etkin: %s", _dosya())
