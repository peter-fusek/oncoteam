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
    return f"funnel_audit:{patient_id}:{card_id}"


def _cards_key(patient_id: str) -> str:
    return f"funnel_cards:{patient_id}"


def _new_event_id() -> str:
    return str(uuid.uuid4())


def _new_card_id(patient_id: str, nct_id: str, lane: FunnelLane) -> str:
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
    all_events: list[dict] = []
    for card_id in cards:
        all_events.extend(await _load_events(patient_id, card_id, token=token))
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
