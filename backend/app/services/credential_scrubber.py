"""Credential scrubber — masks secrets in tool results before they enter the LLM context."""

from __future__ import annotations

import re

# Patterns: (name, regex, replacement)
_PATTERNS: list[tuple[str, re.Pattern[str], str]] = [
    # API keys / tokens — value after = or :
    (
        "api_key",
        re.compile(
            r'(?i)(api[_-]?key|access[_-]?token|secret[_-]?key|auth[_-]?token'
            r'|bearer|authorization|x-api-key)\s*[=:]\s*["\']?([A-Za-z0-9\-_./+]{16,})["\']?',
            re.IGNORECASE,
        ),
        r'\1=***REDACTED***',
    ),
    # Common secret variable names
    (
        "secret_vars",
        re.compile(
            r'(?i)(password|passwd|secret|private[_-]?key|database[_-]?url'
            r'|db[_-]?pass|smtp[_-]?pass|jwt[_-]?secret|elevenlabs[_-]?api'
            r'|openrouter[_-]?api|anthropic[_-]?api|openai[_-]?api)\s*[=:]\s*["\']?(\S{6,})["\']?',
            re.IGNORECASE,
        ),
        r'\1=***REDACTED***',
    ),
    # sk-or-v1-... / sk-... OpenAI/OpenRouter style
    (
        "sk_keys",
        re.compile(r'\b(sk-(?:or-v1-)?[A-Za-z0-9]{20,})\b'),
        '***REDACTED***',
    ),
    # Bearer tokens in Authorization headers
    (
        "bearer",
        re.compile(r'Bearer\s+[A-Za-z0-9\-_./+]{16,}', re.IGNORECASE),
        'Bearer ***REDACTED***',
    ),
    # PostgreSQL / Redis DSNs with embedded password
    (
        "dsn",
        re.compile(r'(postgresql|redis|mysql|mongodb)://[^:]+:[^@]+@'),
        r'\1://***:***@',
    ),
    # SSH private key blocks
    (
        "ssh_key",
        re.compile(r'-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----', re.DOTALL),
        '-----BEGIN PRIVATE KEY----- ***REDACTED*** -----END PRIVATE KEY-----',
    ),
    # ── P1 E (denetim 10-06, madde 6) — JSON/YAML anahtarları + önekli anahtarlar ──
    # Eski desenler `KEY=deger` biçimini yakalıyordu; JSON'da anahtar adından sonra tırnak
    # geldiği için (`"api_key": "…"`) hiçbiri eşleşmiyordu. Google token dosyası
    # (`refresh_token`, `client_secret`) ve çıplak önekli anahtarlar modele aynen gidiyordu.
    # Ad SONU eşleşir: `max_tokens`/`input_tokens` (`token` ile bitmez) dokunulmaz.
    (
        "json_alan",
        re.compile(
            r'(?i)(["\']?\b[\w.-]*?(?:api[_-]?key|apikey|token|secret|passw(?:or)?d|private[_-]?key'
            r'|credentials?)["\']?\s*[=:]\s*["\']?)([^\s"\',}\]]{8,})'
        ),
        r'\1***REDACTED***',
    ),
    ("groq", re.compile(r'\bgsk_[A-Za-z0-9]{20,}'), '***REDACTED***'),
    ("google_api", re.compile(r'\bAIza[0-9A-Za-z_\-]{30,}'), '***REDACTED***'),
    ("anthropic", re.compile(r'\bsk-ant-[A-Za-z0-9_\-]{20,}'), '***REDACTED***'),
    ("sk_tireli", re.compile(r'\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_\-]{32,}'), '***REDACTED***'),
    ("github", re.compile(r'\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})'), '***REDACTED***'),
    ("telegram_bot", re.compile(r'\b\d{8,10}:[A-Za-z0-9_\-]{35}\b'), '***REDACTED***'),
    ("google_oauth", re.compile(r'(?:\bya29\.[0-9A-Za-z_\-]{20,}|\b1//0[0-9A-Za-z_\-]{30,})'), '***REDACTED***'),
    ("google_client_secret", re.compile(r'\bGOCSPX-[0-9A-Za-z_\-]{20,}'), '***REDACTED***'),
    ("aws", re.compile(r'\bAKIA[0-9A-Z]{16}\b'), '***REDACTED***'),
    ("slack", re.compile(r'\bxox[abposr]-[A-Za-z0-9\-]{10,}'), '***REDACTED***'),
    ("huggingface", re.compile(r'\bhf_[A-Za-z0-9]{30,}'), '***REDACTED***'),
]

# Maximum chars in a single tool result sent to LLM (prevents token exhaustion from large file reads)
_MAX_TOOL_RESULT_CHARS = 8_000


def scrub(text: str) -> str:
    """Apply all credential patterns and truncate oversized results."""
    if not isinstance(text, str):
        text = str(text)

    for _name, pattern, replacement in _PATTERNS:
        text = pattern.sub(replacement, text)

    if len(text) > _MAX_TOOL_RESULT_CHARS:
        text = text[:_MAX_TOOL_RESULT_CHARS] + f"\n... [içerik kısaltıldı — {len(text)} karakter toplam]"

    return text
