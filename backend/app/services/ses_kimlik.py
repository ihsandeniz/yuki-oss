"""Ses kimliği — "yalnız kayıtlı sesi dinle" kapısı.

Kullanıcı kendi sesini birkaç kısa kayıtla tanıtır; sonra sesli komutta konuşan kişi kayıtlı
sese benzemiyorsa (TV, odadaki başka biri, Yuki'nin kendi sesi) komut yok sayılabilir.

Söz başına: enerji tabanlı konuşma ayıklama → 80 boyutlu log-mel fbank (Kaldi düzeni,
zaman ortalaması çıkarılır) → CAM++ konuşmacı modeli (ONNX, CPU, 192-d gömme) → kayıtlı
ses iziyle kosinüs benzerliği.

Kurallar:
  · Bayrak `SES_KIMLIK` varsayılan KAPALI. Kapalıyken ya da rıza yokken `dogrula()` hiç
    model yüklemez, `None` döner (kapı geçirir = bugünkü davranış).
  · Bu bir GÜVENLİK sınırı değildir: kayıttan çalma ya da ses klonu atlatır. İşi başka
    sesleri süzmek. Asıl koruma onay kapılarındadır.
  · Kayıt sesleri SAKLANMAZ: yalnız bellekte işlenir, diske yalnız ortalama gömme yazılır
    (`<veri dizini>/ses_kimlik.json`, izin 600). Hiçbir şey buluta gitmez.
  · Rıza geri çekilince ses izi silinir (`riza_geri_cekildi`).
  · Model depoda gelmez (kullanıcı resmî kaynaktan indirir: `MODEL_URL`, Apache-2.0,
    3D-Speaker). Yoksa kayıt açık bir hatayla reddedilir.

Eşikler (ortamdan): SES_KIMLIK_ESIK 0.50 · SES_KIMLIK_KISA_ESIK 0.40 (söz SES_KIMLIK_KISA_SN
1.0 sn'den kısaysa) · SES_KIMLIK_ONAY_ESIK 0.55 · SES_KIMLIK_ONAY_KISA_ESIK 0.42 (onay beklerken).
"""
from __future__ import annotations

import io
import json
import logging
import os
import threading
import wave
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

SR = 16000
EN_AZ_SN = 0.25                 # bundan kısa konuşma doğrulanamaz → red
KAYIT_EN_AZ_SN = 8.0            # kayıt için toplam konuşma
MODEL_ADI = "3dspeaker_speech_campplus_sv_zh_en_16k-common_advanced.onnx"
MODEL_URL = f"https://huggingface.co/csukuangfj/speaker-embedding-models/resolve/main/{MODEL_ADI}"
_ACIK = ("1", "true", "yes", "on")


class ModelYok(RuntimeError):
    pass


class RizaYok(RuntimeError):
    pass


# ── ayarlar ─────────────────────────────────────────────────────────────────
def bayrak_acik() -> bool:
    from app import config
    deger = getattr(config, "SES_KIMLIK", None)
    if deger is not None:
        return bool(deger)
    return os.getenv("SES_KIMLIK", "false").strip().lower() in _ACIK


def _veri_dizini() -> Path:
    yol = os.getenv("YUKI_DATA_DIR", "").strip()
    if yol:
        return Path(yol)
    from app.config import DATA_DIR
    return Path(DATA_DIR)


def model_yolu() -> Path:
    yol = os.getenv("SES_KIMLIK_MODEL", "").strip()
    return Path(yol) if yol else _veri_dizini() / "modeller" / "ses-kimlik" / MODEL_ADI


def parmak_izi_yolu() -> Path:
    return _veri_dizini() / "ses_kimlik.json"


def esikler() -> dict[str, float]:
    def _f(ad: str, v: str) -> float:
        try:
            return float(os.getenv(ad, v))
        except ValueError:
            return float(v)
    return {"komut": _f("SES_KIMLIK_ESIK", "0.50"), "kisa": _f("SES_KIMLIK_KISA_ESIK", "0.40"),
            "onay": _f("SES_KIMLIK_ONAY_ESIK", "0.55"), "onay_kisa": _f("SES_KIMLIK_ONAY_KISA_ESIK", "0.42"),
            "kisa_sn": _f("SES_KIMLIK_KISA_SN", "1.0")}


def _riza_var() -> bool:
    from app.services import biyometrik_riza
    return biyometrik_riza.var_mi("ses_kimlik")


@dataclass
class Sonuc:
    skor: float | None      # None = konuşma doğrulanamayacak kadar kısa
    sure_sn: float          # ayıklanan konuşma süresi

    def esik(self, onay: bool = False) -> float:
        e = esikler()
        kisa = self.sure_sn < e["kisa_sn"]
        if onay:
            return e["onay_kisa"] if kisa else e["onay"]
        return e["kisa"] if kisa else e["komut"]

    def kabul(self, onay: bool = False) -> bool:
        return self.skor is not None and self.skor >= self.esik(onay)


# ── ses → konuşma ───────────────────────────────────────────────────────────
def pcm_oku(ses: bytes) -> np.ndarray:
    """Her biçim (wav/webm/ogg…) → 16 kHz mono float32 [-1, 1]. Diske yazmaz."""
    from app.services.stt import ensure_wav
    try:
        veri = ensure_wav(bytes(ses))
        with wave.open(io.BytesIO(veri), "rb") as w:
            kanal, genislik, hz = w.getnchannels(), w.getsampwidth(), w.getframerate()
            ham = w.readframes(w.getnframes())
    except Exception:
        raise ValueError("ses çözülemedi") from None
    if genislik != 2 or kanal < 1 or hz < 8000:
        raise ValueError("ses biçimi desteklenmiyor")
    x = np.frombuffer(ham, dtype="<i2").astype(np.float32) / 32768.0
    if kanal > 1:
        x = x[: len(x) - len(x) % kanal].reshape(-1, kanal).mean(1)
    if hz != SR and len(x):
        n = int(round(len(x) * SR / hz))
        x = np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x).astype(np.float32)
    return np.ascontiguousarray(x, dtype=np.float32)


def konusma_kismi(x: np.ndarray) -> np.ndarray:
    """Enerjisi düşük (sessiz) 30 ms'lik dilimleri atar."""
    dilim = int(0.03 * SR)
    n = len(x) // dilim
    if n == 0:
        return x[:0]
    d = x[: n * dilim].reshape(n, dilim)
    rms = np.sqrt((d.astype(np.float64) ** 2).mean(1))
    esik = max(0.01, 0.2 * float(np.percentile(rms, 95)))
    secili = d[rms > esik]
    return secili.reshape(-1).astype(np.float32) if len(secili) else x[:0]


_MEL: np.ndarray | None = None


def _mel_suzgec(bant: int = 80, nfft: int = 512) -> np.ndarray:
    def mel(f):
        return 1127.0 * np.log(1.0 + np.asarray(f) / 700.0)
    kutu = nfft // 2
    f_kutu = np.arange(kutu) * SR / nfft
    m_kutu = mel(f_kutu)
    m_alt, m_ust = mel(20.0), mel(SR / 2)
    adim = (m_ust - m_alt) / (bant + 1)
    s = np.zeros((bant, kutu + 1), dtype=np.float64)
    for b in range(bant):
        sol, orta, sag = m_alt + b * adim, m_alt + (b + 1) * adim, m_alt + (b + 2) * adim
        yukari = (m_kutu - sol) / (orta - sol)
        asagi = (sag - m_kutu) / (sag - orta)
        s[b, :kutu] = np.maximum(0.0, np.minimum(yukari, asagi))
    return s


def fbank(x: np.ndarray) -> np.ndarray:
    """Kaldi düzeninde 80 boyutlu log-mel fbank (25 ms pencere, 10 ms adım, hamming)."""
    global _MEL
    if _MEL is None:
        _MEL = _mel_suzgec()
    uzun, adim, nfft = 400, 160, 512
    if len(x) < uzun:
        return np.zeros((0, 80), dtype=np.float32)
    n = 1 + (len(x) - uzun) // adim
    idx = np.arange(uzun)[None, :] + adim * np.arange(n)[:, None]
    c = x[idx].astype(np.float64)
    c = c - c.mean(1, keepdims=True)
    c = np.concatenate([c[:, :1] * (1 - 0.97), c[:, 1:] - 0.97 * c[:, :-1]], axis=1)
    c = c * np.hamming(uzun)[None, :]
    guc = np.abs(np.fft.rfft(c, n=nfft, axis=1)) ** 2
    f = np.log(np.maximum(guc @ _MEL.T, np.finfo(np.float32).eps))
    return (f - f.mean(0, keepdims=True)).astype(np.float32)


# ── model ───────────────────────────────────────────────────────────────────
_oturum = None
_oturum_yolu: str | None = None
_oturum_kilit = threading.Lock()


def _model_gomme(konusma: np.ndarray) -> np.ndarray:
    global _oturum, _oturum_yolu
    yol = model_yolu()
    if not yol.is_file():
        raise ModelYok(model_yok_metni())
    with _oturum_kilit:
        if _oturum is None or _oturum_yolu != str(yol):
            import onnxruntime as ort
            so = ort.SessionOptions()
            so.intra_op_num_threads = 2
            _oturum = ort.InferenceSession(str(yol), so, providers=["CPUExecutionProvider"])
            _oturum_yolu = str(yol)
        s = _oturum
    e = s.run(None, {s.get_inputs()[0].name: fbank(konusma)[None]})[0][0]
    return (e / (np.linalg.norm(e) + 1e-9)).astype(np.float32)


_gomme = _model_gomme      # testler sahte gömme koyar


def model_yok_metni() -> str:
    return (f"ses kimliği modeli bulunamadı ({model_yolu()}). Modeli şuradan indirip bu yola koyun: "
            f"{MODEL_URL}")


# ── ses izi ─────────────────────────────────────────────────────────────────
_iz_onbellek: tuple[float, np.ndarray] | None = None


def _onbellek_temizle() -> None:
    global _iz_onbellek, _uyari_verildi
    _iz_onbellek = None
    _uyari_verildi = False


def parmak_izi() -> np.ndarray | None:
    """Kayıtlı gömme; yok / bozuk / başka model → None."""
    global _iz_onbellek
    yol = parmak_izi_yolu()
    try:
        mt = yol.stat().st_mtime_ns
    except FileNotFoundError:
        return None
    if _iz_onbellek and _iz_onbellek[0] == mt:
        return _iz_onbellek[1]
    try:
        d = json.loads(yol.read_text(encoding="utf-8"))
        v = np.asarray(d["gomme"], dtype=np.float32)
        if d.get("model") != MODEL_ADI or v.shape != (192,) or not np.isfinite(v).all():
            raise ValueError("model/boyut uyuşmuyor")
    except Exception as e:
        logger.error("Ses kimliği: ses izi okunamadı (%s) — kapı geçiriyor", e)
        return None
    v = v / (np.linalg.norm(v) + 1e-9)
    _iz_onbellek = (mt, v)
    return v


def kayit_ozeti() -> dict:
    try:
        d = json.loads(parmak_izi_yolu().read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError, OSError):
        return {"var": False}
    return {"var": parmak_izi() is not None, "klip": d.get("klip"), "konusma_sn": d.get("konusma_sn"),
            "tarih": d.get("tarih")}


def kaydet(sesler: list[bytes], en_az_sn: float = KAYIT_EN_AZ_SN) -> dict:
    """Kayıt sesleri → ortalama gömme → ses izi dosyası (600). Ses saklanmaz."""
    if not bayrak_acik() or not _riza_var():
        raise RizaYok("ses kimliği için rıza verilmedi")
    if not model_yolu().is_file():
        raise ModelYok(model_yok_metni())
    gommeler, toplam = [], 0.0
    for s in sesler:
        k = konusma_kismi(pcm_oku(s))
        if len(k) < SR * EN_AZ_SN:
            continue
        toplam += len(k) / SR
        gommeler.append(_gomme(k))
        del k
    if toplam < en_az_sn:
        raise ValueError(f"kayıt için konuşma az: {toplam:.1f} sn (en az {en_az_sn:.0f} sn)")
    ort = np.mean(gommeler, 0)
    ort = ort / np.linalg.norm(ort)
    yol = parmak_izi_yolu()
    yol.parent.mkdir(parents=True, exist_ok=True)
    gecici = yol.with_suffix(".tmp")
    fd = os.open(gecici, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump({"model": MODEL_ADI, "klip": len(gommeler), "konusma_sn": round(toplam, 2),
                   "tarih": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                   "gomme": [round(float(v), 6) for v in ort]}, f)
    os.replace(gecici, yol)
    os.chmod(yol, 0o600)
    _onbellek_temizle()
    return {"klip": len(gommeler), "konusma_sn": round(toplam, 2),
            "ic_tutarlilik_min": round(min(float(g @ ort) for g in gommeler), 3)}


def sil() -> bool:
    """Ses izini siler. Önceden kayıt varsa True."""
    yol = parmak_izi_yolu()
    vardi = yol.exists()
    yol.unlink(missing_ok=True)
    yol.with_suffix(".tmp").unlink(missing_ok=True)
    _onbellek_temizle()
    return vardi


def riza_geri_cekildi() -> None:
    sil()


# ── kapı ────────────────────────────────────────────────────────────────────
_uyari_verildi = False


def dogrula(ses: bytes) -> Sonuc | None:
    """Kapı kapalı / rıza yok / kullanılamıyorsa None (geçir). Değilse skorlu Sonuc."""
    global _uyari_verildi
    if not bayrak_acik() or not _riza_var():
        return None
    iz = parmak_izi()
    if iz is None or not model_yolu().is_file():
        if not _uyari_verildi:
            logger.warning("Ses kimliği açık ama %s yok — kapı geçiriyor",
                           "ses izi" if iz is None else "model")
            _uyari_verildi = True
        return None
    try:
        k = konusma_kismi(pcm_oku(ses))
        sure = len(k) / SR
        if sure < EN_AZ_SN:
            return Sonuc(None, round(sure, 2))
        return Sonuc(round(float(_gomme(k) @ iz), 4), round(sure, 2))
    except Exception as e:
        logger.error("Ses kimliği hata (%s) — kapı geçiriyor", type(e).__name__)
        return None


def kesme_izni(ses: bytes) -> bool:
    """Söz kesme (barge-in) kapısı: kısa ses parçası kayıtlı konuşmacıdan mı?
    Kapı kapalı / kullanılamıyorsa True (bugünkü davranış). Kısa eşik uygulanır."""
    r = dogrula(ses)
    if r is None:
        return True
    return r.skor is not None and r.skor >= esikler()["kisa"]
