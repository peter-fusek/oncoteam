"""Tests for onboarding API endpoints (#138)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from oncoteam.dashboard_api import (
    _approved_phones,
    api_approve_user,
    api_onboard_patient,
    api_onboarding_status,
    api_whatsapp_media,
)


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
    """Unapproved phone returns status: unknown."""
    request = FakeRequest({"phone": "+421900111222"})
    response = await api_onboarding_status(request)
    data = json.loads(response.body)

    assert response.status_code == 200
    assert data["status"] == "unknown"
    assert data["phone"] == "+421900111222"
    assert data["approved"] is False


@pytest.mark.anyio
async def test_onboarding_status_returns_approved():
    """Approved phone returns status: approved."""
    _approved_phones.add("+421900111222")
    request = FakeRequest({"phone": "+421900111222"})
    response = await api_onboarding_status(request)
    data = json.loads(response.body)

    assert response.status_code == 200
    assert data["status"] == "approved"
    assert data["approved"] is True


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


# ── POST /api/internal/approve-user ────────────────


@pytest.fixture(autouse=True)
def _clear_approved_phones():
    """Clear approved phones set between tests."""
    import oncoteam.dashboard_api as _mod

    _approved_phones.clear()
    _mod._approved_phones_loaded = False
    yield
    _approved_phones.clear()
    _mod._approved_phones_loaded = False


@pytest.mark.anyio
@patch("oncoteam.dashboard_api._persist_approved_phones", new_callable=AsyncMock)
async def test_approve_user_success(mock_persist):
    """Approve a phone number successfully and persist to oncofiles."""
    request = FakeRequest({"phone": "+421900111222"})
    response = await api_approve_user(request)
    data = json.loads(response.body)

    assert response.status_code == 200
    assert data["status"] == "approved"
    assert data["phone"] == "+421900111222"

    # Verify the phone is now in the approved set
    from oncoteam.dashboard_api import is_phone_approved

    assert is_phone_approved("+421900111222") is True


@pytest.mark.anyio
async def test_approve_user_missing_phone():
    """Missing phone returns 400."""
    request = FakeRequest({"phone": ""})
    response = await api_approve_user(request)
    data = json.loads(response.body)

    assert response.status_code == 400
    assert "required" in data["error"]


@pytest.mark.anyio
async def test_approve_user_invalid_json():
    """Invalid JSON body returns 400."""
    request = FakeRequest(None)
    response = await api_approve_user(request)
    data = json.loads(response.body)

    assert response.status_code == 400
    assert "Invalid JSON" in data["error"]


@pytest.mark.anyio
@patch("oncoteam.dashboard_api._persist_approved_phones", new_callable=AsyncMock)
async def test_approve_user_idempotent(mock_persist):
    """Approving the same phone twice works without error."""
    request1 = FakeRequest({"phone": "+421900111222"})
    await api_approve_user(request1)

    request2 = FakeRequest({"phone": "+421900111222"})
    response = await api_approve_user(request2)
    data = json.loads(response.body)

    assert response.status_code == 200
    assert data["status"] == "approved"


# ── POST /api/internal/whatsapp-media ─────────────────


@pytest.mark.anyio
@patch("oncoteam.dashboard_api.oncofiles_client.enhance_document_via_mcp", new_callable=AsyncMock)
@patch("oncoteam.dashboard_api.oncofiles_client.upload_document_via_mcp", new_callable=AsyncMock)
@patch("oncoteam.dashboard_api._check_fup_ai_query", return_value=True)
async def test_whatsapp_media_success(mock_fup, mock_upload, mock_enhance):
    """Upload + enhance succeeds, returns document_id and summary."""
    mock_upload.return_value = {"document_id": "42", "filename": "test.jpg"}
    mock_enhance.return_value = {"summary": "Lab results: WBC 5.2, HGB 12.1"}

    request = FakeRequest(
        {
            "media_base64": "aGVsbG8=",
            "content_type": "image/jpeg",
            "filename": "whatsapp_20260324_120000.jpg",
            "phone": "+421900111222",
            "patient_id": "q1b",
        }
    )
    response = await api_whatsapp_media(request)
    data = json.loads(response.body)

    assert response.status_code == 200
    assert data["status"] == "ok"
    assert data["document_id"] == "42"
    assert "Lab results" in data["summary"]

    mock_upload.assert_called_once_with(
        content_base64="aGVsbG8=",
        filename="whatsapp_20260324_120000.jpg",
        content_type="image/jpeg",
        patient_id="q1b",
    )
    mock_enhance.assert_called_once_with("42")


@pytest.mark.anyio
@patch("oncoteam.dashboard_api._check_fup_ai_query", return_value=False)
async def test_whatsapp_media_fup_exceeded(mock_fup):
    """429 when monthly FUP limit is exceeded."""
    request = FakeRequest(
        {
            "media_base64": "aGVsbG8=",
            "content_type": "image/jpeg",
            "filename": "test.jpg",
            "phone": "+421900111222",
            "patient_id": "",
        }
    )
    response = await api_whatsapp_media(request)
    data = json.loads(response.body)

    assert response.status_code == 429
    assert "limit" in data["error"].lower()


@pytest.mark.anyio
async def test_whatsapp_media_missing_fields():
    """Missing required fields returns 400."""
    request = FakeRequest({"media_base64": "", "content_type": "", "filename": ""})
    response = await api_whatsapp_media(request)
    data = json.loads(response.body)

    assert response.status_code == 400
    assert "required" in data["error"]


@pytest.mark.anyio
async def test_whatsapp_media_invalid_json():
    """Invalid JSON body returns 400."""
    request = FakeRequest(None)
    response = await api_whatsapp_media(request)
    data = json.loads(response.body)

    assert response.status_code == 400
    assert "Invalid JSON" in data["error"]


@pytest.mark.anyio
@patch("oncoteam.dashboard_api.oncofiles_client.upload_document_via_mcp", new_callable=AsyncMock)
@patch("oncoteam.dashboard_api._check_fup_ai_query", return_value=True)
async def test_whatsapp_media_upload_failure(mock_fup, mock_upload):
    """502 when upload to oncofiles fails."""
    mock_upload.side_effect = ConnectionError("oncofiles unreachable")

    request = FakeRequest(
        {
            "media_base64": "aGVsbG8=",
            "content_type": "application/pdf",
            "filename": "report.pdf",
            "phone": "+421900111222",
            "patient_id": "",
        }
    )
    response = await api_whatsapp_media(request)
    data = json.loads(response.body)

    assert response.status_code == 502
    assert "Failed to upload" in data["error"]


# ── load_approved_phones / persist ──────────────────


@pytest.mark.anyio
@patch("oncoteam.dashboard_api.oncofiles_client.get_agent_state", new_callable=AsyncMock)
async def test_load_approved_phones_from_oncofiles(mock_get):
    """Load approved phones from oncofiles agent_state."""
    from oncoteam.dashboard_api import load_approved_phones

    mock_get.return_value = {"value": {"phones": ["+421900111222", "+421900333444"]}}
    await load_approved_phones()

    from oncoteam.dashboard_api import is_phone_approved

    assert is_phone_approved("+421900111222") is True
    assert is_phone_approved("+421900333444") is True
    assert is_phone_approved("+421900999999") is False


@pytest.mark.anyio
@patch("oncoteam.dashboard_api.oncofiles_client.get_agent_state", new_callable=AsyncMock)
async def test_load_approved_phones_oncofiles_down(mock_get):
    """Load gracefully handles oncofiles being down."""
    from oncoteam.dashboard_api import load_approved_phones

    mock_get.side_effect = ConnectionError("oncofiles unreachable")
    await load_approved_phones()  # Should not raise

    from oncoteam.dashboard_api import is_phone_approved

    assert is_phone_approved("+421900111222") is False


# ── Per-patient FUP counters ─────────────────────────


def test_fup_per_patient_isolation():
    """FUP counters track per-patient, not globally."""
    from oncoteam.dashboard_api import (
        _check_fup_ai_query,
        _fup_ai_queries,
        _get_fup_status,
    )

    _fup_ai_queries.clear()

    # Patient A and patient B each get their own counter
    assert _check_fup_ai_query("patient_a") is True
    assert _check_fup_ai_query("patient_b") is True

    status = _get_fup_status()
    assert "patient_a" in status["ai_queries"]["per_patient"]
    assert "patient_b" in status["ai_queries"]["per_patient"]
    assert status["ai_queries"]["used"] == 2

    _fup_ai_queries.clear()
