"""Birleştirme şeridi (oss/entegre-1112) kesişim testleri.

F1-cevap/F2'nin `runner.arac_suresi()` tek kaynağı ile F2b'nin `_ARAC_SURESI`
sözlüğü birleşince ortaya çıkan kurallar: check_updates'in 60 sn'si Anthropic
yolunda da geçerli, görev türünün daha uzun bütçesi kısalmaz.
"""
from app.services import runner


def test_check_updates_anthropic_yolunda_da_60_sn():
    # llm.py Anthropic yolu arac_suresi(tu.name) çağırır (varsayılan parametre)
    assert runner.arac_suresi("check_updates") >= 60.0


def test_check_updates_gorev_butcesini_kisaltmaz():
    assert runner.arac_suresi("check_updates", 120.0) >= 120.0
    assert runner.arac_suresi("check_updates", 30.0) >= 60.0


def test_siradan_arac_genel_tavanda():
    assert runner.arac_suresi("list_packages") == runner.TOOL_TIMEOUT


def test_uzun_araclar_ve_kaldirilan_uai():
    assert runner.arac_suresi("run_team") == runner.LONG_TOOL_TIMEOUT
    assert runner.arac_suresi("mcp__x__y") == runner.LONG_TOOL_TIMEOUT
    # f1-arac: arkası olmayan UAI araçları kalktı, uzun listede de yok
    assert "delegate_task" not in runner._LONG_TOOLS
    assert "get_task_result" not in runner._LONG_TOOLS


def test_anthropic_yolu_arac_suresini_kullaniyor():
    import inspect
    from app.services import llm
    kaynak = inspect.getsource(llm)
    assert "timeout=arac_suresi(tu.name)" in kaynak


def test_wiki_write_onayi_onay_payini_alir(monkeypatch):
    # f1-arac wiki_write'ı CRITICAL_TOOLS'a koydu; f2'nin onay_payi'si onu kapsamalı
    import app.config as cfg
    from app.services.tools import approval_gate as g
    monkeypatch.setattr(cfg, "TOOL_APPROVAL_ENABLED", True)
    assert "wiki_write" in g.CRITICAL_TOOLS
    assert runner.arac_suresi("wiki_write") == runner.TOOL_TIMEOUT + g.APPROVAL_TIMEOUT_SECONDS


def test_check_updates_onay_payi_ile_toplanir(monkeypatch):
    from app.services.tools import approval_gate as g
    monkeypatch.setattr(g, "ALWAYS_APPROVE", set(g.ALWAYS_APPROVE) | {"check_updates"})
    assert runner.arac_suresi("check_updates") == 60.0 + g.APPROVAL_TIMEOUT_SECONDS
