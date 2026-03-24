"""Tests for onboarding API endpoints (#138)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from oncoteam.dashboard_api import api_onboard_patient, api_onboarding_status


class FakeRequest:
    def __init__(self, body_dict: dict | None = None):
        self.method = "POST"
        self.headers = {"origin": "https://dashboard.oncoteam.cloud"}
        self._body_dict = body_dict

    async def json(self):
        if self._body_dict is None:
            raise ValueError("No JSON body")
        return self._body_dict


# ── POST /api/internal/onboard-patient ────────────────


@pytest.mark.anyio
@patch("oncoteam.dashboard_api.oncofiles_client.create_patient_via_api", new_callable=AsyncMock)
@patch("oncoteam.patient_context.register_patient")
async def test_onboard_patient_success(mock_register, mock_create):
    mock_create.return_value = {
        "patient": {"patient_id": "jan_novak", "display_name": "Ján Novák"},
        "bearer_token": "tok_abc123",
    }

    request = FakeRequest(
        {
            "patient_id": "jan_novak",
            "display_name": "Ján Novák",
            "diagnosis_summary": "CRC stage IV",
            "preferred_lang": "sk",
            "phone": "+421900111222",
        }
    )
    response = await api_onboard_patient(request)
    data = json.loads(response.body)

    assert response.status_code == 200
    assert data["status"] == "created"
    assert data["patient_id"] == "jan_novak"
    assert data["bearer_token"] == "tok_abc123"

    mock_create.assert_called_once_with(
        patient_id="jan_novak",
        display_name="Ján Novák",
        diagnosis_summary="CRC stage IV",
        preferred_lang="sk",
        caregiver_email="",
    )


@pytest.mark.anyio
@patch("oncoteam.dashboard_api.oncofiles_client.create_patient_via_api", new_callable=AsyncMock)
async def test_onboard_patient_conflict(mock_create):
    """409 from oncofiles means patient already exists."""
    mock_response = MagicMock()
    mock_response.status_code = 409
    mock_create.side_effect = httpx.HTTPStatusError(
        "Conflict", request=MagicMock(), response=mock_response
    )

    request = FakeRequest({"patient_id": "jan_novak", "display_name": "Ján Novák"})
    response = await api_onboard_patient(request)
    data = json.loads(response.body)

    assert response.status_code == 200
    assert data["status"] == "exists"
    assert data["patient_id"] == "jan_novak"


@pytest.mark.anyio
@patch("oncoteam.dashboard_api.oncofiles_client.create_patient_via_api", new_callable=AsyncMock)
async def test_onboard_patient_oncofiles_down(mock_create):
    """Connection error when oncofiles is unreachable."""
    mock_create.side_effect = ConnectionError("oncofiles unreachable")

    request = FakeRequest({"patient_id": "jan_novak", "display_name": "Ján Novák"})
    response = await api_onboard_patient(request)
    data = json.loads(response.body)

    assert response.status_code == 502
    assert "error" in data


@pytest.mark.anyio
async def test_onboard_patient_missing_fields():
    """Missing patient_id or display_name returns 400."""
    request = FakeRequest({"patient_id": "", "display_name": ""})
    response = await api_onboard_patient(request)
    data = json.loads(response.body)

    assert response.status_code == 400
    assert "required" in data["error"]


@pytest.mark.anyio
async def test_onboard_patient_invalid_json():
    """Invalid JSON body returns 400."""
    request = FakeRequest(None)  # will raise on .json()
    response = await api_onboard_patient(request)
    data = json.loads(response.body)

    assert response.status_code == 400
    assert "Invalid JSON" in data["error"]


# ── POST /api/internal/onboarding-status ──────────────


@pytest.mark.anyio
async def test_onboarding_status_returns_unknown():
    """Placeholder endpoint returns status: unknown."""
    request = FakeRequest({"phone": "+421900111222"})
    response = await api_onboarding_status(request)
    data = json.loads(response.body)

    assert response.status_code == 200
    assert data["status"] == "unknown"
    assert data["phone"] == "+421900111222"


@pytest.mark.anyio
async def test_onboarding_status_missing_phone():
    """Missing phone returns 400."""
    request = FakeRequest({"phone": ""})
    response = await api_onboarding_status(request)
    data = json.loads(response.body)

    assert response.status_code == 400
    assert "required" in data["error"]


@pytest.mark.anyio
async def test_onboarding_status_invalid_json():
    """Invalid JSON body returns 400."""
    request = FakeRequest(None)
    response = await api_onboarding_status(request)
    data = json.loads(response.body)

    assert response.status_code == 400
    assert "Invalid JSON" in data["error"]
