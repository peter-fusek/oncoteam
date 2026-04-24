"""Append-only audit log for the clinical funnel two-lane architecture (#395).

Persistence model:
- Events are stored in oncofiles as agent_state under keys:
    funnel_audit:{patient_id}:{card_id} -> list[dict] of serialized FunnelAuditEvent
    funnel_cards:{patient_id}            -> dict[card_id, dict] of FunnelCard
- Events are APPENDED, never removed. Corrections append a new event with
  event_type="correction" carrying `supersedes: <event_id>` in metadata.
- Re-surfacing: before an agent creates a new proposal, it queries
  `find_existing_card_for_nct()` so a dismissed/archived NCT never re-enters
  the clinical lane without a "⚠️ Previously seen" warning.

This module is the ONLY writer of funnel_audit state. API endpoints call in
here; agents go through the API. No other code path is allowed to mutate the
audit log.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import UTC, datetime, timedelta

from . import oncofiles_client
from .activity_logger import record_suppressed_error
from .models import (
    CLINICAL_STAGES,
    PROPOSAL_STAGES,
    FunnelActorType,
    FunnelAuditEvent,
    FunnelCard,
    FunnelEventType,
    FunnelLane,
)

logger = logging.getLogger("oncoteam.funnel_audit")

# Default TTL for untouched agent proposals. After expiry, the drain job
# appends an `archived` audit event with rationale="TTL expired" — still
# visible in history, just not surfaced in the active proposal view.
DEFAULT_PROPOSAL_TTL_DAYS = 30


def _audit_key(patient_id: str, card_id: str) -> str:
    # #435 Item 5 — build via helper so the patient-scope contract is
    # enforced at call time (raises if patient_id is empty).
    from .request_context import build_agent_state_key

    return build_agent_state_key("funnel_audit", patient_id=patient_id, extra=(card_id,))


def _cards_key(patient_id: str) -> str:
    from .request_context import build_agent_state_key

    return build_agent_state_key("funnel_cards", patient_id=patient_id)


def _new_event_id() -> str:
    return str(uuid.uuid4())


def make_card_id(patient_id: str, nct_id: str, lane: FunnelLane) -> str:
    """Canonical card_id format. Callers outside this module must use this
    helper so promote→clinical transitions resolve the same ID deterministically.
    """
    suffix = "_proposal" if lane == FunnelLane.PROPOSAL else ""
    return f"{patient_id}_{nct_id}{suffix}"


def _unwrap_state(result: dict | None) -> dict | list | None:
    """oncofiles returns agent_state wrapped as {result|value: ...}. Peel it."""
    if not isinstance(result, dict):
        return None
    value = result.get("result", result.get("value"))
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return None
    return value


async def _load_events(patient_id: str, card_id: str, *, token: str | None = None) -> list[dict]:
    try:
        raw = await oncofiles_client.get_agent_state(_audit_key(patient_id, card_id), token=token)
    except Exception as e:
        record_suppressed_error("funnel_audit", f"load_events:{card_id}", e)
        return []
    value = _unwrap_state(raw)
    if isinstance(value, list):
        return value
    if isinstance(value, dict) and isinstance(value.get("events"), list):
        return value["events"]
    return []


async def _save_events(
    patient_id: str, card_id: str, events: list[dict], *, token: str | None = None
) -> None:
    try:
        await oncofiles_client.set_agent_state(
            _audit_key(patient_id, card_id), {"events": events}, token=token
        )
    except Exception as e:
        record_suppressed_error("funnel_audit", f"save_events:{card_id}", e)
        raise


async def _load_cards(patient_id: str, *, token: str | None = None) -> dict[str, dict]:
    try:
        raw = await oncofiles_client.get_agent_state(_cards_key(patient_id), token=token)
    except Exception as e:
        record_suppressed_error("funnel_audit", "load_cards", e)
        return {}
    value = _unwrap_state(raw)
    if isinstance(value, dict):
        # The top-level value is either {card_id: card_dict, ...} directly
        # or {"cards": {card_id: card_dict, ...}} depending on writer.
        inner = value.get("cards")
        if isinstance(inner, dict):
            return inner
        return value
    return {}


async def _save_cards(patient_id: str, cards: dict[str, dict], *, token: str | None = None) -> None:
    try:
        await oncofiles_client.set_agent_state(
            _cards_key(patient_id), {"cards": cards}, token=token
        )
    except Exception as e:
        record_suppressed_error("funnel_audit", "save_cards", e)
        raise


async def record_event(
    *,
    card_id: str,
    patient_id: str,
    nct_id: str,
    actor_type: FunnelActorType,
    actor_id: str,
    actor_display_name: str,
    event_type: FunnelEventType,
    from_stage: str | None = None,
    to_stage: str | None = None,
    rationale: str = "",
    metadata: dict | None = None,
    session_id: str = "",
    token: str | None = None,
) -> FunnelAuditEvent:
    """Append an immutable audit event. Invariants are enforced by the model.

    Raises ValueError from FunnelAuditEvent if a state-changing event is
    missing rationale OR if an agent tries to produce a non-allowlisted event.
    """
    event = FunnelAuditEvent(
        event_id=_new_event_id(),
        card_id=card_id,
        patient_id=patient_id,
        nct_id=nct_id,
        actor_type=actor_type,
        actor_id=actor_id,
        actor_display_name=actor_display_name,
        event_type=event_type,
        from_stage=from_stage,
        to_stage=to_stage,
        rationale=rationale,
        metadata=metadata or {},
        timestamp=datetime.now(UTC),
        session_id=session_id,
    )
    events = await _load_events(patient_id, card_id, token=token)
    events.append(event.model_dump(mode="json"))
    await _save_events(patient_id, card_id, events, token=token)
    return event


async def list_events_for_card(
    patient_id: str, card_id: str, *, token: str | None = None
) -> list[dict]:
    """Return all events for a card in insertion order (oldest first)."""
    return await _load_events(patient_id, card_id, token=token)


async def list_events_for_patient(
    patient_id: str,
    *,
    actor_type: FunnelActorType | None = None,
    event_type: FunnelEventType | None = None,
    limit: int | None = None,
    token: str | None = None,
) -> list[dict]:
    """Return events across all cards for a patient, newest first.

    Filters are applied in-memory; volumes stay small enough (hundreds of
    events per patient lifetime) that a server-side query isn't worth it.
    """
    cards = await _load_cards(patient_id, token=token)
    # Parallel fan-out bounded by the oncofiles 3-slot semaphore. Serial
    # awaits here were the hottest path for the /audit/patient endpoint.
    card_event_lists = await asyncio.gather(
        *(_load_events(patient_id, card_id, token=token) for card_id in cards)
    )
    all_events: list[dict] = [e for lst in card_event_lists for e in lst]
    if actor_type is not None:
        all_events = [e for e in all_events if e.get("actor_type") == actor_type.value]
    if event_type is not None:
        all_events = [e for e in all_events if e.get("event_type") == event_type.value]
    all_events.sort(key=lambda e: e.get("timestamp", ""), reverse=True)
    if limit is not None:
        all_events = all_events[:limit]
    return all_events


async def find_existing_card_for_nct(
    patient_id: str, nct_id: str, *, token: str | None = None
) -> FunnelCard | None:
    """Re-surfacing check — returns the active card for an NCT if one exists.

    Searches both lanes. Used by agents before posting a proposal: if the NCT
    already exists, they must flag `duplicate_of_card_id` + `event_type=RE_SURFACED`
    instead of silently creating a second card.
    """
    cards = await _load_cards(patient_id, token=token)
    for card_id, card_dict in cards.items():
        if card_dict.get("nct_id") == nct_id:
            try:
                return FunnelCard.model_validate(card_dict)
            except Exception as e:
                record_suppressed_error("funnel_audit", f"validate_card:{card_id}", e)
                continue
    return None


async def upsert_card(card: FunnelCard, *, token: str | None = None) -> FunnelCard:
    """Store a card. Callers must record the matching audit event separately."""
    cards = await _load_cards(card.patient_id, token=token)
    card.updated_at = datetime.now(UTC)
    cards[card.card_id] = card.model_dump(mode="json")
    await _save_cards(card.patient_id, cards, token=token)
    return card


async def upsert_cards(
    patient_id: str, cards_to_save: list[FunnelCard], *, token: str | None = None
) -> list[FunnelCard]:
    """Batch variant of upsert_card — one load/save roundtrip for N cards.

    Used by promote (create clinical + archive proposal in one write) so we
    don't pay two oncofiles roundtrips for what's a single logical transition.
    Every input card must share the patient_id argument.
    """
    if not cards_to_save:
        return []
    cards = await _load_cards(patient_id, token=token)
    now = datetime.now(UTC)
    for c in cards_to_save:
        c.updated_at = now
        cards[c.card_id] = c.model_dump(mode="json")
    await _save_cards(patient_id, cards, token=token)
    return cards_to_save


async def get_card(patient_id: str, card_id: str, *, token: str | None = None) -> FunnelCard | None:
    cards = await _load_cards(patient_id, token=token)
    d = cards.get(card_id)
    if d is None:
        return None
    try:
        return FunnelCard.model_validate(d)
    except Exception as e:
        record_suppressed_error("funnel_audit", f"validate_card:{card_id}", e)
        return None


async def list_cards(
    patient_id: str, *, lane: FunnelLane | None = None, token: str | None = None
) -> list[FunnelCard]:
    cards = await _load_cards(patient_id, token=token)
    out: list[FunnelCard] = []
    for card_dict in cards.values():
        try:
            c = FunnelCard.model_validate(card_dict)
        except Exception as e:
            record_suppressed_error("funnel_audit", "validate_card_in_list", e)
            continue
        if lane is None or c.lane == lane:
            out.append(c)
    out.sort(key=lambda c: c.updated_at, reverse=True)
    return out


def validate_stage(lane: FunnelLane, stage: str) -> None:
    """Raise ValueError if `stage` isn't in the vocabulary for `lane`."""
    vocab = PROPOSAL_STAGES if lane == FunnelLane.PROPOSAL else CLINICAL_STAGES
    if stage not in vocab:
        raise ValueError(
            f"stage={stage!r} not allowed in lane={lane.value}; expected one of {list(vocab)}"
        )


def proposal_ttl_expiry(days: int = DEFAULT_PROPOSAL_TTL_DAYS) -> datetime:
    """Return a timezone-aware expiry timestamp N days from now."""
    return datetime.now(UTC) + timedelta(days=days)


async def create_agent_proposal(
    *,
    patient_id: str,
    nct_id: str,
    title: str = "",
    source_agent: str = "",
    source_run_id: str = "",
    biomarker_match: dict | None = None,
    geographic_score: float | None = None,
    sites_in_scope: list[dict] | None = None,
    ai_suggestions: list[dict] | None = None,
    actor_id: str = "agent",
    actor_display_name: str = "",
    rationale: str = "",
    token: str | None = None,
) -> dict:
    """Process-internal helper mirroring POST /api/funnel/proposals.

    Safe for MCP tools and in-process autonomous tasks to call directly —
    enforces the same re-surfacing rule as the HTTP path. Returns a small
    status dict: {"status": "created" | "re_surfaced", "card_id": ..., "nct_id": ...}.
    """
    existing = await find_existing_card_for_nct(patient_id, nct_id, token=token)
    if existing is not None:
        try:
            await record_event(
                card_id=existing.card_id,
                patient_id=patient_id,
                nct_id=nct_id,
                actor_type=FunnelActorType.AGENT,
                actor_id=actor_id,
                actor_display_name=actor_display_name or source_agent or actor_id,
                event_type=FunnelEventType.RE_SURFACED,
                rationale=rationale or "agent re-surfaced previously seen NCT",
                metadata={
                    "existing_lane": existing.lane.value,
                    "existing_stage": existing.current_stage,
                    "source_agent": source_agent,
                    "source_run_id": source_run_id,
                },
                token=token,
            )
        except Exception as e:
            record_suppressed_error("funnel_audit", "re_surface_audit", e)
        return {
            "status": "re_surfaced",
            "card_id": existing.card_id,
            "nct_id": nct_id,
            "lane": existing.lane.value,
            "stage": existing.current_stage,
        }

    card = FunnelCard(
        card_id=make_card_id(patient_id, nct_id, FunnelLane.PROPOSAL),
        patient_id=patient_id,
        nct_id=nct_id,
        lane=FunnelLane.PROPOSAL,
        current_stage="new",
        title=title,
        biomarker_match=biomarker_match or {},
        geographic_score=geographic_score,
        sites_in_scope=sites_in_scope or [],
        ai_suggestions=ai_suggestions or [],
        source_agent=source_agent,
        source_run_id=source_run_id,
        proposal_ttl_expires_at=proposal_ttl_expiry(DEFAULT_PROPOSAL_TTL_DAYS),
    )
    await upsert_card(card, token=token)
    await record_event(
        card_id=card.card_id,
        patient_id=patient_id,
        nct_id=nct_id,
        actor_type=FunnelActorType.AGENT,
        actor_id=actor_id,
        actor_display_name=actor_display_name or source_agent or actor_id,
        event_type=FunnelEventType.CREATED,
        rationale=rationale,
        metadata={
            "lane": FunnelLane.PROPOSAL.value,
            "source_agent": source_agent,
            "source_run_id": source_run_id,
            "biomarker_match": card.biomarker_match,
            "geographic_score": card.geographic_score,
        },
        token=token,
    )
    return {
        "status": "created",
        "card_id": card.card_id,
        "nct_id": nct_id,
        "lane": FunnelLane.PROPOSAL.value,
        "stage": card.current_stage,
    }
