"""Tests for general health protocol module."""

from __future__ import annotations

from oncoteam.general_health_protocol import (
    GENERAL_HEALTH_LAB_RANGES,
    GENERAL_HEALTH_SYSTEM_PROMPT,
    PREVENTIVE_SCREENING_SCHEDULE,
    resolve_general_health_protocol,
)


class TestLabRanges:
    def test_has_metabolic_markers(self):
        assert "glucose_fasting" in GENERAL_HEALTH_LAB_RANGES
        assert "HbA1c" in GENERAL_HEALTH_LAB_RANGES

    def test_has_lipid_markers(self):
        assert "cholesterol_total" in GENERAL_HEALTH_LAB_RANGES
        assert "HDL" in GENERAL_HEALTH_LAB_RANGES
        assert "LDL" in GENERAL_HEALTH_LAB_RANGES
        assert "triglycerides" in GENERAL_HEALTH_LAB_RANGES

    def test_has_thyroid(self):
        assert "TSH" in GENERAL_HEALTH_LAB_RANGES

    def test_has_renal(self):
        assert "creatinine" in GENERAL_HEALTH_LAB_RANGES
        assert "eGFR" in GENERAL_HEALTH_LAB_RANGES

    def test_no_oncology_markers(self):
        # General health should not have chemo-specific thresholds
        assert "ANC" not in GENERAL_HEALTH_LAB_RANGES

    def test_ranges_have_units(self):
        for key, value in GENERAL_HEALTH_LAB_RANGES.items():
            assert "unit" in value, f"{key} missing unit"


class TestScreeningSchedule:
    def test_has_entries(self):
        assert len(PREVENTIVE_SCREENING_SCHEDULE) >= 10

    def test_entries_have_required_fields(self):
        for entry in PREVENTIVE_SCREENING_SCHEDULE:
            assert "screening" in entry
            assert "interval" in entry


class TestSystemPrompt:
    def test_contains_general_health_content(self):
        assert "EU/WHO/ESC" in GENERAL_HEALTH_SYSTEM_PROMPT
        assert "glucose" in GENERAL_HEALTH_SYSTEM_PROMPT

    def test_no_oncology_content(self):
        assert "mFOLFOX6" not in GENERAL_HEALTH_SYSTEM_PROMPT
        assert "NCCN" not in GENERAL_HEALTH_SYSTEM_PROMPT
        assert "SII" not in GENERAL_HEALTH_SYSTEM_PROMPT

    def test_has_do_not_rules(self):
        assert "DO NOT" in GENERAL_HEALTH_SYSTEM_PROMPT
        assert "pre-cycle" in GENERAL_HEALTH_SYSTEM_PROMPT


class TestResolveProtocol:
    def test_returns_dict(self):
        result = resolve_general_health_protocol("en")
        assert isinstance(result, dict)

    def test_has_protocol_type(self):
        result = resolve_general_health_protocol("en")
        assert result["protocol_type"] == "general_health"

    def test_has_lab_ranges(self):
        result = resolve_general_health_protocol("en")
        assert "lab_ranges" in result
        assert "glucose_fasting" in result["lab_ranges"]

    def test_has_screening_schedule(self):
        result = resolve_general_health_protocol("en")
        assert "screening_schedule" in result
        assert len(result["screening_schedule"]) >= 10

    def test_oncology_sections_empty(self):
        result = resolve_general_health_protocol("en")
        assert result["dose_modifications"] == {}
        assert result["milestones"] == []
        assert result["watched_trials"] == []

    def test_bilingual_sk(self):
        result = resolve_general_health_protocol("sk")
        # Slovak version should resolve L() dicts
        assert isinstance(result, dict)
        assert result["protocol_type"] == "general_health"

    def test_returns_deep_copy(self):
        r1 = resolve_general_health_protocol("en")
        r2 = resolve_general_health_protocol("en")
        assert r1 is not r2  # deep copy, not same object
