"""HQ › MODLAR · BAŞLATMA IZGARASI — panel bekçileri (2026-09-27 panel 7).

Kişisel 097779b'nin tasarımı ürüne yeniden yazılırken ölçülen ürün kusurlarının kapıları:
  ① silme `confirm()` ile (Electron'da pencereyi kilitler)
  ② BAŞLAT çift tıkı engellemiyordu (iki POST = iki kez açılan uygulamalar)
  ③ liste yükleme `r.ok`'a bakmıyordu → oturum kilitliyken (401) "Henüz mod yok"
  ④ değer taşıyan inline onclick (`onclick="hqX('<esc(id)>')"`): `esc` tek tırnağı
     kaçırmıyor, tek tırnaklı id/ad onclick'i kırıyordu
  ⑤ panel yalnız ilk açılışta yükleniyordu (`_loaded.modlar`) → başlatıcı ayarı bayat
  ⑥ Hyprland dışı masaüstlerinde `/workspaces` "alan 1 dolu" UYDURUYORDU (`active: i == 1`)
"""
import re
from pathlib import Path

from app.api import modes_api

KOK = Path(__file__).resolve().parents[2]
INTRO = (KOK / "frontend" / "js" / "intro-sequences.js").read_text(encoding="utf-8")
_bas = INTRO.index("// ════════ MODLAR")
BLOK = INTRO[_bas:INTRO.index("// ════════ FAZ 17", _bas)]
KOD = re.sub(r"/\*.*?\*/", "", BLOK, flags=re.S)


def test_silme_ve_baslatma_tarayici_diyalogu_KULLANMIYOR():
    assert "confirm(" not in KOD and "alert(" not in KOD and "prompt(" not in KOD
    assert "md-sil-evet" in KOD, "satır içi silme onayı yok"


def test_baslat_cift_tiki_engeller():
    m = re.search(r"window\.hqModeRun=async function\(id\)\{(.*?)\n  \};", KOD, re.S)
    assert m, "hqModeRun bulunamadı"
    govde = m.group(1)
    ilk = govde.index("'suruyor'")
    assert ilk < govde.index("af('/api/modes/run/"), "istekten ÖNCE 'sürüyor' kilidi kontrol edilmeli"
    assert "return;" in govde[:govde.index("af('/api/modes/run/")]


def test_liste_yukleme_sunucu_cevabina_bakar():
    m = re.search(r"window\.hqLoadModes=async function\(\)\{(.*?)\n  \};", KOD, re.S)
    assert m and "r.ok" in m.group(1) and "_mdHata" in m.group(1)
    assert "hq.modlar.oturum-kilitli" in KOD, "401 ayrı söylenmiyor"


def test_deger_tasiyan_inline_onclick_YOK():
    kotu = re.findall(r"""onclick="[^"]*\('\+esc\(""", KOD)
    assert not kotu, f"tek tırnakta kırılan inline onclick: {kotu[:3]}"


def test_panel_her_acilista_tazelenir():
    m = re.search(r"window\.switchHqTab = function\(name\)\{(.*?)\n  \};", INTRO, re.S)
    assert m
    assert "_loaded.modlar" not in m.group(1) and "if(name==='modlar'){ hqLoadModes(); }" in m.group(1)


def test_hyprland_disinda_alan_dolulugu_UYDURULMAZ(monkeypatch):
    ozellik = {"specials": False, "workspaces": True}
    monkeypatch.setattr(modes_api, "detect_env", lambda: {"features": ozellik})
    import asyncio
    from starlette.requests import Request
    istek = Request({"type": "http", "method": "GET", "path": "/api/modes/workspaces", "headers": [],
                     "client": ("127.0.0.1", 1), "query_string": b""})
    d = asyncio.run(modes_api.list_workspaces.__wrapped__(istek)) if hasattr(modes_api.list_workspaces, "__wrapped__") \
        else asyncio.run(modes_api.list_workspaces(istek))
    assert d["workspaces"] and all(w["active"] is None for w in d["workspaces"])
