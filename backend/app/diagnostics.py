"""Small public diagnostic boundary; never apply text rules to domain identifiers."""
import re

PUBLIC_TEXT_MAX = 500
PUBLIC_DIAGNOSTIC_FIELDS = frozenset({
    "error", "message", "last_error", "reason", "reasons", "last_reason",
    "manual_kill_reason", "warnings",
})
_URL = re.compile(r"(?i)\b(?:https?|wss?)://[^\s<>\"']+")
# Quoted values may contain whitespace. Authorization consumes scheme AND value
# in one match, before the generic secret rule can consume just the scheme.
_VALUE = r'''(?:\[REDACTED\]|"[^"\n]*"|'[^'\n]*'|[^\s,;\]}"']+)'''
_AUTH = re.compile(
    r'''(?i)(\b(?:proxy[-_]authorization|authorization)["']?\s*[:=]\s*)'''
    + r'''(?:["'](?:bearer|basic)\s+[^"'\n]*["']|(?:bearer|basic)\s+'''
    + _VALUE + r"|" + _VALUE + r")"
)
_SECRET = re.compile(
    r'''(?i)(\b(?:x[-_]api[-_]key|api[_-]?key|access[_-]token|token|client[_-]secret|secret|private[_-]?key)["']?\s*[:=]\s*)'''
    + _VALUE
)
_PRIVATE_KEY = re.compile(r"0x[0-9a-fA-F]{64}\b")


def sanitize_public_text(value, *, secrets=(), max_length=PUBLIC_TEXT_MAX):
    """Redact before bounding, including known credentials without a label."""
    text = str(value)
    text = _URL.sub("[provider URL]", text)
    text = _AUTH.sub(r"\1[REDACTED]", text)
    text = _SECRET.sub(r"\1[REDACTED]", text)
    text = _PRIVATE_KEY.sub("[REDACTED]", text)
    for secret in secrets:
        if secret:
            text = text.replace(secret, "[REDACTED]")
    return text if max_length is None else text[:max_length]


def sanitize_public_diagnostic(value):
    """Sanitize every string within an explicitly selected diagnostic container."""
    if isinstance(value, dict):
        return {sanitize_public_text(k) if isinstance(k, str) else k:
                sanitize_public_diagnostic(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [sanitize_public_diagnostic(v) for v in value]
    return sanitize_public_text(value) if isinstance(value, str) else value


def sanitize_public_payload(value, key=None):
    """Copy serialized observations, selecting only allowlisted diagnostic fields."""
    if key in PUBLIC_DIAGNOSTIC_FIELDS:
        return sanitize_public_diagnostic(value)
    if isinstance(value, dict):
        return {k: sanitize_public_payload(v, k) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [sanitize_public_payload(v) for v in value]
    return value
