from __future__ import annotations

import re


SENSITIVE_TEXT_PATTERNS = (
    re.compile(r"(?i)(api[_-]?key|token|secret|password|authorization)\s*[:=]\s*([^\s'\"`]+)"),
    re.compile(r"(?i)bearer\s+[a-z0-9._~+/=-]{12,}"),
    re.compile(
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
        re.DOTALL,
    ),
)


def redact_sensitive_text(value: object) -> str:
    redacted = str(value)
    for pattern in SENSITIVE_TEXT_PATTERNS:
        redacted = pattern.sub(
            lambda match: f"{match.group(1)}=[redacted]" if match.lastindex else "[redacted]",
            redacted,
        )
    return redacted
