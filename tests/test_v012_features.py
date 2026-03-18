"""Tests for v0.12.0 features: source attribution, lab directions,
protocol last values, patient context."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from oncoteam.clinical_protocol import (
    LAB_REFERENCE_RANGES,
    PARAMETER_HEALTH_DIRECTION,
)
from oncoteam.dashboard_api import _protocol_cache, api_labs, api_protocol
from oncoteam.models import PatientProfile
from oncoteam.patient_context import PATIENT

# ── Helpers ──────────────────────────────────────


class FakeRequest:
    """Minimal Starlette Request stub."""

    def __init__(self, method: str = "GET", query: str = "", body: bytes = b""):
        from starlette.datastructures import QueryParams

        self.method = method
        self.query_params = QueryParams(query)
        self._body = body

    async def body(self) -> bytes:
        return self._body


# ── Source Attribution in System Prompt (Session 2B) ──


class TestSourceAttributionPrompt:
    def test_system_prompt_contains_source_attribution(self):
        from oncoteam.server import mcp

        instructions = mcp.instructions or ""
        assert "SOURCE ATTRIBUTION RULES" in instructions

    def test_system_prompt_contains_gdrive_url(self):
        from oncoteam.server import mcp

        instructions = mcp.instructions or ""
        assert "gdrive_url" in instructions

    def test_system_prompt_contains_source_pending(self):
        from oncoteam.server import mcp

        instructions = mcp.instructions or ""
        assert "[source pending]" in instructions


# ── New Lab Reference Ranges (Session 2C) ──


class TestNewReferenceRanges:
    def test_wbc_exists(self):
        assert "WBC" in LAB_REFERENCE_RANGES
        assert LAB_REFERENCE_RANGES["WBC"]["min"] == 4.5
        assert LAB_REFERENCE_RANGES["WBC"]["max"] == 11.0

    def test_abs_lymph_exists(self):
        assert "ABS_LYMPH" in LAB_REFERENCE_RANGES
        assert LAB_REFERENCE_RANGES["ABS_LYMPH"]["min"] == 1000

    def test_sii_exists(self):
        assert "SII" in LAB_REFERENCE_RANGES
        assert LAB_REFERENCE_RANGES["SII"]["max"] == 1800

    def test_ne_ly_ratio_exists(self):
        assert "NE_LY_RATIO" in LAB_REFERENCE_RANGES
        assert LAB_REFERENCE_RANGES["NE_LY_RATIO"]["max"] == 3.0

    def test_bilirubin_already_exists(self):
        assert "bilirubin" in LAB_REFERENCE_RANGES


# ── PARAMETER_HEALTH_DIRECTION (Session 2C) ──


class TestParameterHealthDirection:
    def test_cea_lower_is_better(self):
        assert PARAMETER_HEALTH_DIRECTION["CEA"] == "lower_is_better"

    def test_anc_higher_is_better(self):
        assert PARAMETER_HEALTH_DIRECTION["ANC"] == "higher_is_better"

    def test_plt_in_range(self):
        assert PARAMETER_HEALTH_DIRECTION["PLT"] == "in_range"

    def test_sii_lower_is_better(self):
        assert PARAMETER_HEALTH_DIRECTION["SII"] == "lower_is_better"

    def test_ne_ly_ratio_lower_is_better(self):
        assert PARAMETER_HEALTH_DIRECTION["NE_LY_RATIO"] == "lower_is_better"

    def test_all_reference_params_have_health_direction(self):
        for param in LAB_REFERENCE_RANGES:
            if param in ("CA_19_9",):  # mapped differently
                continue
            assert param in PARAMETER_HEALTH_DIRECTION, f"{param} missing health direction"


# ── Lab Directions (Session 2C) ──


MOCK_LABS_FOR_DIRECTION = [
    {
        "id": 10,
        "event_date": "2026-03-01",
        "event_type": "lab_result",
        "title": "Lab results",
        "notes": "",
        "metadata": {"CEA": 8.0, "ANC": 2500, "PLT": 180000},
    },
    {
        "id": 11,
        "event_date": "2026-02-15",
        "event_type": "lab_result",
        "title": "Lab results",
        "notes": "",
        "metadata": {"CEA": 12.5, "ANC": 2100, "PLT": 180000},
    },
]


@pytest.mark.anyio
@patch(
    "oncoteam.dashboard_api.oncofiles_client.list_treatment_events",
    new_callable=AsyncMock,
)
async def test_api_labs_returns_directions(mock_list):
    mock_list.return_value = MOCK_LABS_FOR_DIRECTION
    request = FakeRequest("GET")
    response = await api_labs(request)
    data = json.loads(response.body)

    # First entry (newest, 2026-03-01): compared to 2026-02-15
    entry = data["entries"][0]
    assert entry["date"] == "2026-03-01"
    assert "directions" in entry
    assert entry["directions"]["CEA"] == "down"  # 8.0 < 12.5
    assert entry["directions"]["ANC"] == "up"  # 2500 > 2100
    assert entry["directions"]["PLT"] == "stable"  # 180000 == 180000


@pytest.mark.anyio
@patch(
    "oncoteam.dashboard_api.oncofiles_client.list_treatment_events",
    new_callable=AsyncMock,
)
async def test_api_labs_returns_health_directions(mock_list):
    mock_list.return_value = MOCK_LABS_FOR_DIRECTION
    request = FakeRequest("GET")
    response = await api_labs(request)
    data = json.loads(response.body)

    entry = data["entries"][0]
    assert "health_directions" in entry
    # CEA down = improving (lower_is_better)
    assert entry["health_directions"]["CEA"] == "improving"
    # ANC up = improving (higher_is_better)
    assert entry["health_directions"]["ANC"] == "improving"
    # PLT stable = stable
    assert entry["health_directions"]["PLT"] == "stable"


@pytest.mark.anyio
@patch(
    "oncoteam.dashboard_api.oncofiles_client.list_treatment_events",
    new_callable=AsyncMock,
)
async def test_api_labs_sorted_descending(mock_list):
    mock_list.return_value = MOCK_LABS_FOR_DIRECTION
    request = FakeRequest("GET")
    response = await api_labs(request)
    data = json.loads(response.body)

    assert data["entries"][0]["date"] == "2026-03-01"  # newest first
    assert data["entries"][1]["date"] == "2026-02-15"


@pytest.mark.anyio
@patch(
    "oncoteam.dashboard_api.oncofiles_client.list_treatment_events",
    new_callable=AsyncMock,
)
async def test_api_labs_oldest_entry_has_no_direction(mock_list):
    """Oldest entry has no previous to compare against."""
    mock_list.return_value = MOCK_LABS_FOR_DIRECTION
    request = FakeRequest("GET")
    response = await api_labs(request)
    data = json.loads(response.body)

    oldest = data["entries"][-1]
    assert oldest["directions"] == {}
    assert oldest["health_directions"] == {}


# ── Protocol Last Lab Values (Session 2D) ──


@pytest.fixture(autouse=True)
def _clear_protocol_cache():
    """Clear protocol response cache between tests to avoid cache poisoning."""
    _protocol_cache.clear()
    yield
    _protocol_cache.clear()


@pytest.mark.anyio
@patch(
    "oncoteam.dashboard_api.oncofiles_client.get_lab_trends_data",
    new_callable=AsyncMock,
    return_value={"values": []},
)
@patch(
    "oncoteam.dashboard_api.oncofiles_client.list_treatment_events",
    new_callable=AsyncMock,
)
async def test_api_protocol_includes_last_lab_values(mock_list, _mock_trends):
    mock_list.return_value = [
        {
            "id": 10,
            "event_date": "2026-03-01",
            "event_type": "lab_result",
            "metadata": {"ANC": 2100, "PLT": 180000},
        }
    ]
    request = FakeRequest("GET")
    response = await api_protocol(request)
    data = json.loads(response.body)

    assert "last_lab_values" in data
    assert "ANC" in data["last_lab_values"]
    assert data["last_lab_values"]["ANC"]["value"] == 2100
    assert data["last_lab_values"]["ANC"]["status"] == "safe"
    assert data["last_lab_values"]["ANC"]["sample_date"] == "2026-03-01"
    # real_values should always be present
    assert "real_values" in data
    assert "current_regimen" in data["real_values"]


@pytest.mark.anyio
@patch(
    "oncoteam.dashboard_api.oncofiles_client.get_lab_trends_data",
    new_callable=AsyncMock,
    return_value={"values": []},
)
@patch(
    "oncoteam.dashboard_api.oncofiles_client.list_treatment_events",
    new_callable=AsyncMock,
)
async def test_api_protocol_last_lab_warning_status(mock_list, _mock_trends):
    # ANC = 1700: above min (1500) but within 20% → warning
    mock_list.return_value = [
        {
            "id": 10,
            "event_date": "2026-03-01",
            "event_type": "lab_result",
            "metadata": {"ANC": 1700},
        }
    ]
    request = FakeRequest("GET")
    response = await api_protocol(request)
    data = json.loads(response.body)

    assert data["last_lab_values"]["ANC"]["status"] == "warning"


@pytest.mark.anyio
@patch(
    "oncoteam.dashboard_api.oncofiles_client.get_lab_trends_data",
    new_callable=AsyncMock,
    return_value={"values": []},
)
@patch(
    "oncoteam.dashboard_api.oncofiles_client.list_treatment_events",
    new_callable=AsyncMock,
)
async def test_api_protocol_last_lab_critical_status(mock_list, _mock_trends):
    # ANC = 800: below min (1500) → critical
    mock_list.return_value = [
        {
            "id": 10,
            "event_date": "2026-03-01",
            "event_type": "lab_result",
            "metadata": {"ANC": 800},
        }
    ]
    request = FakeRequest("GET")
    response = await api_protocol(request)
    data = json.loads(response.body)

    assert data["last_lab_values"]["ANC"]["status"] == "critical"


@pytest.mark.anyio
@patch(
    "oncoteam.dashboard_api.oncofiles_client.get_lab_trends_data",
    new_callable=AsyncMock,
    return_value={"values": []},
)
@patch(
    "oncoteam.dashboard_api.oncofiles_client.list_treatment_events",
    new_callable=AsyncMock,
)
async def test_api_protocol_last_lab_empty_when_no_events(mock_list, _mock_trends):
    mock_list.return_value = []
    request = FakeRequest("GET")
    response = await api_protocol(request)
    data = json.loads(response.body)

    assert data["last_lab_values"] == {}


@pytest.mark.anyio
@patch(
    "oncoteam.dashboard_api.oncofiles_client.get_lab_trends_data",
    new_callable=AsyncMock,
    return_value={"values": []},
)
@patch(
    "oncoteam.dashboard_api.oncofiles_client.list_treatment_events",
    new_callable=AsyncMock,
)
async def test_api_protocol_last_lab_handles_error(mock_list, _mock_trends):
    mock_list.side_effect = Exception("connection refused")
    request = FakeRequest("GET")
    response = await api_protocol(request)
    data = json.loads(response.body)

    # Should still return protocol data, just with empty last_lab_values
    assert "lab_thresholds" in data
    assert data["last_lab_values"] == {}


# ── Patient Context (Session 3B) ──


class TestPatientNewFields:
    def test_patient_has_patient_ids(self):
        assert PATIENT.patient_ids
        assert "rodne_cislo" in PATIENT.patient_ids

    def test_patient_has_active_therapies(self):
        assert PATIENT.active_therapies
        assert len(PATIENT.active_therapies) == 3

    def test_active_therapy_has_drugs(self):
        folfox = PATIENT.active_therapies[0]
        assert folfox["name"] == "mFOLFOX6 90%"
        assert len(folfox["drugs"]) == 3
        assert folfox["drugs"][0]["name"] == "Oxaliplatin"

    def test_planned_therapy_has_warning(self):
        bev = PATIENT.active_therapies[2]
        assert bev["status"] == "planned"
        assert "HIGH RISK" in bev["warning"]

    def test_patient_profile_model_accepts_new_fields(self):
        p = PatientProfile(
            name="Test",
            diagnosis_code="C18.0",
            diagnosis_description="Test",
            tumor_site="Test",
            treatment_regimen="Test",
            patient_ids={"id1": "val1"},
            active_therapies=[{"name": "Test", "drugs": [], "status": "active"}],
        )
        assert p.patient_ids["id1"] == "val1"
        assert len(p.active_therapies) == 1

    def test_patient_profile_new_fields_optional(self):
        p = PatientProfile(
            name="Test",
            diagnosis_code="C18.0",
            diagnosis_description="Test",
            tumor_site="Test",
            treatment_regimen="Test",
        )
        assert p.patient_ids == {}
        assert p.active_therapies == []


class TestPatientLocalization:
    def test_localized_patient_has_active_therapies(self):
        from oncoteam.patient_context import get_patient_localized

        data = get_patient_localized("en")
        assert "active_therapies" in data

    def test_localized_patient_has_patient_ids(self):
        from oncoteam.patient_context import get_patient_localized

        data = get_patient_localized("sk")
        assert "patient_ids" in data
