"""Tests for the oncopanel Inbox API (#399 Sprint 96 S1).

Covers:
    - GET /api/oncopanel/pending parses raw_response + surfaces summary
    - POST approve persists approved_oncopanel:* + flips pending to approved
      + appends to patient oncopanel_history in-memory
    - POST dismiss flips pending to dismissed
    - Agent actor rejected from triage (physician-only)
    - Already-triaged entries return 409
    - Unparseable raw_response requires body `panel` override
    - Active-tab preference round-trip
"""

from __future__ import annotations

import json
from unittest.mock import patch
from urllib.parse import urlencode

import pytest
from starlette.requests import Request

from oncoteam.api_oncopanel import (
    api_oncopanel_audit_get,
    api_oncopanel_pending_get,
    api_oncopanel_pending_post,
    api_research_active_tab_get,
    api_research_active_tab_post,
)


def _make_request(
    method: str = "GET",
    path: str = "/api/oncopanel/pending",
    body: dict | None = None,
    headers: dict[str, str] | None = None,
    query: dict[str, str] | None = None,
) -> Request:
    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "raw_path": path.encode(),
        "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()],
        "query_string": urlencode(query or {}).encode(),
        "path_params": {},
    }
    payload = json.dumps(body or {}).encode() if body is not None else b""

    async def receive():
        return {"type": "http.request", "body": payload, "more_body": False}

    return Request(scope, receive)


_SAMPLE_RAW_RESPONSE = """Based on the NGS report here is the structured extraction.

```json
{
  "panel_id": "q1b_oncopanel_2026-04-18",
  "patient_id": "q1b",
  "report_date": "2026-04-18",
  "lab": "OUSA",
  "sample_type": "tumor_tissue",
  "methodology": "TruSight-500",
  "variants": [
    {
      "gene": "KRAS",
      "hgvs_cdna": "c.34G>A",
      "hgvs_protein": "p.(Gly12Ser)",
      "protein_short": "G12S",
      "vaf": 0.1281,
      "variant_type": "SNV",
      "tier": "IA",
      "classification": "somatic",
      "significance": "pathogenic",
      "source_document_id": "278"
    }
  ],
  "cnvs": [],
  "msi_status": "MSS",
  "mmr_status": "pMMR",
  "tmb_score": 6.67,
  "tmb_category": "low",
  "source_document_id": "278"
}
```

This report is a somatic oncopanel."""


@pytest.fixture(autouse=True)
def _patient_id_q1b():
    with patch("oncoteam.api_oncopanel._get_patient_id", return_value="q1b"):
        yield


@pytest.fixture(autouse=True)
def _token_none():
    with patch("oncoteam.api_oncopanel._get_token_for_patient", return_value=None):
        yield


@pytest.fixture
def mock_store():
    """In-memory oncofiles agent_state shim."""
    store: dict[str, object] = {}

    async def fake_get(key, agent_id="oncoteam", token=None):
        val = store.get(key)
        if val is None:
            return {}
        return {"value": val}

    async def fake_set(key, value, agent_id="oncoteam", token=None):
        store[key] = value
        return {"ok": True}

    async def fake_list(agent_id="oncoteam", limit=500, token=None):
        return {
            "states": [{"key": k, "value": v} for k, v in store.items()],
        }

    with (
        patch("oncoteam.api_oncopanel.get_agent_state", side_effect=fake_get),
        patch("oncoteam.api_oncopanel.set_agent_state", side_effect=fake_set),
        patch("oncoteam.api_oncopanel.list_agent_states", side_effect=fake_list),
    ):
        yield store


class TestPendingList:
    @pytest.mark.asyncio
    async def test_empty_list(self, mock_store):
        resp = await api_oncopanel_pending_get(_make_request())
        data = json.loads(resp.body)
        assert resp.status_code == 200
        assert data["pending"] == []
        assert data["recent_triaged"] == []
        assert data["count"] == 0

    @pytest.mark.asyncio
    async def test_lists_pending_with_summary(self, mock_store):
        mock_store["pending_oncopanel:q1b:278"] = {
            "timestamp": "2026-04-18T10:00:00+00:00",
            "document_id": 278,
            "patient_id": "q1b",
            "raw_response": _SAMPLE_RAW_RESPONSE,
            "status": "pending_physician_review",
            "extraction_cost_usd": 0.12,
            "extraction_model": "claude-sonnet-4-6",
        }
        resp = await api_oncopanel_pending_get(_make_request())
        data = json.loads(resp.body)
        assert data["count"] == 1
        item = data["pending"][0]
        assert item["document_id"] == 278
        assert item["status"] == "pending_physician_review"
        assert item["summary"]["variant_count"] == 1
        assert item["summary"]["variants_preview"][0]["gene"] == "KRAS"
        assert item["summary"]["msi_status"] == "MSS"

    @pytest.mark.asyncio
    async def test_triaged_moves_to_recent(self, mock_store):
        mock_store["pending_oncopanel:q1b:278"] = {
            "timestamp": "2026-04-18T10:00:00+00:00",
            "document_id": 278,
            "raw_response": _SAMPLE_RAW_RESPONSE,
            "status": "approved",
            "approved_by": "physician",
            "approved_at": "2026-04-18T11:00:00+00:00",
        }
        resp = await api_oncopanel_pending_get(_make_request())
        data = json.loads(resp.body)
        assert data["pending"] == []
        assert data["count"] == 0
        assert len(data["recent_triaged"]) == 1
        assert data["recent_triaged"][0]["status"] == "approved"

    @pytest.mark.asyncio
    async def test_filters_other_patient(self, mock_store):
        # Keys for a different patient must be ignored even if list_agent_states
        # returned everything in the agent_id bucket.
        mock_store["pending_oncopanel:other:100"] = {
            "timestamp": "2026-04-18T10:00:00+00:00",
            "document_id": 100,
            "raw_response": _SAMPLE_RAW_RESPONSE,
            "status": "pending_physician_review",
        }
        resp = await api_oncopanel_pending_get(_make_request())
        data = json.loads(resp.body)
        assert data["count"] == 0


class TestApprove:
    @pytest.mark.asyncio
    async def test_approve_requires_rationale(self, mock_store):
        mock_store["pending_oncopanel:q1b:278"] = {
            "timestamp": "2026-04-18T10:00:00+00:00",
            "document_id": 278,
            "raw_response": _SAMPLE_RAW_RESPONSE,
            "status": "pending_physician_review",
        }
        resp = await api_oncopanel_pending_post(
            _make_request(
                method="POST",
                body={"action": "approve", "document_id": 278},
            )
        )
        assert resp.status_code == 400
        assert b"rationale is required" in resp.body

    @pytest.mark.asyncio
    async def test_approve_rejects_agents(self, mock_store):
        mock_store["pending_oncopanel:q1b:278"] = {
            "timestamp": "2026-04-18T10:00:00+00:00",
            "document_id": 278,
            "raw_response": _SAMPLE_RAW_RESPONSE,
            "status": "pending_physician_review",
        }
        resp = await api_oncopanel_pending_post(
            _make_request(
                method="POST",
                headers={"X-Actor-Type": "agent", "X-Actor-Id": "ddr_monitor"},
                body={
                    "action": "approve",
                    "document_id": 278,
                    "rationale": "agent tried to triage",
                },
            )
        )
        assert resp.status_code == 403
        data = json.loads(resp.body)
        assert data["code"] == "agent_not_allowed"

    @pytest.mark.asyncio
    async def test_approve_happy_path(self, mock_store):
        mock_store["pending_oncopanel:q1b:278"] = {
            "timestamp": "2026-04-18T10:00:00+00:00",
            "document_id": 278,
            "raw_response": _SAMPLE_RAW_RESPONSE,
            "status": "pending_physician_review",
        }
        with patch("oncoteam.api_oncopanel.append_approved_oncopanel") as mock_append:
            resp = await api_oncopanel_pending_post(
                _make_request(
                    method="POST",
                    headers={
                        "X-Actor-Type": "human",
                        "X-Actor-Id": "minarikova",
                        "X-Actor-Display-Name": "MUDr. Minarikova",
                    },
                    body={
                        "action": "approve",
                        "document_id": 278,
                        "rationale": "NGS matches Feb report. G12S + ATM + TP53 verified.",
                    },
                )
            )
        data = json.loads(resp.body)
        assert resp.status_code == 200
        assert data["status"] == "approved"
        assert data["panel_id"] == "q1b_oncopanel_2026-04-18"

        # approved_oncopanel:* written
        approved = mock_store.get("approved_oncopanel:q1b:q1b_oncopanel_2026-04-18")
        assert approved is not None
        assert approved["verified_by"] == "MUDr. Minarikova"
        assert approved["verified_status"] == "approved"
        assert len(approved["variants"]) == 1

        # pending flipped to approved
        pending = mock_store["pending_oncopanel:q1b:278"]
        assert pending["status"] == "approved"
        assert pending["approved_by"] == "minarikova"
        assert "MUDr. Minarikova" in pending.get("approved_by_display", "")

        # audit event recorded
        audit = mock_store["oncopanel_audit:q1b"]
        assert isinstance(audit, dict)
        assert len(audit["events"]) == 1
        assert audit["events"][0]["action"] == "approve"
        assert audit["events"][0]["variant_count"] == 1

        # in-memory registry was asked to merge
        mock_append.assert_called_once()

    @pytest.mark.asyncio
    async def test_already_triaged_returns_409(self, mock_store):
        mock_store["pending_oncopanel:q1b:278"] = {
            "timestamp": "2026-04-18T10:00:00+00:00",
            "document_id": 278,
            "raw_response": _SAMPLE_RAW_RESPONSE,
            "status": "approved",
            "approved_by": "minarikova",
        }
        resp = await api_oncopanel_pending_post(
            _make_request(
                method="POST",
                body={
                    "action": "approve",
                    "document_id": 278,
                    "rationale": "retry",
                },
            )
        )
        assert resp.status_code == 409
        assert json.loads(resp.body)["code"] == "already_triaged"

    @pytest.mark.asyncio
    async def test_unparseable_without_override(self, mock_store):
        mock_store["pending_oncopanel:q1b:278"] = {
            "timestamp": "2026-04-18T10:00:00+00:00",
            "document_id": 278,
            "raw_response": "This report is unreadable, no JSON here.",
            "status": "pending_physician_review",
        }
        resp = await api_oncopanel_pending_post(
            _make_request(
                method="POST",
                body={
                    "action": "approve",
                    "document_id": 278,
                    "rationale": "attempting approve",
                },
            )
        )
        assert resp.status_code == 400
        assert json.loads(resp.body)["code"] == "panel_unparseable"

    @pytest.mark.asyncio
    async def test_panel_override_accepted(self, mock_store):
        mock_store["pending_oncopanel:q1b:278"] = {
            "timestamp": "2026-04-18T10:00:00+00:00",
            "document_id": 278,
            "raw_response": "no fenced json",
            "status": "pending_physician_review",
        }
        resp = await api_oncopanel_pending_post(
            _make_request(
                method="POST",
                body={
                    "action": "approve",
                    "document_id": 278,
                    "rationale": "hand-entered from paper",
                    "panel": {
                        "panel_id": "q1b_manual_2026-04-18",
                        "patient_id": "q1b",
                        "report_date": "2026-04-18",
                        "variants": [],
                        "msi_status": "MSS",
                    },
                },
            )
        )
        data = json.loads(resp.body)
        assert resp.status_code == 200
        assert data["panel_id"] == "q1b_manual_2026-04-18"


class TestDismiss:
    @pytest.mark.asyncio
    async def test_dismiss_flips_status(self, mock_store):
        mock_store["pending_oncopanel:q1b:278"] = {
            "timestamp": "2026-04-18T10:00:00+00:00",
            "document_id": 278,
            "raw_response": _SAMPLE_RAW_RESPONSE,
            "status": "pending_physician_review",
        }
        resp = await api_oncopanel_pending_post(
            _make_request(
                method="POST",
                headers={"X-Actor-Type": "human", "X-Actor-Id": "minarikova"},
                body={
                    "action": "dismiss",
                    "document_id": 278,
                    "rationale": "Wrong patient — different case number",
                },
            )
        )
        assert resp.status_code == 200
        assert json.loads(resp.body)["status"] == "dismissed"

        pending = mock_store["pending_oncopanel:q1b:278"]
        assert pending["status"] == "dismissed"
        assert pending["dismissed_by"] == "minarikova"

        audit = mock_store["oncopanel_audit:q1b"]
        assert audit["events"][0]["action"] == "dismiss"

    @pytest.mark.asyncio
    async def test_dismiss_nonexistent_404(self, mock_store):
        resp = await api_oncopanel_pending_post(
            _make_request(
                method="POST",
                body={"action": "dismiss", "document_id": 9999, "rationale": "x"},
            )
        )
        assert resp.status_code == 404


class TestAudit:
    @pytest.mark.asyncio
    async def test_audit_newest_first(self, mock_store):
        mock_store["oncopanel_audit:q1b"] = {
            "events": [
                {"ts": "2026-04-18T10:00:00+00:00", "action": "dismiss"},
                {"ts": "2026-04-19T10:00:00+00:00", "action": "approve"},
            ]
        }
        resp = await api_oncopanel_audit_get(_make_request())
        data = json.loads(resp.body)
        assert resp.status_code == 200
        assert data["count"] == 2
        assert data["events"][0]["action"] == "approve"  # newest


class TestActiveTab:
    @pytest.mark.asyncio
    async def test_round_trip(self, mock_store):
        resp = await api_research_active_tab_post(
            _make_request(
                method="POST",
                headers={"X-Actor-Type": "human", "X-Actor-Id": "minarikova"},
                body={"tab": "inbox"},
            )
        )
        assert resp.status_code == 200

        resp2 = await api_research_active_tab_get(
            _make_request(
                headers={"X-Actor-Type": "human", "X-Actor-Id": "minarikova"},
            )
        )
        data = json.loads(resp2.body)
        assert data["tab"] == "inbox"

    @pytest.mark.asyncio
    async def test_unknown_tab_rejected(self, mock_store):
        resp = await api_research_active_tab_post(
            _make_request(
                method="POST",
                body={"tab": "fundraiser"},
            )
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_per_user_isolation(self, mock_store):
        await api_research_active_tab_post(
            _make_request(
                method="POST",
                headers={"X-Actor-Id": "minarikova"},
                body={"tab": "inbox"},
            )
        )
        await api_research_active_tab_post(
            _make_request(
                method="POST",
                headers={"X-Actor-Id": "peter"},
                body={"tab": "funnel"},
            )
        )
        r_minari = await api_research_active_tab_get(
            _make_request(headers={"X-Actor-Id": "minarikova"})
        )
        r_peter = await api_research_active_tab_get(_make_request(headers={"X-Actor-Id": "peter"}))
        assert json.loads(r_minari.body)["tab"] == "inbox"
        assert json.loads(r_peter.body)["tab"] == "funnel"
