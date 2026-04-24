"""Tests for the patient_registry_sync agent + /api/internal/onboarding-queue
endpoint (#422 Sprint 96 S2).

Core invariant: the agent NEVER calls register_patient(). It detects, notifies,
and persists a snapshot — humans complete Gate 2.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch
from urllib.parse import urlencode

import pytest
from starlette.requests import Request

from oncoteam.api_admin import api_onboarding_queue
from oncoteam.autonomous_tasks import run_patient_registry_sync


def _make_request(path: str = "/api/internal/onboarding-queue") -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": path,
        "raw_path": path.encode(),
        "headers": [],
        "query_string": urlencode({}).encode(),
        "path_params": {},
    }

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    return Request(scope, receive)


@pytest.fixture
def mock_state():
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

    with (
        patch("oncoteam.autonomous_tasks.oncofiles_client.get_agent_state", side_effect=fake_get),
        patch("oncoteam.autonomous_tasks.oncofiles_client.set_agent_state", side_effect=fake_set),
        patch("oncoteam.api_admin.oncofiles_client.get_agent_state", side_effect=fake_get),
    ):
        yield store


class TestPatientRegistrySync:
    @pytest.mark.asyncio
    async def test_gate1_only_detected_and_notified(self, mock_state):
        """New Gate-1-only patient triggers a WhatsApp push + snapshot write."""
        list_patients_mock = AsyncMock(
            return_value={
                "patients": [
                    {
                        "slug": "q1b",
                        "name": "Erika F.",
                        "patient_type": "oncology",
                        "documents": 113,
                    },
                    {
                        "slug": "nora-antalova",
                        "name": "Nora A.",
                        "patient_type": "oncology",
                        "documents": 112,
                    },
                    {
                        "slug": "mattias-cesnak",
                        "name": "Mattias C.",
                        "patient_type": "oncology",
                        "documents": 20,
                    },
                ]
            }
        )
        register_mock = AsyncMock()  # MUST NOT be called
        whatsapp_mock = AsyncMock(return_value={"ok": True})

        def list_ids_mock():
            return ["q1b", "e5g"]

        with (
            patch("oncoteam.autonomous_tasks.oncofiles_client.list_patients", list_patients_mock),
            patch("oncoteam.autonomous_tasks._send_whatsapp", whatsapp_mock),
            patch("oncoteam.autonomous_tasks.oncofiles_client.add_activity_log", AsyncMock()),
            patch("oncoteam.autonomous_tasks.oncofiles_client.log_conversation", AsyncMock()),
            patch("oncoteam.patient_context.list_patient_ids", list_ids_mock),
            # Assert the agent NEVER auto-registers.
            patch("oncoteam.patient_context.register_patient", register_mock),
        ):
            result = await run_patient_registry_sync()

        assert result["ok"] is True
        assert set(result["gate1_only"]) == {"nora-antalova", "mattias-cesnak"}
        assert set(result["gate1_new_arrivals"]) == {"nora-antalova", "mattias-cesnak"}
        assert result["gate2_ok"] == ["q1b"]
        # Two new Gate-1-only arrivals → two WhatsApp pushes.
        assert whatsapp_mock.call_count == 2
        for call in whatsapp_mock.call_args_list:
            # System-level — patient_id=None bypasses per-patient policy.
            assert call.kwargs.get("patient_id") is None
        # Snapshot written.
        assert "patient_registry:last_snapshot" in mock_state
        snapshot = mock_state["patient_registry:last_snapshot"]
        assert snapshot["gate1_only_count"] == 2
        assert snapshot["gate2_ok_count"] == 1
        # Invariant: register_patient is NEVER called by the sync agent.
        register_mock.assert_not_called()

    @pytest.mark.asyncio
    async def test_second_run_does_not_renotify(self, mock_state):
        """Running the agent twice in succession does not double-push."""
        list_patients_mock = AsyncMock(
            return_value={
                "patients": [
                    {
                        "slug": "nora-antalova",
                        "name": "Nora A.",
                        "patient_type": "oncology",
                        "documents": 112,
                    }
                ]
            }
        )
        whatsapp_mock = AsyncMock(return_value={"ok": True})

        def list_ids_mock():
            return ["q1b"]

        with (
            patch("oncoteam.autonomous_tasks.oncofiles_client.list_patients", list_patients_mock),
            patch("oncoteam.autonomous_tasks._send_whatsapp", whatsapp_mock),
            patch("oncoteam.autonomous_tasks.oncofiles_client.add_activity_log", AsyncMock()),
            patch("oncoteam.autonomous_tasks.oncofiles_client.log_conversation", AsyncMock()),
            patch("oncoteam.patient_context.list_patient_ids", list_ids_mock),
        ):
            await run_patient_registry_sync()
            pushes_after_first = whatsapp_mock.call_count
            await run_patient_registry_sync()

        # Second run should not re-push for the same Gate-1-only patient.
        assert pushes_after_first == 1
        assert whatsapp_mock.call_count == 1

    @pytest.mark.asyncio
    async def test_gate2_present_no_push(self, mock_state):
        """If every oncofiles patient is already Gate-2-registered, no push."""
        list_patients_mock = AsyncMock(
            return_value={
                "patients": [
                    {
                        "slug": "q1b",
                        "name": "Erika F.",
                        "patient_type": "oncology",
                        "documents": 113,
                    },
                    {"slug": "e5g", "name": "Peter F.", "patient_type": "general", "documents": 51},
                ]
            }
        )
        whatsapp_mock = AsyncMock()

        def list_ids_mock():
            return ["q1b", "e5g"]

        with (
            patch("oncoteam.autonomous_tasks.oncofiles_client.list_patients", list_patients_mock),
            patch("oncoteam.autonomous_tasks._send_whatsapp", whatsapp_mock),
            patch("oncoteam.autonomous_tasks.oncofiles_client.add_activity_log", AsyncMock()),
            patch("oncoteam.autonomous_tasks.oncofiles_client.log_conversation", AsyncMock()),
            patch("oncoteam.patient_context.list_patient_ids", list_ids_mock),
        ):
            result = await run_patient_registry_sync()

        whatsapp_mock.assert_not_called()
        assert result["gate1_only"] == []

    @pytest.mark.asyncio
    async def test_archived_patients_logged_not_deleted(self, mock_state):
        """A patient that disappears from oncofiles is logged as archived."""
        # Seed a prior snapshot that includes sgu.
        mock_state["patient_registry:last_snapshot"] = {
            "timestamp": "2026-04-23T00:00:00+00:00",
            "patients": [
                {"slug": "q1b", "name": "Erika F.", "classification": "gate2_ok"},
                {"slug": "sgu", "name": "Peter F. 2", "classification": "gate2_ok"},
            ],
        }
        list_patients_mock = AsyncMock(
            return_value={
                "patients": [
                    {
                        "slug": "q1b",
                        "name": "Erika F.",
                        "patient_type": "oncology",
                        "documents": 113,
                    }
                ]
            }
        )
        activity_log_mock = AsyncMock()

        with (
            patch("oncoteam.autonomous_tasks.oncofiles_client.list_patients", list_patients_mock),
            patch("oncoteam.autonomous_tasks._send_whatsapp", AsyncMock()),
            patch("oncoteam.autonomous_tasks.oncofiles_client.add_activity_log", activity_log_mock),
            patch("oncoteam.autonomous_tasks.oncofiles_client.log_conversation", AsyncMock()),
            patch("oncoteam.patient_context.list_patient_ids", lambda: ["q1b"]),
        ):
            result = await run_patient_registry_sync()

        assert "sgu" in result["archived"]
        # Activity log was invoked for the archived slug.
        calls = [c for c in activity_log_mock.call_args_list if "sgu" in str(c)]
        assert len(calls) >= 1

    @pytest.mark.asyncio
    async def test_oncofiles_failure_is_soft(self, mock_state):
        """list_patients failure should return ok=False, not raise."""
        list_patients_mock = AsyncMock(side_effect=RuntimeError("oncofiles unreachable"))
        with (
            patch("oncoteam.autonomous_tasks.oncofiles_client.list_patients", list_patients_mock),
            patch("oncoteam.autonomous_tasks._send_whatsapp", AsyncMock()),
            patch("oncoteam.patient_context.list_patient_ids", lambda: ["q1b"]),
        ):
            result = await run_patient_registry_sync()
        assert result["ok"] is False
        assert "oncofiles unreachable" in result["error"]


class TestOnboardingQueueEndpoint:
    @pytest.mark.asyncio
    async def test_snapshot_missing_returns_stale_true(self, mock_state):
        resp = await api_onboarding_queue(_make_request())
        data = json.loads(resp.body)
        assert resp.status_code == 200
        assert data["queue"] == []
        assert data["count"] == 0
        assert data["stale"] is True

    @pytest.mark.asyncio
    async def test_snapshot_surfaces_gate1_only(self, mock_state):
        mock_state["patient_registry:last_snapshot"] = {
            "timestamp": "2026-04-24T01:45:00+00:00",
            "patients": [
                {
                    "slug": "nora-antalova",
                    "name": "Nora A.",
                    "patient_type": "oncology",
                    "documents": 112,
                    "first_seen_in_oncofiles": "2026-04-15T00:00:00Z",
                    "flagged_at": "2026-04-24T01:45:00+00:00",
                    "classification": "gate1_only",
                },
                {
                    "slug": "q1b",
                    "name": "Erika F.",
                    "patient_type": "oncology",
                    "documents": 113,
                    "classification": "gate2_ok",
                },
            ],
            "gate1_only_count": 1,
            "gate2_ok_count": 1,
        }
        resp = await api_onboarding_queue(_make_request())
        data = json.loads(resp.body)
        assert resp.status_code == 200
        assert data["count"] == 1
        assert data["stale"] is False
        assert data["queue"][0]["slug"] == "nora-antalova"
        # Gate-2 patients must not leak into the queue.
        assert all(e["slug"] != "q1b" for e in data["queue"])

    @pytest.mark.asyncio
    async def test_snapshot_error_degrades_gracefully(self):
        async def fake_get(key, agent_id="oncoteam", token=None):
            raise RuntimeError("oncofiles unreachable")

        with patch("oncoteam.api_admin.oncofiles_client.get_agent_state", side_effect=fake_get):
            resp = await api_onboarding_queue(_make_request())
        data = json.loads(resp.body)
        assert resp.status_code == 200
        assert data["queue"] == []
        assert data["stale"] is True
        assert data["error"] == "snapshot unavailable"
