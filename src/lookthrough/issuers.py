"""Issuer normalization helpers shared by look-through entry points."""

from __future__ import annotations


def normalize_issuer(issuer: str | None) -> str | None:
    if issuer is None:
        return None

    normalized = issuer.strip().lower()
    if "ishares" in normalized:
        return "ishares"
    if "vaneck" in normalized:
        return "vaneck"
    if "state street" in normalized or "ssga" in normalized or "spdr" in normalized:
        return "ssga"
    if "global x" in normalized:
        return "globalx"
    if "amundi" in normalized or "lyxor" in normalized:
        return "lyxor"
    return None
