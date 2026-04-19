"""Webhook & internal trigger API handlers — extracted from dashboard_api.py."""

from __future__ import annotations

import asyncio
import json
import logging

from starlette.requests import Request
from starlette.responses import JSONResponse

from . import oncofiles_client
from .activity_logger import record_suppressed_error
from .config import DOC_WEBHOOK_CEE_NIGHT_HOURS, FUP_AGENT_RUNS_PER_MONTH
from .patient_context import DEFAULT_PATIENT_ID, get_patient
from .request_context import get_token_for_patient as _get_token_for_patient

_logger = logging.getLogger("oncoteam.api_webhooks")

# ---------------------------------------------------------------------------
# Lazy imports from dashboard_api to avoid circular dependency
# ---------------------------------------------------------------------------


def _cors_json(data: dict, status_code: int = 200, request: Request | None = None) -> JSONResponse:
    from .dashboard_api import _cors_json as _cj

    return _cj(data, status_code=status_code, request=request)


def _check_expensive_rate_limit() -> bool:
    from .dashboard_api import _check_expensive_rate_limit as _cerl

    return _cerl()


def _check_fup_agent_run(patient_id: str = "") -> bool:
    from .dashboard_api import _check_fup_agent_run as _cfar

    return _cfar(patient_id)


# ---------------------------------------------------------------------------
# API Handlers
# ---------------------------------------------------------------------------


async def api_bug_report(request: Request) -> JSONResponse:
    """POST /api/bug-report — create a GitHub issue from dashboard bug reporter.

    Expects JSON: {description: str, url: str, route: str, viewport: str,
                    role: str, locale: str}
    """
    try:
        body = json.loads(await request.body())
    except (json.JSONDecodeError, Exception):
        return _cors_json({"error": "Invalid JSON"}, status_code=400)

    description = body.get("description", "").strip()
    if not description:
        return _cors_json({"error": "description is required"}, status_code=400)

    url = body.get("url", "")
    route = body.get("route", "")
    viewport = body.get("viewport", "")
    role = body.get("role", "")
    locale = body.get("locale", "")
    # page_text removed — auto-capture of DOM content is an injection risk.
    user_agent = request.headers.get("user-agent", "")[:200]

    from datetime import UTC, datetime

    now_str = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    page_file = route.strip("/") or "index"

    issue_body = (
        f"## Bug Report\n\n"
        f"**{description}**\n\n"
        f"### Context\n"
        f"| Field | Value |\n|-------|-------|\n"
        f"| Page | `{route}` |\n"
        f"| URL | {url} |\n"
        f"| Viewport | {viewport} |\n"
        f"| Role | {role} |\n"
        f"| Locale | {locale} |\n"
        f"| User Agent | {user_agent[:100]} |\n"
        f"| Reported | {now_str} |\n\n"
        f"### For Claude Code\n"
        f"- **File**: `dashboard/app/pages/{page_file}.vue`\n"
        f"- **Repro**: `{url}` as `{role}` / `{locale}`\n"
        f"- **Checklist**: [ ] Root cause [ ] Fix [ ] Test\n\n"
        f"---\n*Reported via dashboard bug reporter*\n"
    )

    try:
        from .github_client import create_issue

        result = await create_issue(
            repo="peter-fusek/oncoteam",
            title=f"Bug: {description[:80]}",
            body=issue_body,
            labels=["bug"],
        )
        return _cors_json({"created": True, **result})
    except Exception as e:
        record_suppressed_error("api_bug_report", "create_issue", e)
        return _cors_json({"error": str(e)}, status_code=502)


async def api_document_webhook(request: Request) -> JSONResponse:
    """POST /api/internal/document-webhook — triggered by oncofiles on new upload.

    Expects JSON body: {document_id: int, patient_id?: str, filename?: str,
    category?: str, uploaded_at?: str}
    Launches the document pipeline as a background task.
    """

    from .autonomous_tasks import (
        _extract_timestamp,
        _get_state,
        _set_state,
        run_document_pipeline,
    )

    if not _check_expensive_rate_limit():
        return _cors_json(
            {"error": "Too many pipeline triggers. Try again later."},
            status_code=429,
            request=request,
        )

    try:
        body = await request.json()
    except Exception:
        return _cors_json({"error": "Invalid JSON body"}, status_code=400, request=request)

    document_id = body.get("document_id")
    if not isinstance(document_id, int) or document_id <= 0:
        return _cors_json(
            {"error": "document_id must be a positive integer"}, status_code=400, request=request
        )

    patient_id = body.get("patient_id", DEFAULT_PATIENT_ID)

    # Non-destructive pause gate: data stays in oncofiles, no Claude spend.
    try:
        patient = get_patient(patient_id)
    except KeyError:
        return _cors_json(
            {"error": f"Unknown patient: {patient_id}"}, status_code=400, request=request
        )
    if patient.paused:
        _logger.info(
            "Document webhook skipped for paused patient %s (doc %d)", patient_id, document_id
        )
        return _cors_json(
            {
                "status": "skipped_patient_paused",
                "document_id": document_id,
                "patient_id": patient_id,
            },
            status_code=202,
            request=request,
        )

    token = _get_token_for_patient(patient_id)

    # Quick dedup check before launching background task
    existing = await _get_state(f"pipeline:{document_id}", token=token)
    if _extract_timestamp(existing):
        return _cors_json(
            {"status": "already_processed", "document_id": document_id}, request=request
        )

    metadata = {
        "filename": body.get("filename", ""),
        "category": body.get("category", ""),
        "uploaded_at": body.get("uploaded_at", ""),
    }

    # Auto-fill metadata from oncofiles when webhook doesn't provide it
    if not metadata["category"]:
        try:
            doc = await asyncio.wait_for(
                oncofiles_client.get_document_by_id(document_id),
                timeout=5,
            )
            if isinstance(doc, dict):
                metadata["category"] = doc.get("category", "")
                metadata["filename"] = metadata["filename"] or doc.get("filename", "")
        except Exception as exc:
            record_suppressed_error("api_document_webhook", "get_document_by_id", exc)

    # CEE-night window gate: inside window → immediate dispatch; outside →
    # enqueue for the nightly drain agent. Keeps Claude spend concentrated in
    # the cheap off-peak window.
    from datetime import UTC
    from datetime import datetime as _dt

    hour_utc = _dt.now(UTC).hour
    night_lo, night_hi = DOC_WEBHOOK_CEE_NIGHT_HOURS
    in_cee_night = night_lo <= hour_utc < night_hi

    if in_cee_night:
        asyncio.create_task(run_document_pipeline(document_id, metadata, patient_id=patient_id))
        _logger.info(
            "Document pipeline dispatched immediately (CEE night) doc=%d patient=%s hour=%d",
            document_id,
            patient_id,
            hour_utc,
        )
        return _cors_json(
            {
                "status": "pipeline_started",
                "document_id": document_id,
                "patient_id": patient_id,
                "dispatch": "immediate",
            },
            request=request,
        )

    # Outside CEE night: enqueue for document_pipeline_drain (runs 02:00 UTC).
    queue_state = await _get_state("pending_docs_queue", token=token)
    docs_list: list[dict] = []
    if isinstance(queue_state, dict):
        if isinstance(queue_state.get("docs"), list):
            docs_list = list(queue_state["docs"])
        else:
            raw = queue_state.get("value")
            if isinstance(raw, str):
                try:
                    raw = json.loads(raw)
                except (json.JSONDecodeError, TypeError):
                    raw = None
            if isinstance(raw, dict) and isinstance(raw.get("docs"), list):
                docs_list = list(raw["docs"])

    if not any(d.get("doc_id") == document_id for d in docs_list if isinstance(d, dict)):
        docs_list.append(
            {
                "doc_id": document_id,
                "metadata": metadata,
                "enqueued_at": _dt.now(UTC).isoformat(),
            }
        )
        await _set_state("pending_docs_queue", {"docs": docs_list}, token=token)

    _logger.info(
        "Document queued for CEE-night drain doc=%d patient=%s hour=%d queue_len=%d",
        document_id,
        patient_id,
        hour_utc,
        len(docs_list),
    )
    return _cors_json(
        {
            "status": "queued_for_cee_night",
            "document_id": document_id,
            "patient_id": patient_id,
            "dispatch": "queued",
            "queue_len": len(docs_list),
        },
        status_code=202,
        request=request,
    )


async def api_trigger_agent(request: Request) -> JSONResponse:
    """POST /api/internal/trigger-agent — manually trigger a full agent run.

    Expects JSON body: {agent_id: str}
    Launches the agent as a background task with full resources (no cooldown skip).
    """

    from .agent_registry import AGENT_REGISTRY

    if not _check_expensive_rate_limit():
        return _cors_json(
            {"error": "Too many agent triggers. Try again later."},
            status_code=429,
            request=request,
        )

    try:
        body = await request.json()
    except Exception:
        return _cors_json({"error": "Invalid JSON body"}, status_code=400, request=request)

    agent_id = body.get("agent_id", "")
    trigger_patient_id = body.get("patient_id", "")

    if not _check_fup_agent_run(trigger_patient_id or "global"):
        return _cors_json(
            {"error": f"Monthly agent run limit reached ({FUP_AGENT_RUNS_PER_MONTH})."},
            status_code=429,
            request=request,
        )
    if agent_id not in AGENT_REGISTRY:
        return _cors_json(
            {"error": f"Unknown agent: {agent_id}", "available": list(AGENT_REGISTRY.keys())},
            status_code=400,
            request=request,
        )

    # Import task functions dynamically (same map as scheduler.py)
    from .scheduler import _get_task_functions

    task_functions = _get_task_functions()
    func = task_functions.get(agent_id)
    if func is None:
        return _cors_json(
            {"error": f"No runnable function for agent: {agent_id}"},
            status_code=400,
            request=request,
        )

    # Clear cooldown state so the agent runs unconditionally
    effective_patient_id = trigger_patient_id or DEFAULT_PATIENT_ID
    token = _get_token_for_patient(effective_patient_id)
    try:
        await oncofiles_client.set_agent_state(
            f"last_{agent_id}:{effective_patient_id}", {}, token=token
        )
        _logger.info("Cleared cooldown for %s:%s", agent_id, effective_patient_id)
    except Exception as e:
        _logger.warning("Could not clear cooldown for %s: %s", agent_id, e)

    asyncio.create_task(func(patient_id=effective_patient_id))
    _logger.info("Manually triggered agent: %s (patient=%s)", agent_id, effective_patient_id)

    return _cors_json({"status": "triggered", "agent_id": agent_id}, request=request)
