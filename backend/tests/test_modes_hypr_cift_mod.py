"""mod yöneticisinin Hyprland dispatch'i conf + Lua ayarında çalışmalı.

Hyprland 0.56+ `hyprland.lua` ile açılınca eski `hyprctl dispatch togglespecialworkspace x`
çıkış 7 ile ölür; 0.57'de conf biçimi tamamen kalkıyor. Sahte yanıtlar 0.56.2'de ölçüldü
(2026-09-27): conf oturumu Lua biçimine "Invalid dispatcher", Lua oturumu eski biçime 7.
"""
from types import SimpleNamespace

import pytest

from app.services.tools import modes


class FakeHyprctl:
    def __init__(self, config):
        self.config = config
        self.calls = []

    def __call__(self, argv, **kwargs):
        self.calls.append(argv)
        lua = len(argv) == 3 and argv[2].startswith("hl.dsp.")
        if self.config == "lua":
            if lua:
                return SimpleNamespace(stdout="ok", stderr="", returncode=0)
            return SimpleNamespace(stdout="", stderr="error: dispatch in lua is a shorthand for hl.dispatch(...)",
                                   returncode=7)
        return SimpleNamespace(stdout="Invalid dispatcher" if lua else "ok", stderr="", returncode=0)


@pytest.fixture(params=["conf", "lua"])
def hyprctl(monkeypatch, request):
    fake = FakeHyprctl(request.param)
    monkeypatch.setattr(modes.subprocess, "run", fake)
    monkeypatch.setattr(modes, "detect_env", lambda: {"features": {
        "specials": True, "workspace_move": True, "workspaces": True}, "os": "linux"})
    return fake


CASES = [
    ({"special": "notlar"},
     'hl.dsp.workspace.toggle_special("notlar")', ["togglespecialworkspace", "notlar"]),
    ({"workspace": "3"},
     'hl.dsp.focus({ workspace = "3", on_current_monitor = true })', ["focusworkspaceoncurrentmonitor", "3"]),
    ({"workspace": "kod"},
     'hl.dsp.focus({ workspace = "name:kod" })', ["workspace", "name:kod"]),
]


@pytest.mark.parametrize("mode,lua,legacy", CASES)
def test_reveal_ws_dual_mode(hyprctl, mode, lua, legacy):
    ok, _ = modes._reveal_ws(mode)
    assert ok
    assert hyprctl.calls[0] == ["hyprctl", "dispatch", lua]
    if hyprctl.config == "lua":
        assert len(hyprctl.calls) == 1  # Lua tuttuysa eski biçim hiç gönderilmez
    else:
        assert hyprctl.calls[1] == ["hyprctl", "dispatch", *legacy]


def test_move_new_win_dual_mode(hyprctl, monkeypatch):
    monkeypatch.setattr(modes.time, "sleep", lambda _: None)
    monkeypatch.setattr(modes, "_get_window_addrs", lambda env: {"0x1", "0x2"})
    assert modes._move_new_win({"0x1"}, "special:yan", {}) is True
    assert hyprctl.calls[0] == ["hyprctl", "dispatch",
                                'hl.dsp.window.move({ workspace = "special:yan", follow = false, window = "address:0x2" })']
    if hyprctl.config == "conf":
        assert hyprctl.calls[1] == ["hyprctl", "dispatch", "movetoworkspacesilent", "special:yan,address:0x2"]


def test_lua_str_escapes_quotes_and_backslash():
    assert modes._lua_str('a"b\\c') == '"a\\"b\\\\c"'
