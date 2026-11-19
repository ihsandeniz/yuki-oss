"""Kabul ⑥ — gerçek süreç ölümüyle restart (Faz 0b, karar 3).

Görev ayrı süreçte koşarken `kill -9` → yeni süreç: görev `durdu`
(`yeniden_baslatma`), kendiliğinden KOŞMAZ (1,5 sn izlenir, LLM çağrısı 0) →
onaylı DEVAM son tamamlanan adımın mesajlarıyla sürer ve biter.
Yürütücü: tests/gorev_sahte_yurutucu.py (LLM sahte, kök geçici dizin).
"""
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

ARKA = Path(__file__).resolve().parents[1]
YURUTUCU = ARKA / "tests" / "gorev_sahte_yurutucu.py"


def _env(kok):
    return dict(os.environ, YUKI_ATOLYE_KOK=str(kok), OPENROUTER_API_KEY="sahte-test")


def _kos(kip, kok):
    p = subprocess.run([sys.executable, str(YURUTUCU), kip], cwd=ARKA, env=_env(kok),
                       capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, p.stderr[-2000:]
    return json.loads(p.stdout.strip().splitlines()[-1])


def test_kill9_sonrasi_durdu_kendiliginden_kosmaz_onayla_ayni_adimdan_surer(tmp_path):
    kok = tmp_path / "atolye"
    durum = kok / "site" / "restart" / ".gorev" / "durum.json"
    p = subprocess.Popen([sys.executable, str(YURUTUCU), "baslat"], cwd=ARKA, env=_env(kok),
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        son = time.monotonic() + 30
        adim = 0
        while time.monotonic() < son:
            if durum.exists():
                try:
                    adim = json.loads(durum.read_text())["adim"]
                except (json.JSONDecodeError, KeyError):
                    adim = 0
                if adim >= 3:
                    break
            assert p.poll() is None, p.stderr.read()[-2000:]
            time.sleep(0.05)
        assert adim >= 3, "görev 30 sn'de 3 adıma ulaşmadı"
        os.kill(p.pid, signal.SIGKILL)
        p.wait(5)
    finally:
        if p.poll() is None:
            p.kill()

    olu = json.loads(durum.read_text())
    assert olu["durum"] == "kosuyor", "ölen süreç kaydı 'kosuyor' bırakmalı (kurtarılacak durum)"
    n = olu["adim"]

    k = _kos("kurtar", kok)
    assert (k["durum"], k["neden"]) == ("durdu", "yeniden_baslatma")
    assert k["llm_cagri"] == 0 and k["kosan"] == 0, "restart sonrası görev kendiliğinden koştu"
    assert k["adim"] == n

    d = _kos("devam", kok)
    assert (d["once_durum"], d["once_adim"]) == ("durdu", n)
    assert d["ilk_mesaj_kayitla_ayni"], "DEVAM kayıtlı adımdan başlamadı"
    assert d["kayitli_mesaj"] == 2 + 2 * n, "kayıtta tamamlanan adımların mesajları yok"
    assert (d["durum"], d["adim"], d["devam_sayisi"]) == ("bitti", n + 3, 1)
    alan = kok / "site" / "restart"
    assert all((alan / f"once-{i}.txt").exists() for i in range(1, n + 1))
    assert (alan / "sonra-1.txt").exists() and (alan / "sonra-2.txt").exists()
    olaylar = (alan / ".gorev" / "olaylar.jsonl").read_text()
    assert "yeniden_baslatma_durdu" in olaylar and "devam_onay" in olaylar
