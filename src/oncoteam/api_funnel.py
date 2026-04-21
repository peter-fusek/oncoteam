"""Clinical funnel two-lane API handlers (#395).

Endpoints:
    POST   /api/funnel/proposals                 — agent-writable (creates proposal card)
    GET    /api/funnel/proposals                 — list active proposals for patient
    POST   /api/funnel/cards                     — physician-writable (promote / move / archive)
    GET    /api/funnel/cards                     — list clinical-lane cards
    GET    /api/funnel/audit/{card_id}           — per-card audit timeline
    GET    /api/funnel/audit/patient/{patient_id} — patient-wide audit timeline

Actor / lane enforcement:
    - Any POST to /api/funnel/cards is a "human-disposes" action and must
      originate from a physician or advocate role. Agents are rejected.
    - POST /api/funnel/proposals is the only agent-writable mutation. Every
      proposal is tagged with actor_type=agent in the audit event.
    - Role is derived from the request's `X-Actor-Type` header (set by the
      Nuxt proxy from session) OR from the `actor_type` field in the JSON
      body for agent-side calls that carry their own bearer token. The body
      is only trusted for agent-writable endpoints.
"""

from __future__ import annotations

import logging

from starlette.requests import Request
from starlette.responses import JSONResponse

from .activity_logger import record_suppressed_error
from .funnel_audit import (
    DEFAULT_PROPOSAL_TTL_DAYS,
    find_existing_card_for_nct,
    get_card,
    list_cards,
    list_events_for_card,
    list_events_for_patient,
    proposal_ttl_expiry,
    record_event,
    upsert_card,
    validate_stage,
)
from .models import (
    CLINICAL_STAGES,
    PROPOSAL_STAGES,
    FunnelActorType,
    FunnelCard,
    FunnelEventType,
    FunnelLane,
)
from .request_context import get_token_for_patient as _get_token_for_patient

_logger = logging.getLogger("oncoteam.api_funnel")


# ── lazy imports from dashboard_api (avoid circular deps) ───────────────


def _cors_json(data: dict, status_code: int = 200, request: Request | None = None) -> JSONResponse:
    from .dashboard_api import _cors_json as _cj

    return _cj(data, status_code=status_code, request=request)


def _get_patient_id(request: Request) -> str:
    from .dashboard_api import _get_patient_id as _gpi

    return _gpi(request)


async def _parse_json_body(request: Request) -> dict:
    from .dashboard_api import _parse_json_body as _pjb

    return await _pjb(request)


# ── helpers ────────────────────────────────────────────────────────────


def _actor_from_request(
    request: Request, body: dict | None = None
) -> tuple[FunnelActorType, str, str]:
    """Resolve the acting entity for an API call.

    Order of precedence:
      1. `X-Actor-Type` + `X-Actor-Id` + `X-Actor-Display-Name` headers (set
         by the Nuxt session proxy — user-trustworthy).
      2. `actor_type`/`actor_id`/`actor_display_name` in the JSON body.
         Only honored for agent-writable endpoints (caller is responsible
         for gating this).

    Defaults to advocate when nothing is set — safer default than agent
    because clinical endpoints reject agents outright.
    """
    h = request.headers
    actor_type_raw = h.get("X-Actor-Type") or (body or {}).get("actor_type") or "human"
    actor_id = h.get("X-Actor-Id") or (body or {}).get("actor_id", "advocate")
    actor_display = h.get("X-Actor-Display-Name") or (body or {}).get(
        "actor_display_name", actor_id
    )
    try:
        actor_type = FunnelActorType(actor_type_raw)
    except ValueError:
        actor_type = FunnelActorType.HUMAN
    return actor_type, actor_id, actor_display


def _reject_agent(message: str, request: Request | None = None) -> JSONResponse:
    return _cors_json(
        {"error": message, "code": "agent_not_allowed"}, status_code=403, request=request
    )


def _card_to_dict(card: FunnelCard) -> dict:
    return card.model_dump(mode="json")


# ── API handlers ───────────────────────────────────────────────────────


async def api_funnel_proposals_post(request: Request) -> JSONResponse:
    """Agent-writable — create a proposal card (with re-surfacing check).

    Body schema:
        nct_id: str (required)
        title: str
        biomarker_match: dict
        geographic_score: float | null
        sites_in_scope: list[TrialSite-dict]
        ai_suggestions: list[dict]
        source_agent: str
        source_run_id: str
        rationale: str        — stored in metadata; NOT required for 'created'
        actor_type/actor_id/actor_display_name: optional agent identity
    """
    body = await _parse_json_body(request)
    if not isinstance(body, dict):
        return _cors_json({"error": "invalid body"}, status_code=400, request=request)

    nct_id = (body.get("nct_id") or "").strip()
    if not nct_id:
        return _cors_json({"error": "nct_id is required"}, status_code=400, request=request)

    patient_id = _get_patient_id(request)
    token = _get_token_for_patient(patient_id)
    actor_type, actor_id, actor_display = _actor_from_request(request, body)

    # Re-surfacing check: if this NCT is already on the board, we refuse to
    # create a silent duplicate. Instead we append a `re_surfaced` audit
    # event on the existing card and return the existing card so the agent
    # (or UI) can show the "previously seen" warning.
    existing = await find_existing_card_for_nct(patient_id, nct_id, token=token)
    if existing is not None:
        try:
            await record_event(
                card_id=existing.card_id,
                patient_id=patient_id,
                nct_id=nct_id,
                actor_type=actor_type,
                actor_id=actor_id,
                actor_display_name=actor_display,
                event_type=FunnelEventType.RE_SURFACED,
                rationale=body.get("rationale", "agent re-surfaced previously seen NCT"),
                metadata={
                    "existing_lane": existing.lane.value,
                    "existing_stage": existing.current_stage,
                    "source_agent": body.get("source_agent", ""),
                    "source_run_id": body.get("source_run_id", ""),
                },
                token=token,
            )
        except Exception as e:
            record_suppressed_error("api_funnel", "re_surface_audit", e)
        return _cors_json(
            {
                "status": "re_surfaced",
                "card": _card_to_dict(existing),
                "message": (
                    f"NCT {nct_id} already on board in lane={existing.lane.value},"
                    f" stage={existing.current_stage}. Recorded re_surfaced event."
                ),
            },
            status_code=200,
            request=request,
        )

    card = FunnelCard(
        card_id=f"{patient_id}_{nct_id}_proposal",
        patient_id=patient_id,
        nct_id=nct_id,
        lane=FunnelLane.PROPOSAL,
        current_stage="new",
        title=body.get("title", ""),
        biomarker_match=body.get("biomarker_match") or {},
        geographic_score=body.get("geographic_score"),
        sites_in_scope=body.get("sites_in_scope") or [],
        ai_suggestions=body.get("ai_suggestions") or [],
        source_agent=body.get("source_agent", ""),
        source_run_id=body.get("source_run_id", ""),
        proposal_ttl_expires_at=proposal_ttl_expiry(DEFAULT_PROPOSAL_TTL_DAYS),
    )
    await upsert_card(card, token=token)
    try:
        await record_event(
            card_id=card.card_id,
            patient_id=patient_id,
            nct_id=nct_id,
            actor_type=actor_type,
            actor_id=actor_id,
            actor_display_name=actor_display,
            event_type=FunnelEventType.CREATED,
            rationale=body.get("rationale", ""),
            metadata={
                "lane": FunnelLane.PROPOSAL.value,
                "source_agent": card.source_agent,
                "source_run_id": card.source_run_id,
                "biomarker_match": card.biomarker_match,
                "geographic_score": card.geographic_score,
            },
            token=token,
        )
    except ValueError as e:
        return _cors_json(
            {"error": f"audit invariant violated: {e}"},
            status_code=400,
            request=request,
        )
    return _cors_json(
        {"status": "created", "card": _card_to_dict(card)},
        status_code=201,
        request=request,
    )


async def api_funnel_proposals_get(request: Request) -> JSONResponse:
    """List all proposal-lane cards for the current patient."""
    patient_id = _get_patient_id(request)
    token = _get_token_for_patient(patient_id)
    cards = await list_cards(patient_id, lane=FunnelLane.PROPOSAL, token=token)
    return _cors_json(
        {"cards": [_card_to_dict(c) for c in cards], "count": len(cards)},
        request=request,
    )


async def api_funnel_cards_post(request: Request) -> JSONResponse:
    """Physician-writable — move / archive / promote clinical-lane card.

    Body schema:
        action: "promote" | "move" | "archive" | "comment"
        card_id: str (existing card, required)
        to_stage: str (required for promote/move)
        rationale: str (required for promote/move/archive)
        comment: str (required for comment)
    Rejected when actor_type=agent.
    """
    body = await _parse_json_body(request)
    if not isinstance(body, dict):
        return _cors_json({"error": "invalid body"}, status_code=400, request=request)

    actor_type, actor_id, actor_display = _actor_from_request(request, None)
    if actor_type == FunnelActorType.AGENT:
        return _reject_agent(
            "agents cannot mutate clinical-lane cards — use /api/funnel/proposals",
            request=request,
        )

    action = (body.get("action") or "").strip()
    card_id = (body.get("card_id") or "").strip()
    if not action or not card_id:
        return _cors_json(
            {"error": "action and card_id are required"}, status_code=400, request=request
        )

    patient_id = _get_patient_id(request)
    token = _get_token_for_patient(patient_id)
    card = await get_card(patient_id, card_id, token=token)
    if card is None:
        return _cors_json({"error": f"card {card_id} not found"}, status_code=404, request=request)

    if action == "promote":
        if card.lane != FunnelLane.PROPOSAL:
            return _cors_json(
                {"error": "only proposal-lane cards can be promoted"},
                status_code=400,
                request=request,
            )
        to_stage = (body.get("to_stage") or "Watching").strip()
        rationale = (body.get("rationale") or "").strip()
        if not rationale:
            return _cors_json(
                {"error": "rationale is required for promote"},
                status_code=400,
                request=request,
            )
        try:
            validate_stage(FunnelLane.CLINICAL, to_stage)
        except ValueError as e:
            return _cors_json({"error": str(e)}, status_code=400, request=request)

        # Create a NEW clinical-lane card; original proposal is archived so
        # the proposal-lane listing stays clean but the audit trail survives.
        new_card = card.model_copy(
            update={
                "card_id": f"{patient_id}_{card.nct_id}",
                "lane": FunnelLane.CLINICAL,
                "current_stage": to_stage,
                "proposal_ttl_expires_at": None,
            }
        )
        await upsert_card(new_card, token=token)
        await record_event(
            card_id=new_card.card_id,
            patient_id=patient_id,
            nct_id=new_card.nct_id,
            actor_type=actor_type,
            actor_id=actor_id,
            actor_display_name=actor_display,
            event_type=FunnelEventType.PROMOTED_FROM_PROPOSAL,
            from_stage=card.current_stage,
            to_stage=to_stage,
            rationale=rationale,
            metadata={"from_card_id": card.card_id},
            token=token,
        )
        # Archive the original proposal (rationale required — same as move).
        archived = card.model_copy(update={"current_stage": "dismissed"})
        await upsert_card(archived, token=token)
        await record_event(
            card_id=card.card_id,
            patient_id=patient_id,
            nct_id=card.nct_id,
            actor_type=actor_type,
            actor_id=actor_id,
            actor_display_name=actor_display,
            event_type=FunnelEventType.ARCHIVED,
            from_stage=card.current_stage,
            to_stage="dismissed",
            rationale=f"promoted to clinical lane as {new_card.card_id}",
            metadata={"promoted_to_card_id": new_card.card_id},
            token=token,
        )
        return _cors_json(
            {"status": "promoted", "card": _card_to_dict(new_card)},
            status_code=200,
            request=request,
        )

    if action == "move":
        if card.lane != FunnelLane.CLINICAL:
            return _cors_json(
                {"error": "only clinical-lane cards can be moved; promote proposals first"},
                status_code=400,
                request=request,
            )
        to_stage = (body.get("to_stage") or "").strip()
        rationale = (body.get("rationale") or "").strip()
        if not rationale or not to_stage:
            return _cors_json(
                {"error": "to_stage and rationale are required for move"},
                status_code=400,
                request=request,
            )
        try:
            validate_stage(FunnelLane.CLINICAL, to_stage)
        except ValueError as e:
            return _cors_json({"error": str(e)}, status_code=400, request=request)
        from_stage = card.current_stage
        card = card.model_copy(update={"current_stage": to_stage})
        await upsert_card(card, token=token)
        await record_event(
            card_id=card.card_id,
            patient_id=patient_id,
            nct_id=card.nct_id,
            actor_type=actor_type,
            actor_id=actor_id,
            actor_display_name=actor_display,
            event_type=FunnelEventType.MOVED,
            from_stage=from_stage,
            to_stage=to_stage,
            rationale=rationale,
            token=token,
        )
        return _cors_json(
            {"status": "moved", "card": _card_to_dict(card)},
            status_code=200,
            request=request,
        )

    if action == "archive":
        rationale = (body.get("rationale") or "").strip()
        if not rationale:
            return _cors_json(
                {"error": "rationale is required for archive"},
                status_code=400,
                request=request,
            )
        from_stage = card.current_stage
        to_stage = "Archived" if card.lane == FunnelLane.CLINICAL else "dismissed"
        card = card.model_copy(update={"current_stage": to_stage})
        await upsert_card(card, token=token)
        await record_event(
            card_id=card.card_id,
            patient_id=patient_id,
            nct_id=card.nct_id,
            actor_type=actor_type,
            actor_id=actor_id,
            actor_display_name=actor_display,
            event_type=FunnelEventType.ARCHIVED,
            from_stage=from_stage,
            to_stage=to_stage,
            rationale=rationale,
            token=token,
        )
        return _cors_json(
            {"status": "archived", "card": _card_to_dict(card)},
            status_code=200,
            request=request,
        )

    if action == "comment":
        comment = (body.get("comment") or "").strip()
        if not comment:
            return _cors_json({"error": "comment is required"}, status_code=400, request=request)
        await record_event(
            card_id=card.card_id,
            patient_id=patient_id,
            nct_id=card.nct_id,
            actor_type=actor_type,
            actor_id=actor_id,
            actor_display_name=actor_display,
            event_type=FunnelEventType.COMMENTED,
            rationale=comment,
            token=token,
        )
        return _cors_json({"status": "commented"}, status_code=200, request=request)

    return _cors_json({"error": f"unknown action: {action}"}, status_code=400, request=request)


async def api_funnel_cards_get(request: Request) -> JSONResponse:
    """List clinical-lane cards (proposals are on a separate endpoint)."""
    patient_id = _get_patient_id(request)
    token = _get_token_for_patient(patient_id)
    lane_param = request.query_params.get("lane", "clinical")
    try:
        lane = FunnelLane(lane_param)
    except ValueError:
        return _cors_json(
            {"error": f"invalid lane: {lane_param}"}, status_code=400, request=request
        )
    cards = await list_cards(patient_id, lane=lane, token=token)
    return _cors_json(
        {"cards": [_card_to_dict(c) for c in cards], "count": len(cards)},
        request=request,
    )


async def api_funnel_audit_for_card(request: Request) -> JSONResponse:
    """GET /api/funnel/audit/{card_id} — timeline for one card."""
    card_id = request.path_params.get("card_id", "")
    if not card_id:
        return _cors_json({"error": "card_id required"}, status_code=400, request=request)
    patient_id = _get_patient_id(request)
    token = _get_token_for_patient(patient_id)
    events = await list_events_for_card(patient_id, card_id, token=token)
    return _cors_json(
        {"events": events, "count": len(events), "card_id": card_id},
        request=request,
    )


async def api_funnel_audit_for_patient(request: Request) -> JSONResponse:
    """GET /api/funnel/audit/patient — patient-wide timeline, newest first.

    Query params:
        actor_type: "human" | "agent" (optional filter)
        event_type: FunnelEventType value (optional filter)
        limit: int (default 200)
    """
    patient_id = _get_patient_id(request)
    token = _get_token_for_patient(patient_id)
    actor_type = None
    event_type = None
    if v := request.query_params.get("actor_type"):
        try:
            actor_type = FunnelActorType(v)
        except ValueError:
            return _cors_json(
                {"error": f"invalid actor_type: {v}"}, status_code=400, request=request
            )
    if v := request.query_params.get("event_type"):
        try:
            event_type = FunnelEventType(v)
        except ValueError:
            return _cors_json(
                {"error": f"invalid event_type: {v}"}, status_code=400, request=request
            )
    try:
        limit = int(request.query_params.get("limit", "200"))
    except ValueError:
        limit = 200
    events = await list_events_for_patient(
        patient_id,
        actor_type=actor_type,
        event_type=event_type,
        limit=limit,
        token=token,
    )
    return _cors_json(
        {
            "events": events,
            "count": len(events),
            "patient_id": patient_id,
            "vocab": {
                "proposal_stages": list(PROPOSAL_STAGES),
                "clinical_stages": list(CLINICAL_STAGES),
            },
        },
        request=request,
    )
