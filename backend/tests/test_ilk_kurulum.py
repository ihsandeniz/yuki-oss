"""İlk açılış sihirbazı (frontend/js/ilk-kurulum.js) — statik kapılar + saf karar fonksiyonu.

Uçtan uca (gerçek motor + tarayıcı) ölçüm: frontend/tests/test_ilk_kurulum_e2e.py.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[2]
JS = KOK / "frontend/js/ilk-kurulum.js"
INDEX = KOK / "frontend/index.html"


def _anahtarlar(dil: str) -> set[str]:
    metin = (KOK / f"frontend/js/diller/{dil}.js").read_text(encoding="utf-8")
    return set(re.findall(r"^\s*['\"](ik\.[\w.\-]+)['\"]\s*:", metin, re.M))


def test_sozluk_anahtarlari_uc_dilde_esit_ve_kodda_kullanilanlari_kapsar():
    tr, en, ja = _anahtarlar("tr"), _anahtarlar("en"), _anahtarlar("ja")
    assert tr and tr == en == ja
    kod = JS.read_text(encoding="utf-8")
    sabit = {k for k in re.findall(r"t\('(ik\.[\w.\-]+)'", kod) if not k.endswith(".")}
    # Dinamik üretilenler: ik.adim.<adim>, ik.dil.<kod>
    dinamik = {f"ik.adim.{a}" for a in ("dil", "saglayici", "anahtar", "hazir")} | {f"ik.dil.{d}" for d in ("tr", "en", "ja")}
    assert (sabit | dinamik) <= tr, sorted((sabit | dinamik) - tr)


def test_mevcut_byok_uclarini_kullanir_yeni_sir_yolu_yok():
    kod = JS.read_text(encoding="utf-8")
    assert "'/api/llm/key'" in kod and "'/api/llm/yerel'" in kod and "'/api/llm/providers'" in kod
    # localStorage'a yalnız bayrak yazılır — anahtar değil
    yazimlar = re.findall(r"localStorage\.setItem\(([^)]*)\)", kod)
    assert yazimlar == ["BAYRAK, v"], yazimlar
    assert "sessionStorage" not in kod and "indexedDB" not in kod


def test_index_dil_modulunden_sonra_yukler():
    html = INDEX.read_text(encoding="utf-8")
    i_dil = html.index("/ui/js/dil.js")
    i_ik = html.index("/ui/js/ilk-kurulum.js")
    assert i_dil < i_ik
    assert "/ui/css/ilk-kurulum.css" in html


@pytest.mark.skipif(not shutil.which("node"), reason="node yok")
@pytest.mark.parametrize("saglayicilar, aktif, bayrak, beklenen", [
    ([{"kimlik": "openrouter", "anahtar_var": False, "yerel": False}], "openrouter", None, True),     # temiz kurulum
    ([{"kimlik": "openrouter", "anahtar_var": True, "yerel": False}], "openrouter", None, False),     # anahtarı var
    ([{"kimlik": "openrouter", "anahtar_var": False}, {"kimlik": "ollama", "anahtar_var": False, "yerel": True}],
     "ollama", None, False),                                                                           # yerel seçilmiş
    ([{"kimlik": "openrouter", "anahtar_var": False, "yerel": False}], "openrouter", "atlandi", False), # atlanmış
    ([], "openrouter", None, True),
])
def test_gosterilmeli_mi(saglayicilar, aktif, bayrak, beklenen):
    betik = (
        "global.window={};global.document={readyState:'loading',addEventListener(){}};"
        f"require({json.dumps(str(JS))});"
        f"process.stdout.write(JSON.stringify(window.YukiIlkKurulum.gosterilmeliMi({json.dumps(saglayicilar)},"
        f"{json.dumps(aktif)},{json.dumps(bayrak)})))"
    )
    cikti = subprocess.run(["node", "-e", betik], capture_output=True, text=True, check=True).stdout
    assert json.loads(cikti) is beklenen
