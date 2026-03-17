"""Tests for the get_clinical_protocol MCP tool."""

from __future__ import annotations

import json

import pytest

from oncoteam.clinical_protocol import PROTOCOL_SECTIONS, resolve_protocol


class TestResolveProtocol:
    def test_returns_all_sections(self):
        protocol = resolve_protocol("en")
        for section in PROTOCOL_SECTIONS:
            assert section in protocol, f"Missing section: {section}"

    def test_health_direction_included(self):
        protocol = resolve_protocol("en")
        assert "health_direction" in protocol
        assert protocol["health_direction"]["CEA"] == "lower_is_better"

    def test_lang_en_resolves_strings(self):
        protocol = resolve_protocol("en")
        # Dose mods should be plain strings in EN
        assert isinstance(protocol["dose_modifications"]["neuropathy_grade_2"], str)
        assert "75%" in protocol["dose_modifications"]["neuropathy_grade_2"]

    def test_lang_sk_resolves_strings(self):
        protocol = resolve_protocol("sk")
        rule = protocol["dose_modifications"]["neuropathy_grade_2"]
        assert isinstance(rule, str)
        assert "75%" in rule

    def test_all_sections_json_serializable(self):
        """Every section must be JSON-serializable (the MCP tool calls json.dumps)."""
        protocol = resolve_protocol("en")
        dumped = json.dumps(protocol, default=str)
        loaded = json.loads(dumped)
        assert set(loaded.keys()) == set(protocol.keys())

    def test_current_cycle_present(self):
        protocol = resolve_protocol("en")
        assert "current_cycle" in protocol


class TestProtocolSections:
    def test_sections_set_matches_resolve_keys(self):
        """PROTOCOL_SECTIONS must list every key that resolve_protocol returns
        (except current_cycle which is metadata, not a section)."""
        protocol = resolve_protocol("en")
        protocol_keys = {k for k in protocol if k != "current_cycle"}
        assert protocol_keys == PROTOCOL_SECTIONS


class TestGetClinicalProtocolTool:
    """Test the tool function directly (no MCP transport needed)."""

    @pytest.mark.asyncio
    async def test_full_protocol(self):
        from oncoteam.server import get_clinical_protocol

        result = await get_clinical_protocol()
        data = json.loads(result)
        assert "lab_thresholds" in data
        assert "safety_flags" in data
        assert "milestones" in data

    @pytest.mark.asyncio
    async def test_single_section(self):
        from oncoteam.server import get_clinical_protocol

        result = await get_clinical_protocol(section="lab_thresholds")
        data = json.loads(result)
        assert "lab_thresholds" in data
        assert len(data) == 1
        assert "ANC" in data["lab_thresholds"]

    @pytest.mark.asyncio
    async def test_unknown_section_returns_error(self):
        from oncoteam.server import get_clinical_protocol

        result = await get_clinical_protocol(section="nonexistent")
        data = json.loads(result)
        assert "error" in data
        assert "nonexistent" in data["error"]
        assert "available" in data

    @pytest.mark.asyncio
    async def test_lang_sk(self):
        from oncoteam.server import get_clinical_protocol

        result = await get_clinical_protocol(section="dose_modifications", lang="sk")
        data = json.loads(result)
        rule = data["dose_modifications"]["neuropathy_grade_4"]
        # Slovak text
        assert "UKON" in rule  # UKONČIŤ

    @pytest.mark.asyncio
    async def test_lang_en(self):
        from oncoteam.server import get_clinical_protocol

        result = await get_clinical_protocol(section="dose_modifications", lang="en")
        data = json.loads(result)
        rule = data["dose_modifications"]["neuropathy_grade_4"]
        assert "DISCONTINUE" in rule

    @pytest.mark.asyncio
    async def test_all_sections_individually(self):
        from oncoteam.server import get_clinical_protocol

        for section in PROTOCOL_SECTIONS:
            result = await get_clinical_protocol(section=section)
            data = json.loads(result)
            assert section in data, f"Section {section} not in response"
