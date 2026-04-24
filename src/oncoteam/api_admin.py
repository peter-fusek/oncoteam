"""Admin API handlers — extracted from dashboard_api.py."""

from __future__ import annotations

import asyncio
import json
import logging
import time

from starlette.requests import Request
from starlette.responses import JSONResponse

from . import oncofiles_client
from .activity_logger import record_suppressed_error
from .api_whatsapp import (
    _approved_phones,
    _persist_approved_phones,
    _persist_patient_token,
    _phone_patient_map,
    is_phone_approved,
)
from .request_context import get_token_for_patient as _get_token_for_patient

_logger = logging.getLogger("oncoteam.api_admin")

# ---------------------------------------------------------------------------
# Lazy imports from dashboard_api to avoid circular dependency
# ---------------------------------------------------------------------------


def _cors_json(data: dict, status_code: int = 200, request: Request | None = None) -> JSONResponse:
    from .dashboard_api import _cors_json as _cj

    return _cj(data, status_code=status_code, request=request)


def _get_patient_id(request: Request) -> str:
    from .dashboard_api import _get_patient_id as _gpi

    return _gpi(request)


# ---------------------------------------------------------------------------
# Access rights cache (module-level state)
# ---------------------------------------------------------------------------

_access_rights_cache: dict[str, object] = {}
_access_rights_ts: float = 0.0
_ACCESS_RIGHTS_TTL = 60.0


async def _load_access_rights() -> dict[str, object]:
    """Load access rights from oncofiles agent_state, with 60s cache."""
    global _access_rights_cache, _access_rights_ts
    now = time.monotonic()
    if _access_rights_cache and (now - _access_rights_ts) < _ACCESS_RIGHTS_TTL:
        return _access_rights_cache
    try:
        raw = await oncofiles_client.get_agent_state(key="role_map", agent_id="access_rights")
        if isinstance(raw, dict):
            data = raw.get("value") or raw.get("state") or raw
            if isinstance(data, str):
                data = json.loads(data)
            if isinstance(data, dict):
                role_map = data.get("role_map", data)
                _access_rights_cache = role_map
                _access_rights_ts = now
                return role_map
    except Exception as exc:
        record_suppressed_error("_load_access_rights", "get_agent_state", exc)
        _logger.warning("Failed to load access rights: %s", exc)
    return _access_rights_cache


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


async def api_patients(request: Request) -> JSONResponse:
    """GET /api/patients — list all active patients with doc counts."""
    token = _get_token_for_patient(_get_patient_id(request))
    try:
        result = await oncofiles_client.list_patients(token=token)
        patients = result if isinstance(result, list) else result.get("patients", [])
        return _cors_json({"patients": patients}, request=request)
    except Exception as exc:
        record_suppressed_error("api_patients", "list_patients", exc)
        # Fallback to local registry
        from .patient_context import get_patient, list_patient_ids

        patients = []
        for pid in list_patient_ids():
            try:
                p = get_patient(pid)
                patients.append(
                    {
                        "slug": pid,
                        "name": p.name,
                        "patient_type": (
                            "general" if p.diagnosis_code.startswith("Z") else "oncology"
                        ),
                    }
                )
            except Exception:
                continue
        return _cors_json({"patients": patients, "source": "local"}, request=request)


async def api_onboarding_queue(request: Request) -> JSONResponse:
    """GET /api/internal/onboarding-queue — Gate-1-only patients awaiting manual onboarding.

    Source of truth is the `patient_registry:last_snapshot` agent_state key
    written by the `patient_registry_sync` agent (#422). We read it directly
    instead of re-calling `list_patients` + diffing — that keeps this
    endpoint cheap and consistent with the banner count.

    Falls back to an empty queue + `stale=true` if the snapshot is missing
    (e.g. fresh deploy, agent hasn't fired yet). UI can show "snapshot
    pending" instead of an empty "you're caught up" state that would be
    misleading.
    """
    try:
        raw = await oncofiles_client.get_agent_state(
            key="patient_registry:last_snapshot", agent_id="oncoteam"
        )
    except Exception as exc:
        record_suppressed_error("api_onboarding_queue", "get_snapshot", exc)
        return _cors_json(
            {"queue": [], "count": 0, "stale": True, "error": "snapshot unavailable"},
            request=request,
        )

    snapshot: dict = {}
    value = raw.get("value") if isinstance(raw, dict) else raw
    if isinstance(value, str):
        try:
            snapshot = json.loads(value)
        except (json.JSONDecodeError, TypeError):
            snapshot = {}
    elif isinstance(value, dict):
        snapshot = value

    if not snapshot or not snapshot.get("timestamp"):
        return _cors_json(
            {"queue": [], "count": 0, "stale": True, "snapshot_timestamp": None},
            request=request,
        )

    patients = snapshot.get("patients") or []
    queue = [
        {
            "slug": p.get("slug", ""),
            "name": p.get("name", ""),
            "patient_type": p.get("patient_type", ""),
            "documents": p.get("documents", 0),
            "first_seen_in_oncofiles": p.get("first_seen_in_oncofiles", ""),
            "flagged_at": p.get("flagged_at", ""),
        }
        for p in patients
        if isinstance(p, dict) and p.get("classification") == "gate1_only"
    ]
    return _cors_json(
        {
            "queue": queue,
            "count": len(queue),
            "stale": False,
            "snapshot_timestamp": snapshot.get("timestamp"),
        },
        request=request,
    )


async def api_onboard_patient(request: Request) -> JSONResponse:
    """POST /api/internal/onboard-patient — create a new patient in oncofiles and register locally.

    Expects JSON body: {patient_id, display_name, diagnosis_summary?, preferred_lang?, phone?}
    Returns: {patient_id, bearer_token, status: "created"} or {status: "exists"} on 409.
    """
    import httpx as _httpx

    from .models import PatientProfile
    from .patient_context import register_patient

    try:
        body = await request.json()
    except Exception:
        return _cors_json({"error": "Invalid JSON body"}, status_code=400, request=request)

    patient_id = (body.get("patient_id") or "").strip()
    # Accept both field name variants (frontend sends patient_name)
    display_name = (body.get("display_name") or body.get("patient_name") or "").strip()
    if not patient_id or not display_name:
        return _cors_json(
            {"error": "patient_id and display_name are required"},
            status_code=400,
            request=request,
        )

    diagnosis_summary = body.get("diagnosis_summary", body.get("diagnosis", ""))
    preferred_lang = body.get("preferred_lang", body.get("lang", "sk"))

    try:
        result = await oncofiles_client.create_patient_via_api(
            patient_id=patient_id,
            display_name=display_name,
            diagnosis_summary=diagnosis_summary,
            preferred_lang=preferred_lang,
            caregiver_email="",
        )
    except _httpx.HTTPStatusError as exc:
        if exc.response.status_code == 409:
            _logger.info("Patient %s already exists in oncofiles", patient_id)
            return _cors_json(
                {"patient_id": patient_id, "status": "exists"},
                request=request,
            )
        record_suppressed_error("api_onboard_patient", "create_patient", exc)
        return _cors_json(
            {"error": f"Oncofiles error: {exc.response.status_code}"},
            status_code=502,
            request=request,
        )
    except Exception as exc:
        record_suppressed_error("api_onboard_patient", "create_patient", exc)
        return _cors_json(
            {"error": f"Failed to create patient: {exc}"},
            status_code=502,
            request=request,
        )

    # Register in oncoteam's in-memory patient registry
    bearer_token = result.get("bearer_token", "")
    profile = PatientProfile(
        patient_id=patient_id,
        name=display_name,
        diagnosis_code="",
        diagnosis_description=diagnosis_summary,
        tumor_site="",
        treatment_regimen="",
    )
    try:
        register_patient(patient_id=patient_id, token=bearer_token, profile=profile)
    except Exception as exc:
        record_suppressed_error("api_onboard_patient", "register_patient", exc)
        # Non-fatal — patient was created in oncofiles, just not registered locally

    # Persist token for reload after restart (#265)
    if bearer_token:
        asyncio.ensure_future(_persist_patient_token(patient_id, bearer_token))

    _logger.info("Onboarded patient %s", patient_id)

    return _cors_json(
        {
            "patient_id": patient_id,
            "bearer_token": bearer_token,
            "status": "created",
        },
        request=request,
    )


async def api_onboarding_status(request: Request) -> JSONResponse:
    """POST /api/internal/onboarding-status — check onboarding state for a phone number.

    Expects JSON body: {phone}
    Returns: {status: "unknown"} — placeholder for #137 state machine.
    """
    try:
        body = await request.json()
    except Exception:
        return _cors_json({"error": "Invalid JSON body"}, status_code=400, request=request)

    phone = (body.get("phone") or "").strip()
    if not phone:
        return _cors_json({"error": "phone is required"}, status_code=400, request=request)

    # Check if the phone is in the approved set (includes oncofiles-persisted phones)
    approved = is_phone_approved(phone)
    return _cors_json(
        {
            "phone": phone,
            "status": "approved" if approved else "unknown",
            "approved": approved,
            "patient_id": _phone_patient_map.get(phone, ""),
        },
        request=request,
    )


async def api_approve_user(request: Request) -> JSONResponse:
    """POST /api/internal/approve-user — admin approves a new WhatsApp user.

    Expects JSON body: {phone}
    Stores phone in the in-memory approved set and persists to oncofiles.
    Returns: {status: "approved", phone: str}
    """
    try:
        body = await request.json()
    except Exception:
        return _cors_json({"error": "Invalid JSON body"}, status_code=400, request=request)

    phone = (body.get("phone") or "").strip()
    if not phone:
        return _cors_json({"error": "phone is required"}, status_code=400, request=request)

    _approved_phones.add(phone)

    # Optionally link phone to a patient_id (#265)
    patient_id_for_phone = (body.get("patient_id") or "").strip()
    if patient_id_for_phone:
        _phone_patient_map[phone] = patient_id_for_phone

    _logger.info("Admin approved WhatsApp user: %s", phone)

    # Persist to oncofiles (fire-and-forget, don't block response)
    asyncio.ensure_future(_persist_approved_phones())

    return _cors_json({"status": "approved", "phone": phone}, request=request)


async def api_access_rights_get(request: Request) -> JSONResponse:
    """GET /api/internal/access-rights — read the role map from database."""
    role_map = await _load_access_rights()
    return _cors_json({"role_map": role_map}, request=request)


async def api_access_rights_set(request: Request) -> JSONResponse:
    """POST /api/internal/access-rights — update the role map in database.

    Expects JSON body: {role_map: {...}}
    """
    global _access_rights_cache, _access_rights_ts
    try:
        body = await request.json()
    except Exception:
        return _cors_json({"error": "Invalid JSON body"}, status_code=400, request=request)

    role_map = body.get("role_map")
    if not isinstance(role_map, dict):
        return _cors_json(
            {"error": "role_map must be a JSON object"}, status_code=400, request=request
        )

    from datetime import UTC
    from datetime import datetime as _dt

    try:
        await oncofiles_client.set_agent_state(
            key="role_map",
            value={
                "role_map": role_map,
                "updated_at": _dt.now(UTC).isoformat(),
            },
            agent_id="access_rights",
        )
        _access_rights_cache = role_map
        _access_rights_ts = time.monotonic()
        _logger.info("Access rights updated: %d entries", len(role_map))
        return _cors_json({"status": "updated", "entries": len(role_map)}, request=request)
    except Exception as exc:
        record_suppressed_error("api_access_rights_set", "set_agent_state", exc)
        return _cors_json({"error": f"Failed to persist: {exc}"}, status_code=500, request=request)
