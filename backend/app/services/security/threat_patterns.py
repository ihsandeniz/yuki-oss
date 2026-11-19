"""Tehdit deseni kütüphanesi — prompt injection / promptware / sır sızdırma tespiti.

Desenler Nous Research'ün açık kaynak ajan projesindeki `tools/threat_patterns.py`
dosyasından uyarlandı (MIT lisansı; kaynak ve telif metni NOTICE'ta) ve Türkçe karşılıklarla genişletildi.

Her desen ``(regex, pattern_id, scope)``:

- ``"all"``      — her yerde (klasik prompt injection, sızdırma)
- ``"context"``  — bağlam + araç sonuçları (promptware, rol ele geçirme, asistana seslenme)
- ``"strict"``   — yalnız kullanıcı aracılı yazımlar (kalıcılık, SSH); araç sonucu için çok gürültülü

Araç sonuçları kullanıcının YAZMADIĞI içerik taşır: orada geniş TESPİT isteriz, engel değil.
Desenler kesin saldırı davranışına çıpalanır, "buyurgan cümle"ye değil ("you must" tek başına
çok yaygın). Çok kelimeli atlatmayı önlemek için anahtar sözcükler arasında ``(?:\\w+\\s+)*``.
"""
from __future__ import annotations

import os
import re

_PATTERNS: list[tuple[str, str, str]] = [
    # ── Klasik prompt injection ──────────────────────────────────────
    (r'ignore\s+(?:\w+\s+)*(previous|all|above|prior)\s+(?:\w+\s+)*instructions', "prompt_injection", "all"),
    (r'(önceki|yukarıdaki|tüm|bütün)\s+(?:\w+\s+)*(talimat|komut|kural)lar[ıi]?[nsıi]*\s+(?:\w+\s+)*(yok\s*say|görmezden\s*gel|unut)',
     "prompt_injection_tr", "all"),
    (r'system\s+prompt\s+override', "sys_prompt_override", "all"),
    (r'disregard\s+(?:\w+\s+)*(your|all|any)\s+(?:\w+\s+)*(instructions|rules|guidelines)', "disregard_rules", "all"),
    (r'act\s+as\s+(if|though)\s+(?:\w+\s+)*you\s+(?:\w+\s+)*(have\s+no|don\'t\s+have)\s+(?:\w+\s+)*(restrictions|limits|rules)',
     "bypass_restrictions", "all"),
    (r'<!--[^>]*(?:ignore|override|system|secret|hidden|asistan|assistant)[^>]*-->', "html_comment_injection", "all"),
    (r'<\s*div\s+style\s*=\s*["\'][\s\S]*?display\s*:\s*none', "hidden_div", "all"),
    (r'translate\s+.*\s+into\s+.*\s+and\s+(execute|run|eval)', "translate_execute", "all"),
    (r'do\s+not\s+(?:\w+\s+)*tell\s+(?:\w+\s+)*the\s+user', "deception_hide", "all"),
    (r'kullanıcıya\s+(?:\w+\s+)*(söyleme|belli\s*etme|haber\s*verme|bahsetme)', "deception_hide_tr", "all"),

    # ── Metni işleyen asistana seslenme ("bu dosyayı özetleyen asistan … eklemelidir") ──
    (r'\b(bu|şu)\s+(?:\w+\s+){0,3}(özetleyen|okuyan|işleyen|çeviren|inceleyen)\s+(asistan|yapay\s*zek[aâ]|model)',
     "addresses_assistant_tr", "context"),
    (r'\b(assistant|ai|model)\s+(reading|summari[sz]ing|processing|translating)\s+this\b', "addresses_assistant", "context"),

    # ── Rol değiştirme / kimlik ele geçirme ──────────────────────────
    (r'you\s+are\s+(?:\w+\s+)*now\s+(?:a|an|the)\s+', "role_hijack", "context"),
    (r'pretend\s+(?:\w+\s+)*(you\s+are|to\s+be)\s+', "role_pretend", "context"),
    (r'(output|reveal|print|show)\s+(?:\w+\s+)*(system|initial)\s+prompt', "leak_system_prompt", "context"),
    (r'(sistem|başlangıç)\s+prompt[’\'u]*\s*(nu)?\s+(yazdır|göster|çıktıla|ver)', "leak_system_prompt_tr", "context"),
    (r'(respond|answer|reply)\s+without\s+(?:\w+\s+)*(restrictions|limitations|filters|safety)', "remove_filters", "context"),
    (r'you\s+have\s+been\s+(?:\w+\s+)*(updated|upgraded|patched)\s+to', "fake_update", "context"),
    (r'\bname\s+yourself\s+\w+', "identity_override", "context"),

    # ── C2 tarzı promptware ──────────────────────────────────────────
    (r'register\s+(as\s+)?a?\s*node', "c2_node_registration", "context"),
    (r'(heartbeat|beacon|check[\s\-]?in)\s+(to|with)\s+', "c2_heartbeat", "context"),
    (r'pull\s+(down\s+)?(?:new\s+)?task(?:ing|s)?\b', "c2_task_pull", "context"),
    (r'connect\s+to\s+the\s+network\b', "c2_network_connect", "context"),
    (r'you\s+must\s+(?:\w+\s+){0,3}(register|connect|report|beacon)\b', "forced_action", "context"),
    (r'only\s+use\s+one[\s\-]?liners?\b', "anti_forensic_oneliner", "context"),
    (r'never\s+(?:\w+\s+)*(?:create|write)\s+(?:\w+\s+)*(?:script|file)\s+(?:\w+\s+)*disk', "anti_forensic_disk", "context"),
    (r'unset\s+\w*(?:CLAUDE|CODEX|AGENT|OPENAI|ANTHROPIC|OPENROUTER|YUKI)\w*', "env_var_unset_agent", "context"),
    (r'\b(?:cobalt\s*strike|sliver|havoc|mythic|metasploit|brainworm)\b', "known_c2_framework", "context"),
    (r'\bc2\s+(?:server|channel|infrastructure|beacon)\b', "c2_explicit", "context"),
    (r'\bcommand\s+and\s+control\b', "c2_explicit_long", "context"),

    # ── Sır sızdırma ─────────────────────────────────────────────────
    (r'curl\s+[^\n]*\$\{?\w*(KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|API)', "exfil_curl", "all"),
    (r'curl\s+[^\n]*(-d|--data[\w-]*|-F|-T)\s+@', "exfil_curl_file", "all"),
    (r'wget\s+[^\n]*\$\{?\w*(KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|API)', "exfil_wget", "all"),
    (r'cat\s+[^\n]*(\.env|credentials|\.netrc|\.pgpass|\.npmrc|\.pypirc|gizli|secret)', "read_secrets", "all"),
    (r'(send|post|upload|transmit)\s+.*\s+(to|at)\s+https?://', "send_to_url", "strict"),
    (r'(include|output|print|share)\s+(?:\w+\s+)*(conversation|chat\s+history|previous\s+messages|full\s+context|entire\s+context)',
     "context_exfil", "strict"),

    # ── Kalıcılık / SSH (strict) ─────────────────────────────────────
    (r'authorized_keys', "ssh_backdoor", "strict"),
    (r'\$HOME/\.ssh|\~/\.ssh', "ssh_access", "strict"),
    (r'\$HOME/\.env|\~/\.env', "env_access", "strict"),
    (r'(update|modify|edit|write|change|append|add\s+to)\s+.*(?:AGENTS\.md|CLAUDE\.md|\.cursorrules|\.clinerules)',
     "agent_config_mod", "strict"),
    (r'(?:api[_-]?key|token|secret|password)\s*[=:]\s*["\'][A-Za-z0-9+/=_-]{20,}', "hardcoded_secret", "strict"),
]

#: Injection'da kullanılan görünmez / çift yönlü unicode karakterler.
INVISIBLE_CHARS = frozenset({
    "\u200b", "\u200c", "\u200d", "\u2060", "\u2062", "\u2063", "\u2064", "\ufeff",
    "\u202a", "\u202b", "\u202c", "\u202d", "\u202e",
    "\u2066", "\u2067", "\u2068", "\u2069",
})


def _derle() -> dict[str, list[tuple[re.Pattern, str]]]:
    """"all" her sete, "context" context+strict'e, "strict" yalnız strict'e girer."""
    setler: dict[str, list[tuple[re.Pattern, str]]] = {"all": [], "context": [], "strict": []}
    kapsar = {"all": ("all", "context", "strict"), "context": ("context", "strict"), "strict": ("strict",)}
    for desen, pid, kapsam in _PATTERNS:
        if kapsam not in kapsar:
            raise ValueError(f"threat_patterns: bilinmeyen scope {kapsam!r} (desen {pid!r})")
        derli = re.compile(desen, re.IGNORECASE)
        for s in kapsar[kapsam]:
            setler[s].append((derli, pid))
    return setler


_COMPILED = _derle()


def is_enabled() -> bool:
    """`THREAT_SCAN_ENABLED` ortam değişkeni (varsayılan açık)."""
    return os.getenv("THREAT_SCAN_ENABLED", "1").lower() not in ("0", "false", "no", "")


def scan_for_threats(content: str, scope: str = "context") -> list[str]:
    """``content`` içinde ``scope``'ta eşleşen pattern_id listesi; tarama kapalıysa boş liste."""
    if not content or not is_enabled():
        return []
    desenler = _COMPILED.get(scope)
    if desenler is None:
        raise ValueError(f"scan_for_threats: bilinmeyen scope {scope!r}")
    bulgular = [f"invisible_unicode_U+{ord(ch):04X}" for ch in sorted(set(content) & INVISIBLE_CHARS)]
    bulgular += [pid for derli, pid in desenler if derli.search(content)]
    return bulgular


__all__ = ["INVISIBLE_CHARS", "is_enabled", "scan_for_threats"]
