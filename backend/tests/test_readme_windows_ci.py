"""README'deki Windows adımları ile CI'ın Windows'ta koştuğu satırlar aynıdır.

Kusur: README Windows için yalnız bir yorum veriyordu (`# Windows: venv\\Scripts\\pip ...`);
sunucuyu başlatma satırı yoktu. CI'ın Windows işi ise README'de olmayan başka bir yol
koşuyordu (venv'siz `python run.py`). Okuyanın izlediği yol hiçbir yerde denenmiyordu.

Ölçülen:
  1. README'de "Windows steps (PowerShell)" bloğu var: venv, paket kurma, başlatma satırları.
  2. Bloğun her komut satırı (`cd backend` hariç: CI'da `working-directory: backend`)
     CI'ın windows-duman işindeki README adımında AYNEN geçer.
  3. O adım backend dizininde koşar ve /health 200 bekler.
  4. README'de depoyu alma adımı ve `python3` / `python` açıklaması var.
"""
from __future__ import annotations

import re
from pathlib import Path

KOK = Path(__file__).resolve().parents[2]
README = (KOK / "README.md").read_text(encoding="utf-8")
CI = (KOK / ".github/workflows/pytest.yml").read_text(encoding="utf-8")
ADIM_ADI = "README Windows adımları"


def _windows_blogu() -> list[str]:
    m = re.search(r"#### Windows steps \(PowerShell\).*?```powershell\n(.*?)```", README, re.S)
    assert m, "README'de 'Windows steps (PowerShell)' bloğu yok"
    return [s.strip() for s in m.group(1).splitlines() if s.strip() and not s.strip().startswith("#")]


def _ci_adimi() -> str:
    i = CI.index(f"- name: {ADIM_ADI}")
    son = CI.find("\n      - name:", i + 1)
    return CI[i:son if son != -1 else None]


def test_readme_windows_blogu_tam():
    satirlar = _windows_blogu()
    assert satirlar[0] == "cd backend"
    assert any(s.startswith("python -m venv venv") for s in satirlar)
    assert any("pip install -r" in s for s in satirlar)
    assert any("uvicorn app.main:app" in s and "--port 8001" in s for s in satirlar)


def test_readme_windows_satirlari_ci_da_aynen_kosar():
    adim = _ci_adimi()
    ci_satirlari = {s.strip() for s in adim.splitlines()}
    eksik = [s for s in _windows_blogu() if s != "cd backend" and s not in ci_satirlari]
    assert not eksik, f"README satırı CI'da yok: {eksik}"


def test_ci_adimi_backend_dizininde_ve_health_bekler():
    adim = _ci_adimi()
    assert "working-directory: backend" in adim
    assert "shell: pwsh" in adim
    assert "http://127.0.0.1:8001/health" in adim
    assert "exit 1" in adim
    # windows-duman işinin içinde (runs-on: windows-latest)
    is_bas = CI.index("windows-duman:")
    assert is_bas < CI.index(f"- name: {ADIM_ADI}")
    assert "runs-on: windows-latest" in CI[is_bas:CI.index(f"- name: {ADIM_ADI}")]


def test_readme_depo_alma_ve_python_adi():
    assert "git clone https://github.com/ihsandeniz/yuki-oss.git" in README
    assert "Download ZIP" in README
    assert "`python3` or `python`?" in README
