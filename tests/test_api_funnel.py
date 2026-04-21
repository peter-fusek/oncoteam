"""Tests for the two-lane funnel API endpoints (#395).

Mocks oncofiles_client and focuses on the HTTP-layer contract:
    - Agent tokens are rejected from POST /api/funnel/cards
    - Re-surfacing collapses duplicate proposals and emits RE_SURFACED event
    - promote requires rationale; move requires rationale + to_stage
    - audit endpoints return events in expected shape
"""

from __future__ import annotations

import json
from unittest.mock import patch
from urllib.parse import urlencode

import pytest
from starlette.requests import Request

from oncoteam.api_funnel import (
    api_funnel_audit_for_card,
    api_funnel_audit_for_patient,
    api_funnel_cards_get,
    api_funnel_cards_post,
    api_funnel_proposals_get,
    api_funnel_proposals_post,
)


def _make_request(
    method: str = "GET",
    path: str = "/api/funnel/proposals",
    body: dict | None = None,
    headers: dict[str, str] | None = None,
    query: dict[str, str] | None = None,
    path_params: dict[str, str] | None = None,
) -> Request:
    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "raw_path": path.encode(),
        "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()],
        "query_string": urlencode(query or {}).encode(),
        "path_params": path_params or {},
    }
    # Pre-load body bytes so starlette returns them sync when .json() is awaited
    payload = json.dumps(body or {}).encode() if body is not None else b""

    async def receive():
        return {"type": "http.request", "body": payload, "more_body": False}

    return Request(scope, receive)


@pytest.fixture(autouse=True)
def _patient_id_q1b():
    """Short-circuit dashboard_api._get_patient_id to always return q1b."""
    with patch("oncoteam.api_funnel._get_patient_id", return_value="q1b"):
        yield


@pytest.fixture(autouse=True)
def _token_none():
    with patch("oncoteam.api_funnel._get_token_for_patient", return_value=None):
        yield


@pytest.fixture
def mock_oncofiles():
    """Fresh in-memory oncofiles agent_state per test."""
    store: dict[str, dict] = {}

    async def fake_get(key, token=None):
        return store.get(key, {})

    async def fake_set(key, value, token=None):
        store[key] = {"result": value}

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
        yield store


# ── Agent lane isolation ───────────────────────────────────────────────


class TestAgentLaneIsolation:
    @pytest.mark.asyncio
    async def test_agent_can_post_proposals(self, mock_oncofiles):
        req = _make_request(
            method="POST",
            path="/api/funnel/proposals",
            body={
                "nct_id": "NCT01",
                "title": "DDR-deficient mCRC PARPi trial",
                "biomarker_match": {"ATM": "biallelic"},
                "source_agent": "ddr_monitor",
                "actor_type": "agent",
                "actor_id": "ddr_monitor",
                "actor_display_name": "ddr_monitor",
            },
        )
        resp = await api_funnel_proposals_post(req)
        data = json.loads(resp.body)
        assert resp.status_code == 201
        assert data["status"] == "created"
        assert data["card"]["lane"] == "proposal"
        assert data["card"]["nct_id"] == "NCT01"

    @pytest.mark.asyncio
    async def test_agent_rejected_from_clinical_cards(self, mock_oncofiles):
        req = _make_request(
            method="POST",
            path="/api/funnel/cards",
            headers={
                "X-Actor-Type": "agent",
                "X-Actor-Id": "ddr_monitor",
                "X-Actor-Display-Name": "ddr_monitor",
            },
            body={
                "action": "move",
                "card_id": "q1b_NCT01",
                "to_stage": "Watching",
                "rationale": "agent trying to move",
            },
        )
        resp = await api_funnel_cards_post(req)
        data = json.loads(resp.body)
        assert resp.status_code == 403
        assert data["code"] == "agent_not_allowed"


# ── Re-surfacing protection ────────────────────────────────────────────


class TestResurfacing:
    @pytest.mark.asyncio
    async def test_second_proposal_for_same_nct_returns_resurfaced(self, mock_oncofiles):
        # First proposal creates the card.
        req1 = _make_request(
            method="POST",
            body={
                "nct_id": "NCT02",
                "title": "First time seeing NCT02",
                "source_agent": "ddr_monitor",
                "actor_type": "agent",
                "actor_id": "ddr_monitor",
                "actor_display_name": "ddr_monitor",
            },
        )
        r1 = await api_funnel_proposals_post(req1)
        assert r1.status_code == 201
        # Second proposal for same NCT should re-surface, not create a duplicate.
        req2 = _make_request(
            method="POST",
            body={
                "nct_id": "NCT02",
                "title": "trial_monitor also saw NCT02",
                "source_agent": "trial_monitor",
                "actor_type": "agent",
                "actor_id": "trial_monitor",
                "actor_display_name": "trial_monitor",
            },
        )
        r2 = await api_funnel_proposals_post(req2)
        data = json.loads(r2.body)
        assert r2.status_code == 200
        assert data["status"] == "re_surfaced"
        assert data["card"]["nct_id"] == "NCT02"
        # The event log for that card now includes a re_surfaced event.
        get_req = _make_request(
            method="GET",
            path_params={"card_id": data["card"]["card_id"]},
        )
        audit_resp = await api_funnel_audit_for_card(get_req)
        events = json.loads(audit_resp.body)["events"]
        event_types = [e["event_type"] for e in events]
        assert "created" in event_types
        assert "re_surfaced" in event_types


# ── Promote requires rationale ─────────────────────────────────────────


class TestPromoteGates:
    @pytest.mark.asyncio
    async def test_promote_without_rationale_rejected(self, mock_oncofiles):
        # Seed proposal.
        await api_funnel_proposals_post(
            _make_request(
                method="POST",
                body={
                    "nct_id": "NCT03",
                    "title": "Promote test",
                    "actor_type": "agent",
                    "actor_id": "ddr_monitor",
                    "actor_display_name": "ddr_monitor",
                },
            )
        )
        req = _make_request(
            method="POST",
            path="/api/funnel/cards",
            headers={
                "X-Actor-Type": "human",
                "X-Actor-Id": "mudr",
                "X-Actor-Display-Name": "MUDr. X",
            },
            body={
                "action": "promote",
                "card_id": "q1b_NCT03_proposal",
                "to_stage": "Watching",
                # rationale intentionally missing
            },
        )
        resp = await api_funnel_cards_post(req)
        assert resp.status_code == 400
        assert "rationale" in json.loads(resp.body)["error"]

    @pytest.mark.asyncio
    async def test_promote_with_rationale_creates_clinical_card(self, mock_oncofiles):
        await api_funnel_proposals_post(
            _make_request(
                method="POST",
                body={
                    "nct_id": "NCT04",
                    "title": "Promote happy path",
                    "actor_type": "agent",
                    "actor_id": "ddr_monitor",
                    "actor_display_name": "ddr_monitor",
                },
            )
        )
        req = _make_request(
            method="POST",
            path="/api/funnel/cards",
            headers={
                "X-Actor-Type": "human",
                "X-Actor-Id": "mudr",
                "X-Actor-Display-Name": "MUDr. X",
            },
            body={
                "action": "promote",
                "card_id": "q1b_NCT04_proposal",
                "to_stage": "Watching",
                "rationale": "DDR-deficient profile matches eligibility",
            },
        )
        resp = await api_funnel_cards_post(req)
        data = json.loads(resp.body)
        assert resp.status_code == 200
        assert data["status"] == "promoted"
        assert data["card"]["lane"] == "clinical"
        assert data["card"]["current_stage"] == "Watching"
        # Clinical-lane listing now includes the card.
        list_resp = await api_funnel_cards_get(
            _make_request(method="GET", query={"lane": "clinical"})
        )
        cards = json.loads(list_resp.body)["cards"]
        assert any(c["nct_id"] == "NCT04" for c in cards)


# ── Move requires rationale + to_stage on existing clinical card ───────


class TestMoveRules:
    @pytest.mark.asyncio
    async def test_move_on_proposal_rejected(self, mock_oncofiles):
        await api_funnel_proposals_post(
            _make_request(
                method="POST",
                body={
                    "nct_id": "NCT05",
                    "title": "Move rule test",
                    "actor_type": "agent",
                    "actor_id": "ddr_monitor",
                    "actor_display_name": "ddr_monitor",
                },
            )
        )
        req = _make_request(
            method="POST",
            path="/api/funnel/cards",
            headers={
                "X-Actor-Type": "human",
                "X-Actor-Id": "mudr",
                "X-Actor-Display-Name": "MUDr. X",
            },
            body={
                "action": "move",
                "card_id": "q1b_NCT05_proposal",
                "to_stage": "Candidate",
                "rationale": "skipping the promote step",
            },
        )
        resp = await api_funnel_cards_post(req)
        assert resp.status_code == 400
        # Error mentions that proposals need to be promoted first.
        assert "promote" in json.loads(resp.body)["error"]


# ── Audit endpoints ────────────────────────────────────────────────────


class TestAuditEndpoints:
    @pytest.mark.asyncio
    async def test_audit_for_patient_filter_by_actor(self, mock_oncofiles):
        await api_funnel_proposals_post(
            _make_request(
                method="POST",
                body={
                    "nct_id": "NCT06",
                    "title": "Audit filter",
                    "actor_type": "agent",
                    "actor_id": "ddr_monitor",
                    "actor_display_name": "ddr_monitor",
                },
            )
        )
        req = _make_request(
            method="GET",
            path="/api/funnel/audit/patient",
            query={"actor_type": "agent"},
        )
        resp = await api_funnel_audit_for_patient(req)
        data = json.loads(resp.body)
        assert resp.status_code == 200
        assert data["count"] == 1
        assert data["events"][0]["actor_id"] == "ddr_monitor"
        # Vocab is included so the UI can render the correct stage list.
        assert "Watching" in data["vocab"]["clinical_stages"]
        assert "new" in data["vocab"]["proposal_stages"]

    @pytest.mark.asyncio
    async def test_proposals_get_lists_active_proposals(self, mock_oncofiles):
        await api_funnel_proposals_post(
            _make_request(
                method="POST",
                body={
                    "nct_id": "NCT07",
                    "title": "Listing test",
                    "actor_type": "agent",
                    "actor_id": "ddr_monitor",
                    "actor_display_name": "ddr_monitor",
                },
            )
        )
        resp = await api_funnel_proposals_get(_make_request(method="GET"))
        data = json.loads(resp.body)
        assert data["count"] == 1
        assert data["cards"][0]["current_stage"] == "new"
