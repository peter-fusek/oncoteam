"""Request-scoped context utilities.

Extracted from dashboard_api.py to break circular imports with
oncofiles_client.py and autonomous.py.
"""

from __future__ import annotations

import contextvars
import logging
import uuid

from .patient_context import get_patient_token

_logger = logging.getLogger(__name__)

# ── Request correlation ID ─────────────────────────────────────────────
# Short UUID generated per API request for log correlation.
_CORRELATION_ID: contextvars.ContextVar[str] = contextvars.ContextVar("_CORRELATION_ID", default="")


def new_correlation_id() -> str:
    """Generate a short correlation ID (8 hex chars)."""
    return uuid.uuid4().hex[:8]


def get_correlation_id() -> str:
    """Return current request's correlation ID (empty if none)."""
    return _CORRELATION_ID.get()


def set_correlation_id(cid: str) -> None:
    """Set the current request's correlation ID."""
    _CORRELATION_ID.set(cid)


# ── Patient token resolution ──────────────────────────────────────────

# Per-patient counter for admin-bearer fallback observations — incremented
# when get_token_for_patient returns None for a non-q1b patient because the
# per-patient token isn't registered. Exposed via /api/diagnostics (#435
# Item 2). Oncofiles#478 now turns the downstream read into a "no access"
# sentinel, but the oncoteam-side counter is the defense-in-depth signal
# so the regression is visible before oncofiles's peer-layer defense hides it.
_ADMIN_FALLBACK_COUNTS: dict[str, int] = {}


def get_tenant_isolation_stats() -> dict:
    """Snapshot of tenant-isolation telemetry for /api/diagnostics (#435 Item 2)."""
    return {
        "admin_bearer_fallbacks_total": sum(_ADMIN_FALLBACK_COUNTS.values()),
        "admin_bearer_fallbacks_by_patient": dict(_ADMIN_FALLBACK_COUNTS),
    }


def reset_tenant_isolation_stats() -> None:
    """Test-only reset of the admin-bearer fallback counter."""
    _ADMIN_FALLBACK_COUNTS.clear()


def get_token_for_patient(patient_id: str) -> str | None:
    """Get the oncofiles bearer token for a patient. None = default (q1b)."""
    if not patient_id or patient_id == "q1b":
        return None  # Admin bearer = q1b in multi-patient mode
    token = get_patient_token(patient_id)
    if token is None:
        # Non-q1b patient with no registered per-patient token — caller will
        # fall back to admin bearer, which oncofiles#478 now rejects with a
        # no-access sentinel. Log + count so the fallback rate is visible
        # from /api/diagnostics before any silent cross-tenant leak can form.
        # See memory/feedback_fail-closed-on-missing-tenant.md.
        _ADMIN_FALLBACK_COUNTS[patient_id] = _ADMIN_FALLBACK_COUNTS.get(patient_id, 0) + 1
        _logger.warning(
            "tenant_isolation.admin_bearer_fallback",
            extra={
                "patient_id": patient_id,
                "correlation_id": get_correlation_id() or "",
                "total_for_patient": _ADMIN_FALLBACK_COUNTS[patient_id],
            },
        )
    return token
