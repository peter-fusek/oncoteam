"""Oncopanel Inbox API (#399 Sprint 96 S1).

The extraction agent (`run_oncopanel_extraction_single` in `autonomous_tasks`)
writes each NGS report it parses to agent_state under the key
`pending_oncopanel:{patient_id}:{document_id}`. Per the #395 principle —
AI proposes, humans dispose — these pending entries are NEVER auto-merged
into `PatientProfile.oncopanel_history`. A physician must review + approve.

Endpoints:
    GET  /api/oncopanel/pending     — list pending (+ recently triaged) items
    POST /api/oncopanel/pending     — approve or dismiss a pending item

Approve flow:
    1. Parse the LLM's ```json fenced block from `raw_response`.
    2. Build a strict `Oncopanel` model (physician can optionally override
       fields in `panel` body).
    3. Persist `approved_oncopanel:{patient_id}:{panel_id}` in agent_state.
    4. Append to the in-memory `PatientRegistry` oncopanel_history so
       dashboard surfaces + eligibility rules pick it up immediately.
    5. Mark the pending entry as status=approved (kept for audit — nothing
       is deleted).
    6. Append an entry to `oncopanel_audit:{patient_id}` (append-only list).

Dismiss flow:
    Same as above minus steps 3 + 4; pending entry flips to status=dismissed.

Audit trail lives in agent_state key `oncopanel_audit:{patient_id}` as a
list of events. Each event: {event_id, ts, actor_*, action, document_id,
panel_id, rationale}. Event IDs are uuid4. The list is append-only; the
writer does a read-modify-write but never rewrites prior entries.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError
from starlette.requests import Request
from starlette.responses import JSONResponse

from .activity_logger import record_suppressed_error
from .models import FunnelActorType, Oncopanel
from .oncofiles_client import get_agent_state, list_agent_states, set_agent_state
from .patient_context import append_approved_oncopanel
from .request_context import get_token_for_patient as _get_token_for_patient

_logger = logging.getLogger("oncoteam.api_oncopanel")

_JSON_FENCE_RE = re.compile(r"```json\s*(?P<body>\{.*?\})\s*```", re.DOTALL)


def _cors_json(data: dict, status_code: int = 200, request: Request | None = None) -> JSONResponse:
    from .dashboard_api import _cors_json as _cj

    return _cj(data, status_code=status_code, request=request)


def _get_patient_id(request: Request) -> str:
    from .dashboard_api import _get_patient_id as _gpi

    return _gpi(request)


async def _parse_json_body(request: Request) -> dict:
    from .dashboard_api import _parse_json_body as _pjb

    return await _pjb(request)


def _actor_from_request(
    request: Request, body: dict | None = None
) -> tuple[FunnelActorType, str, str]:
    h = request.headers
    actor_type_raw = h.get("X-Actor-Type") or (body or {}).get("actor_type") or "human"
    actor_id = h.get("X-Actor-Id") or (body or {}).get("actor_id", "physician")
    actor_display = h.get("X-Actor-Display-Name") or (body or {}).get(
        "actor_display_name", actor_id
    )
    try:
        actor_type = FunnelActorType(actor_type_raw)
    except ValueError:
        actor_type = FunnelActorType.HUMAN
    return actor_type, actor_id, actor_display


def _extract_json_block(text: str) -> dict | None:
    """Pull the first ```json fenced block out of a Claude response.

    Falls back to the first top-level {...} object if the fenced form
    wasn't produced (older extractions).
    """
    if not text:
        return None
    m = _JSON_FENCE_RE.search(text)
    if m:
        try:
            return json.loads(m.group("body"))
        except json.JSONDecodeError:
            pass
    # Fallback: first balanced-brace object. Naive but good enough.
    first = text.find("{")
    last = text.rfind("}")
    if first >= 0 and last > first:
        try:
            return json.loads(text[first : last + 1])
        except json.JSONDecodeError:
            return None
    return None


def _pending_key(patient_id: str, document_id: int | str) -> str:
    return f"pending_oncopanel:{patient_id}:{document_id}"


def _approved_key(patient_id: str, panel_id: str) -> str:
    return f"approved_oncopanel:{patient_id}:{panel_id}"


def _audit_key(patient_id: str) -> str:
    return f"oncopanel_audit:{patient_id}"


def _normalize_state(state: Any) -> dict | None:
    """oncofiles get_agent_state can return the value JSON-encoded, a dict,
    or wrapped in a `{"value": ...}` envelope. Normalize to a plain dict."""
    if state is None:
        return None
    if isinstance(state, str):
        try:
            return json.loads(state)
        except json.JSONDecodeError:
            return None
    if isinstance(state, dict):
        if "value" in state and isinstance(state["value"], (str, dict)):
            inner = state["value"]
            if isinstance(inner, str):
                try:
                    return json.loads(inner)
                except json.JSONDecodeError:
                    return None
            return inner
        return state
    return None


def _summary_from_panel_dict(panel: dict) -> dict:
    """UI-friendly extraction preview. Safe on malformed input."""
    variants = panel.get("variants") or []
    cnvs = panel.get("cnvs") or []
    return {
        "panel_id": panel.get("panel_id", ""),
        "report_date": panel.get("report_date", ""),
        "lab": panel.get("lab", ""),
        "methodology": panel.get("methodology", ""),
        "sample_type": panel.get("sample_type", ""),
        "msi_status": panel.get("msi_status", ""),
        "mmr_status": panel.get("mmr_status", ""),
        "tmb_score": panel.get("tmb_score"),
        "tmb_category": panel.get("tmb_category", ""),
        "variant_count": len(variants),
        "cnv_count": len(cnvs),
        "variants_preview": [
            {
                "gene": v.get("gene", ""),
                "protein_short": v.get("protein_short", ""),
                "tier": v.get("tier", ""),
                "significance": v.get("significance", ""),
                "vaf": v.get("vaf"),
            }
            for v in variants[:12]
        ],
    }


async def _append_audit_event(
    patient_id: str,
    event: dict,
    *,
    token: str | None,
) -> None:
    key = _audit_key(patient_id)
    try:
        existing = await get_agent_state(key, token=token)
    except Exception as e:
        record_suppressed_error("api_oncopanel", "audit_read", e)
        existing = None
    history = _normalize_state(existing) or {}
    events = history.get("events") if isinstance(history, dict) else None
    if not isinstance(events, list):
        events = []
    events.append(event)
    await set_agent_state(key, {"events": events}, token=token)


async def api_oncopanel_pending_get(request: Request) -> JSONResponse:
    """List pending oncopanel extractions for the current patient.

    Response:
        {
          "pending": [ {key, document_id, timestamp, status, summary, ...}, ... ],
          "recent_triaged": [ ... status ∈ {approved, dismissed} ... ],
          "count": N,
        }

    Approved + dismissed entries stay in the list (append-only — nothing
    disappears) but are separated for UI grouping. By default we return
    the last 20 triaged entries alongside the open ones.
    """
    patient_id = _get_patient_id(request)
    token = _get_token_for_patient(patient_id)

    try:
        raw = await list_agent_states(agent_id="oncoteam", limit=500, token=token)
    except Exception as e:
        record_suppressed_error("api_oncopanel", "list_agent_states", e)
        return _cors_json(
            {"pending": [], "recent_triaged": [], "count": 0, "error": "agent_state_unavailable"},
            request=request,
        )

    if isinstance(raw, dict):
        states = raw.get("states", [])
    elif isinstance(raw, list):
        states = raw
    else:
        states = []
    prefix = f"pending_oncopanel:{patient_id}:"

    pending: list[dict] = []
    triaged: list[dict] = []
    for st in states:
        if not isinstance(st, dict):
            continue
        key = st.get("key") or ""
        if not key.startswith(prefix):
            continue
        value = _normalize_state(st.get("value"))
        if not isinstance(value, dict):
            continue
        raw_response = value.get("raw_response", "") or ""
        panel_dict = _extract_json_block(raw_response) or {}
        summary = _summary_from_panel_dict(panel_dict) if panel_dict else None
        item = {
            "key": key,
            "document_id": value.get("document_id"),
            "timestamp": value.get("timestamp", ""),
            "status": value.get("status", "pending_physician_review"),
            "extraction_cost_usd": value.get("extraction_cost_usd", 0),
            "extraction_model": value.get("extraction_model", ""),
            "summary": summary,
            "approved_at": value.get("approved_at"),
            "approved_by": value.get("approved_by"),
            "dismissed_at": value.get("dismissed_at"),
            "dismissed_by": value.get("dismissed_by"),
            "rationale": value.get("rationale", ""),
            "parse_error": panel_dict == {} and bool(raw_response),
        }
        if item["status"] in ("approved", "dismissed"):
            triaged.append(item)
        else:
            pending.append(item)

    pending.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    triaged.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

    return _cors_json(
        {
            "pending": pending,
            "recent_triaged": triaged[:20],
            "count": len(pending),
        },
        request=request,
    )


async def api_oncopanel_pending_post(request: Request) -> JSONResponse:
    """Approve or dismiss a pending oncopanel entry.

    Body:
        action: "approve" | "dismiss"          (required)
        document_id: int | str                 (required)
        rationale: str                         (required — physician must
                                                explain why)
        panel: dict                            (optional — physician's
                                                edited Oncopanel payload;
                                                falls back to the parsed
                                                raw_response)
    """
    body = await _parse_json_body(request)
    if not isinstance(body, dict):
        return _cors_json({"error": "invalid body"}, status_code=400, request=request)

    action = (body.get("action") or "").strip().lower()
    if action not in ("approve", "dismiss"):
        return _cors_json(
            {"error": "action must be 'approve' or 'dismiss'"},
            status_code=400,
            request=request,
        )

    document_id = body.get("document_id")
    if document_id in (None, ""):
        return _cors_json({"error": "document_id is required"}, status_code=400, request=request)

    rationale = (body.get("rationale") or "").strip()
    if not rationale:
        return _cors_json({"error": "rationale is required"}, status_code=400, request=request)

    actor_type, actor_id, actor_display = _actor_from_request(request, body)
    if actor_type == FunnelActorType.AGENT:
        return _cors_json(
            {
                "error": "agents cannot triage oncopanel — physician approval required",
                "code": "agent_not_allowed",
            },
            status_code=403,
            request=request,
        )

    patient_id = _get_patient_id(request)
    token = _get_token_for_patient(patient_id)
    key = _pending_key(patient_id, document_id)

    try:
        existing_raw = await get_agent_state(key, token=token)
    except Exception as e:
        record_suppressed_error("api_oncopanel", "pending_read", e)
        return _cors_json({"error": "pending entry unavailable"}, status_code=503, request=request)
    existing = _normalize_state(existing_raw)
    if not isinstance(existing, dict) or not existing.get("timestamp"):
        return _cors_json(
            {"error": f"no pending entry for document_id={document_id}"},
            status_code=404,
            request=request,
        )

    if existing.get("status") in ("approved", "dismissed"):
        return _cors_json(
            {
                "error": (
                    f"entry already {existing.get('status')} "
                    f"by {existing.get('approved_by') or existing.get('dismissed_by') or '?'}"
                ),
                "code": "already_triaged",
            },
            status_code=409,
            request=request,
        )

    now_iso = datetime.now(UTC).isoformat()
    event_id = uuid.uuid4().hex

    if action == "dismiss":
        updated = {
            **existing,
            "status": "dismissed",
            "dismissed_at": now_iso,
            "dismissed_by": actor_id,
            "dismissed_by_display": actor_display,
            "rationale": rationale,
        }
        try:
            await set_agent_state(key, updated, token=token)
        except Exception as e:
            record_suppressed_error("api_oncopanel", "dismiss_write", e)
            return _cors_json(
                {"error": "failed to persist dismissal"},
                status_code=503,
                request=request,
            )
        await _append_audit_event(
            patient_id,
            {
                "event_id": event_id,
                "ts": now_iso,
                "actor_type": actor_type.value,
                "actor_id": actor_id,
                "actor_display_name": actor_display,
                "action": "dismiss",
                "document_id": document_id,
                "rationale": rationale,
            },
            token=token,
        )
        return _cors_json(
            {"status": "dismissed", "document_id": document_id, "event_id": event_id},
            request=request,
        )

    # ── approve path ────────────────────────────────
    panel_override = body.get("panel")
    if panel_override is None:
        panel_override = _extract_json_block(existing.get("raw_response", "") or "")
    if not isinstance(panel_override, dict) or not panel_override:
        return _cors_json(
            {
                "error": (
                    "no parseable panel JSON in raw_response; "
                    "edit the `panel` body field or dismiss + re-extract"
                ),
                "code": "panel_unparseable",
            },
            status_code=400,
            request=request,
        )

    # Fill required-by-model fields with sensible defaults if the extractor
    # omitted them.
    panel_override.setdefault("patient_id", patient_id)
    panel_override.setdefault(
        "panel_id", f"{patient_id}_oncopanel_{existing.get('document_id', 'unknown')}"
    )
    panel_override.setdefault("source_document_id", str(existing.get("document_id", "")))
    panel_override["verified_by"] = actor_display
    panel_override["verified_at"] = now_iso
    panel_override["verified_status"] = "approved"
    panel_override["verification_notes"] = rationale

    try:
        panel = Oncopanel.model_validate(panel_override)
    except ValidationError as e:
        return _cors_json(
            {
                "error": "extracted oncopanel fails schema validation",
                "code": "panel_invalid",
                "details": e.errors(),
            },
            status_code=400,
            request=request,
        )

    try:
        await set_agent_state(
            _approved_key(patient_id, panel.panel_id),
            panel.model_dump(mode="json"),
            token=token,
        )
    except Exception as e:
        record_suppressed_error("api_oncopanel", "approved_write", e)
        return _cors_json(
            {"error": "failed to persist approved panel"},
            status_code=503,
            request=request,
        )

    # Best-effort in-process merge — gives immediate consistency on this
    # process. Cross-process consistency relies on a startup rehydration
    # or an on-demand reader, tracked as a Sprint 96 S1 follow-up.
    try:
        append_approved_oncopanel(patient_id, panel)
    except Exception as e:
        record_suppressed_error("api_oncopanel", "memory_merge", e)

    updated = {
        **existing,
        "status": "approved",
        "approved_at": now_iso,
        "approved_by": actor_id,
        "approved_by_display": actor_display,
        "panel_id": panel.panel_id,
        "rationale": rationale,
    }
    try:
        await set_agent_state(key, updated, token=token)
    except Exception as e:
        record_suppressed_error("api_oncopanel", "approve_pending_update", e)

    await _append_audit_event(
        patient_id,
        {
            "event_id": event_id,
            "ts": now_iso,
            "actor_type": actor_type.value,
            "actor_id": actor_id,
            "actor_display_name": actor_display,
            "action": "approve",
            "document_id": existing.get("document_id"),
            "panel_id": panel.panel_id,
            "rationale": rationale,
            "variant_count": len(panel.variants),
            "cnv_count": len(panel.cnvs),
        },
        token=token,
    )

    return _cors_json(
        {
            "status": "approved",
            "document_id": existing.get("document_id"),
            "panel_id": panel.panel_id,
            "event_id": event_id,
        },
        request=request,
    )


async def api_oncopanel_audit_get(request: Request) -> JSONResponse:
    """GET /api/oncopanel/audit — patient-wide triage timeline (newest first)."""
    patient_id = _get_patient_id(request)
    token = _get_token_for_patient(patient_id)
    try:
        raw = await get_agent_state(_audit_key(patient_id), token=token)
    except Exception as e:
        record_suppressed_error("api_oncopanel", "audit_get", e)
        return _cors_json(
            {"events": [], "count": 0, "error": "agent_state_unavailable"},
            request=request,
        )
    value = _normalize_state(raw) or {}
    events = value.get("events") if isinstance(value, dict) else None
    if not isinstance(events, list):
        events = []
    events_sorted = sorted(events, key=lambda e: e.get("ts", ""), reverse=True)
    return _cors_json({"events": events_sorted, "count": len(events_sorted)}, request=request)


# ── /research active-tab preference (cross-device per-user state) ──────


_VALID_RESEARCH_TABS = frozenset(
    {
        "inbox",
        "funnel",
        "literature",
        "news",
        "discussion",
        "audit",
        "watchlist",
        "resurfaced",
    }
)


def _active_tab_key(patient_id: str, actor_id: str) -> str:
    # Per-user + per-patient because the same physician may review q1b on
    # one tab and another patient on another.
    return f"research_active_tab:{patient_id}:{actor_id}"


async def api_research_active_tab_get(request: Request) -> JSONResponse:
    """GET /api/research/active-tab — current user's preferred /research tab."""
    patient_id = _get_patient_id(request)
    _, actor_id, _ = _actor_from_request(request, None)
    token = _get_token_for_patient(patient_id)
    try:
        raw = await get_agent_state(_active_tab_key(patient_id, actor_id), token=token)
    except Exception as e:
        record_suppressed_error("api_oncopanel", "active_tab_get", e)
        return _cors_json({"tab": None, "error": "agent_state_unavailable"}, request=request)
    value = _normalize_state(raw)
    tab = (value or {}).get("tab") if isinstance(value, dict) else None
    if tab not in _VALID_RESEARCH_TABS:
        tab = None
    return _cors_json({"tab": tab}, request=request)


async def api_research_active_tab_post(request: Request) -> JSONResponse:
    """POST /api/research/active-tab — persist the user's active tab."""
    body = await _parse_json_body(request)
    if not isinstance(body, dict):
        return _cors_json({"error": "invalid body"}, status_code=400, request=request)
    tab = (body.get("tab") or "").strip().lower()
    if tab not in _VALID_RESEARCH_TABS:
        return _cors_json(
            {"error": f"tab must be one of {sorted(_VALID_RESEARCH_TABS)}"},
            status_code=400,
            request=request,
        )
    patient_id = _get_patient_id(request)
    _, actor_id, _ = _actor_from_request(request, body)
    token = _get_token_for_patient(patient_id)
    try:
        await set_agent_state(
            _active_tab_key(patient_id, actor_id),
            {"tab": tab, "updated_at": datetime.now(UTC).isoformat()},
            token=token,
        )
    except Exception as e:
        record_suppressed_error("api_oncopanel", "active_tab_set", e)
        return _cors_json({"error": "failed to persist"}, status_code=503, request=request)
    return _cors_json({"tab": tab, "status": "saved"}, request=request)
