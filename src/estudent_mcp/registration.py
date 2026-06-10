"""Pure helpers for the two-step registration confirmation invariant.

The fingerprint binds a confirm call to a specific preview: confirm_registration
recomputes the fingerprint from its items and rejects the call unless it matches
the one the preview returned. This makes it impossible to submit a real change
without first going through preview.
"""

from __future__ import annotations

import hashlib
import json

from .models import RegistrationItem


def compute_fingerprint(items: list[RegistrationItem]) -> str:
    """Deterministic hash of a registration action set.

    Order-independent (sorted) so the fingerprint reflects *what* will change,
    not the order items were listed.
    """
    normalized = sorted(
        (
            {
                "action": it.action,
                "subject_code": it.subject_code.upper().strip(),
                "section": it.section.upper().strip(),
            }
            for it in items
        ),
        key=lambda d: (d["action"], d["subject_code"], d["section"]),
    )
    payload = json.dumps(normalized, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def summarize(items: list[RegistrationItem]) -> str:
    """Human-readable one-line-per-item summary for the preview."""
    if not items:
        return "(no actions)"
    lines = []
    for it in items:
        verb = "ADD" if it.action == "add" else "DROP"
        sect = f" [{it.section}]" if it.section else ""
        lines.append(f"{verb} {it.subject_code.upper()}{sect}")
    return "\n".join(lines)
