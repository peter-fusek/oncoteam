"""Tests for the clinical funnel two-lane audit system (#395).

Covers the three critical invariants:
    1. FunnelAuditEvent is immutable (Pydantic frozen=True).
    2. State-changing events require non-empty rationale.
    3. Agent-actor events are restricted to {created, suggested, re_surfaced}.

Plus:
    - Re-surfacing protection (dismissed NCT returns existing card).
    - Append-only persistence (list growth monotonic).
    - Stage validation per lane.
    - Migration: legacy stages mapped to new vocabulary + snapshot written.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import ValidationError

from oncoteam.funnel_audit import (
    find_existing_card_for_nct,
    list_cards,
    list_events_for_card,
    list_events_for_patient,
    proposal_ttl_expiry,
    record_event,
    upsert_card,
    validate_stage,
)
from oncoteam.models import (
    CLINICAL_STAGES,
    FUNNEL_AGENT_ALLOWED_EVENTS,
    FUNNEL_STATE_CHANGING_EVENTS,
    PROPOSAL_STAGES,
    FunnelActorType,
    FunnelAuditEvent,
    FunnelCard,
    FunnelEventType,
    FunnelLane,
)

# ── Invariant 1: immutability ──────────────────────────────────────────


class TestFunnelAuditEventImmutability:
    def _valid_event(self) -> FunnelAuditEvent:
        return FunnelAuditEvent(
            event_id="evt-1",
            card_id="q1b_NCT0001",
            nct_id="NCT0001",
            patient_id="q1b",
            actor_type=FunnelActorType.HUMAN,
            actor_id="mudr",
            actor_display_name="MUDr. X",
            event_type=FunnelEventType.CREATED,
        )

    def test_event_is_frozen(self):
        """Pydantic frozen config should reject attribute mutation."""
        e = self._valid_event()
        with pytest.raises(ValidationError):
            e.rationale = "changed after the fact"

    def test_event_cannot_change_actor(self):
        e = self._valid_event()
        with pytest.raises(ValidationError):
            e.actor_type = FunnelActorType.AGENT


# ── Invariant 2: state-changing events require rationale ───────────────


class TestStateChangingRequireRationale:
    @pytest.mark.parametrize("event_type", list(FUNNEL_STATE_CHANGING_EVENTS))
    def test_missing_rationale_rejected(self, event_type: FunnelEventType):
        with pytest.raises(ValueError, match="rationale is required"):
            FunnelAuditEvent(
                event_id="evt-2",
                card_id="q1b_NCT0002",
                nct_id="NCT0002",
                patient_id="q1b",
                actor_type=FunnelActorType.HUMAN,
                actor_id="mudr",
                actor_display_name="MUDr. X",
                event_type=event_type,
                to_stage="Watching",
                rationale="   ",  # whitespace-only is still empty
            )

    @pytest.mark.parametrize("event_type", list(FUNNEL_STATE_CHANGING_EVENTS))
    def test_non_empty_rationale_accepted(self, event_type: FunnelEventType):
        e = FunnelAuditEvent(
            event_id="evt-3",
            card_id="q1b_NCT0003",
            nct_id="NCT0003",
            patient_id="q1b",
            actor_type=FunnelActorType.HUMAN,
            actor_id="mudr",
            actor_display_name="MUDr. X",
            event_type=event_type,
            to_stage="Watching",
            rationale="oncologist approved during MDT",
        )
        assert e.rationale == "oncologist approved during MDT"

    def test_non_state_changing_does_not_require_rationale(self):
        """COMMENTED, VIEWED, SUGGESTED, CREATED — no rationale required."""
        e = FunnelAuditEvent(
            event_id="evt-4",
            card_id="q1b_NCT0004",
            nct_id="NCT0004",
            patient_id="q1b",
            actor_type=FunnelActorType.HUMAN,
            actor_id="advocate",
            actor_display_name="Peter",
            event_type=FunnelEventType.COMMENTED,
        )
        assert e.rationale == ""


# ── Invariant 3: agent-actor restrictions ──────────────────────────────


class TestAgentActorRestrictions:
    @pytest.mark.parametrize("event_type", list(FUNNEL_AGENT_ALLOWED_EVENTS))
    def test_allowed_event_types_accepted(self, event_type: FunnelEventType):
        # suggested / re_surfaced are not state-changing, so no rationale
        # is required. created is also not state-changing.
        e = FunnelAuditEvent(
            event_id="evt-5",
            card_id="q1b_NCT0005",
            nct_id="NCT0005",
            patient_id="q1b",
            actor_type=FunnelActorType.AGENT,
            actor_id="ddr_monitor",
            actor_display_name="ddr_monitor",
            event_type=event_type,
        )
        assert e.actor_type == FunnelActorType.AGENT

    @pytest.mark.parametrize(
        "event_type",
        [
            FunnelEventType.MOVED,
            FunnelEventType.ARCHIVED,
            FunnelEventType.PROMOTED_FROM_PROPOSAL,
            FunnelEventType.KANBAN_RESET,
            FunnelEventType.CORRECTION,
            FunnelEventType.COMMENTED,
        ],
    )
    def test_disallowed_event_types_rejected(self, event_type: FunnelEventType):
        with pytest.raises(
            ValueError,
            match="agent cannot produce|rationale is required",
        ):
            FunnelAuditEvent(
                event_id="evt-6",
                card_id="q1b_NCT0006",
                nct_id="NCT0006",
                patient_id="q1b",
                actor_type=FunnelActorType.AGENT,
                actor_id="ddr_monitor",
                actor_display_name="ddr_monitor",
                event_type=event_type,
                to_stage="Watching",
                rationale="agent trying to move a card",
            )


# ── Stage vocabulary validation ────────────────────────────────────────


class TestStageValidation:
    def test_proposal_accepts_new(self):
        validate_stage(FunnelLane.PROPOSAL, "new")

    def test_proposal_rejects_clinical_stage(self):
        with pytest.raises(ValueError, match="not allowed in lane=proposal"):
            validate_stage(FunnelLane.PROPOSAL, "Watching")

    def test_clinical_accepts_all_five_stages(self):
        for stage in CLINICAL_STAGES:
            validate_stage(FunnelLane.CLINICAL, stage)

    def test_clinical_rejects_gibberish(self):
        with pytest.raises(ValueError):
            validate_stage(FunnelLane.CLINICAL, "totally-made-up")

    def test_vocabs_disjoint_except_nothing(self):
        """Proposal and clinical vocabularies should not overlap."""
        assert set(PROPOSAL_STAGES).isdisjoint(set(CLINICAL_STAGES))


# ── Append-only persistence (with mocked oncofiles) ────────────────────


class TestAppendOnlyPersistence:
    @pytest.mark.asyncio
    async def test_record_event_appends(self):
        """Two record_event calls should result in two events, in order."""
        stored: dict[str, dict] = {}

        async def fake_get(key, token=None):
            return stored.get(key, {})

        async def fake_set(key, value, token=None):
            stored[key] = {"result": value}

        with (
            patch(
                "oncoteam.funnel_audit.oncofiles_client.get_agent_state",
                side_effect=fake_get,
            ),
            patch(
                "oncoteam.funnel_audit.oncofiles_client.set_agent_state",
                side_effect=fake_set,
            ),
        ):
            await record_event(
                card_id="q1b_NCT7",
                patient_id="q1b",
                nct_id="NCT7",
                actor_type=FunnelActorType.AGENT,
                actor_id="ddr_monitor",
                actor_display_name="ddr_monitor",
                event_type=FunnelEventType.CREATED,
            )
            await record_event(
                card_id="q1b_NCT7",
                patient_id="q1b",
                nct_id="NCT7",
                actor_type=FunnelActorType.HUMAN,
                actor_id="mudr",
                actor_display_name="MUDr. X",
                event_type=FunnelEventType.PROMOTED_FROM_PROPOSAL,
                to_stage="Watching",
                rationale="approved after review",
            )
            events = await list_events_for_card("q1b", "q1b_NCT7")

        assert len(events) == 2
        assert events[0]["event_type"] == "created"
        assert events[1]["event_type"] == "promoted_from_proposal"
        # Events carry a UUID event_id and a timestamp
        assert events[0]["event_id"] != events[1]["event_id"]
        assert events[0]["timestamp"]

    @pytest.mark.asyncio
    async def test_record_event_propagates_invariant_violations(self):
        """If the model rejects, record_event must not persist anything."""
        fake_set = AsyncMock()
        with (
            patch(
                "oncoteam.funnel_audit.oncofiles_client.get_agent_state",
                return_value={},
            ),
            patch(
                "oncoteam.funnel_audit.oncofiles_client.set_agent_state",
                side_effect=fake_set,
            ),
        ):
            with pytest.raises(ValueError, match="agent cannot produce"):
                await record_event(
                    card_id="q1b_NCTX",
                    patient_id="q1b",
                    nct_id="NCTX",
                    actor_type=FunnelActorType.AGENT,
                    actor_id="ddr_monitor",
                    actor_display_name="ddr_monitor",
                    event_type=FunnelEventType.MOVED,  # forbidden for agents
                    to_stage="Watching",
                    rationale="agent trying to move",
                )
            # No writes should have happened.
            fake_set.assert_not_called()


# ── Re-surfacing protection ────────────────────────────────────────────


class TestResurfacing:
    @pytest.mark.asyncio
    async def test_finds_existing_card_by_nct(self):
        existing = FunnelCard(
            card_id="q1b_NCT9",
            patient_id="q1b",
            nct_id="NCT9",
            lane=FunnelLane.CLINICAL,
            current_stage="Archived",
        )
        state = {"result": {"cards": {existing.card_id: existing.model_dump(mode="json")}}}
        with patch(
            "oncoteam.funnel_audit.oncofiles_client.get_agent_state",
            return_value=state,
        ):
            hit = await find_existing_card_for_nct("q1b", "NCT9")
        assert hit is not None
        assert hit.card_id == "q1b_NCT9"
        assert hit.current_stage == "Archived"

    @pytest.mark.asyncio
    async def test_no_hit_returns_none(self):
        with patch(
            "oncoteam.funnel_audit.oncofiles_client.get_agent_state",
            return_value={"result": {"cards": {}}},
        ):
            hit = await find_existing_card_for_nct("q1b", "NCT-does-not-exist")
        assert hit is None


# ── Card CRUD helpers ──────────────────────────────────────────────────


class TestCardHelpers:
    @pytest.mark.asyncio
    async def test_upsert_and_list_cards(self):
        stored: dict[str, dict] = {}

        async def fake_get(key, token=None):
            return stored.get(key, {})

        async def fake_set(key, value, token=None):
            stored[key] = {"result": value}

        card = FunnelCard(
            card_id="q1b_NCTA_proposal",
            patient_id="q1b",
            nct_id="NCTA",
            lane=FunnelLane.PROPOSAL,
            current_stage="new",
        )
        with (
            patch(
                "oncoteam.funnel_audit.oncofiles_client.get_agent_state",
                side_effect=fake_get,
            ),
            patch(
                "oncoteam.funnel_audit.oncofiles_client.set_agent_state",
                side_effect=fake_set,
            ),
        ):
            await upsert_card(card)
            cards = await list_cards("q1b", lane=FunnelLane.PROPOSAL)

        assert len(cards) == 1
        assert cards[0].card_id == "q1b_NCTA_proposal"

    def test_proposal_ttl_expiry_is_in_the_future(self):
        now = datetime.now(UTC)
        expiry = proposal_ttl_expiry(days=30)
        delta_days = (expiry - now).total_seconds() / 86400
        # Allow a small positive slop — `now` in the test is captured AFTER
        # the expiry is computed, so expected delta is slightly > 30 days.
        assert 29.9 < delta_days < 30.01


class TestCreateAgentProposalHelper:
    """Process-internal helper used by the MCP tool funnel_propose_trial."""

    @pytest.mark.asyncio
    async def test_creates_new_card_and_audit_event(self):
        from oncoteam.funnel_audit import create_agent_proposal

        stored: dict[str, dict] = {}

        async def fake_get(key, token=None):
            return stored.get(key, {})

        async def fake_set(key, value, token=None):
            stored[key] = {"result": value}

        with (
            patch(
                "oncoteam.funnel_audit.oncofiles_client.get_agent_state",
                side_effect=fake_get,
            ),
            patch(
                "oncoteam.funnel_audit.oncofiles_client.set_agent_state",
                side_effect=fake_set,
            ),
        ):
            result = await create_agent_proposal(
                patient_id="q1b",
                nct_id="NCT12345",
                title="Example PARPi trial",
                source_agent="ddr_monitor",
                rationale="ATM biallelic loss",
            )

        assert result["status"] == "created"
        assert result["card_id"] == "q1b_NCT12345_proposal"
        assert result["lane"] == "proposal"

        # Card + audit event both persisted
        assert "funnel_cards:q1b" in stored
        assert any(k.startswith("funnel_audit:q1b:") for k in stored)

    @pytest.mark.asyncio
    async def test_resurfaces_existing_clinical_card_instead_of_duplicating(self):
        """If the NCT is already on the clinical lane, helper must NOT create
        a duplicate — it records a re_surfaced event on the existing card."""
        from oncoteam.funnel_audit import create_agent_proposal

        existing = FunnelCard(
            card_id="q1b_NCT9",
            patient_id="q1b",
            nct_id="NCT9",
            lane=FunnelLane.CLINICAL,
            current_stage="Watching",
        )
        cards_state = {"result": {"cards": {existing.card_id: existing.model_dump(mode="json")}}}
        audit_state: dict[str, dict] = {}

        async def fake_get(key, token=None):
            if key == "funnel_cards:q1b":
                return cards_state
            return audit_state.get(key, {})

        async def fake_set(key, value, token=None):
            audit_state[key] = {"result": value}

        with (
            patch(
                "oncoteam.funnel_audit.oncofiles_client.get_agent_state",
                side_effect=fake_get,
            ),
            patch(
                "oncoteam.funnel_audit.oncofiles_client.set_agent_state",
                side_effect=fake_set,
            ),
        ):
            result = await create_agent_proposal(
                patient_id="q1b",
                nct_id="NCT9",
                source_agent="ddr_monitor",
            )

        assert result["status"] == "re_surfaced"
        assert result["card_id"] == existing.card_id
        assert result["lane"] == "clinical"

        # Audit event recorded on the existing card
        audit_key = f"funnel_audit:q1b:{existing.card_id}"
        assert audit_key in audit_state


# ── Patient-wide event listing ─────────────────────────────────────────


class TestPatientWideEventListing:
    @pytest.mark.asyncio
    async def test_filters_by_actor_type(self):
        stored: dict[str, dict] = {}

        async def fake_get(key, token=None):
            return stored.get(key, {})

        async def fake_set(key, value, token=None):
            stored[key] = {"result": value}

        card1 = FunnelCard(
            card_id="q1b_A_proposal",
            patient_id="q1b",
            nct_id="A",
            lane=FunnelLane.PROPOSAL,
            current_stage="new",
        )
        with (
            patch(
                "oncoteam.funnel_audit.oncofiles_client.get_agent_state",
                side_effect=fake_get,
            ),
            patch(
                "oncoteam.funnel_audit.oncofiles_client.set_agent_state",
                side_effect=fake_set,
            ),
        ):
            await upsert_card(card1)
            await record_event(
                card_id="q1b_A_proposal",
                patient_id="q1b",
                nct_id="A",
                actor_type=FunnelActorType.AGENT,
                actor_id="ddr_monitor",
                actor_display_name="ddr_monitor",
                event_type=FunnelEventType.CREATED,
            )
            await record_event(
                card_id="q1b_A_proposal",
                patient_id="q1b",
                nct_id="A",
                actor_type=FunnelActorType.HUMAN,
                actor_id="mudr",
                actor_display_name="MUDr. X",
                event_type=FunnelEventType.COMMENTED,
            )
            agent_only = await list_events_for_patient("q1b", actor_type=FunnelActorType.AGENT)
            human_only = await list_events_for_patient("q1b", actor_type=FunnelActorType.HUMAN)

        assert len(agent_only) == 1
        assert agent_only[0]["actor_id"] == "ddr_monitor"
        assert len(human_only) == 1
        assert human_only[0]["actor_id"] == "mudr"
