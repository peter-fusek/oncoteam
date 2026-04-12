from datetime import date
from unittest.mock import AsyncMock, patch

import pytest

from oncoteam.models import PatientProfile
from oncoteam.patient_context import (
    _GENETIC_SEARCH_TERMS,
    PATIENT,
    RESEARCH_TERMS,
    _extract_text,
    _update_biomarkers,
    get_context_tags,
    get_genetic_profile,
    get_patient_profile_text,
    get_research_terms_text,
)


class TestPatientContext:
    def test_patient_is_valid_profile(self):
        assert isinstance(PATIENT, PatientProfile)
        assert PATIENT.name == "Erika F."
        assert PATIENT.diagnosis_code == "C18.7"

    def test_patient_has_treatment(self):
        assert "FOLFOX" in PATIENT.treatment_regimen
        assert "NOU" in PATIENT.hospitals[0]

    def test_patient_diagnosis_date(self):
        assert PATIENT.diagnosis_date == date(2025, 12, 1)

    def test_patient_biomarkers(self):
        assert "negative" in PATIENT.biomarkers["HER2"]
        assert "G12S" in PATIENT.biomarkers["KRAS"]
        assert PATIENT.biomarkers["NRAS"] == "wild-type"
        assert PATIENT.biomarkers["BRAF_V600E"] == "wild-type"
        assert PATIENT.biomarkers["anti_EGFR_eligible"] is False

    def test_patient_extended_fields(self):
        assert PATIENT.staging
        assert PATIENT.histology
        assert PATIENT.tumor_laterality == "left-sided"
        assert len(PATIENT.metastases) > 5
        assert len(PATIENT.excluded_therapies) > 0

    def test_research_terms_not_empty(self):
        assert len(RESEARCH_TERMS) > 0
        assert any("KRAS" in t for t in RESEARCH_TERMS)
        assert any("FOLFOX" in t for t in RESEARCH_TERMS)

    def test_profile_text_contains_key_info(self):
        text = get_patient_profile_text()
        assert "Erika F." in text
        assert "C18.7" in text
        assert "FOLFOX" in text
        assert "HER2" in text
        assert "KRAS" in text
        assert "Staging" in text
        assert "Excluded therapies" in text

    def test_research_terms_text(self):
        text = get_research_terms_text()
        assert "Research Search Terms" in text
        assert "kras" in text.lower()


class TestSecondPatient:
    """Tests for the e5g (Peter F.) non-oncology patient."""

    def test_e5g_in_registry(self):
        from oncoteam.patient_context import list_patient_ids

        ids = list_patient_ids()
        assert "e5g" in ids
        assert "q1b" in ids

    def test_e5g_profile(self):
        from oncoteam.patient_context import get_patient

        p = get_patient("e5g")
        assert p.name == "Peter F."
        assert p.diagnosis_code == "Z00.0"
        assert p.biomarkers == {}
        assert p.excluded_therapies == {}

    def test_e5g_agent_whitelist(self):
        from oncoteam.patient_context import get_patient

        p = get_patient("e5g")
        assert "lab_sync" in p.agent_whitelist
        assert "weekly_briefing" in p.agent_whitelist
        assert "pre_cycle_check" not in p.agent_whitelist

    def test_e5g_biomarker_rules_are_safe(self):
        from oncoteam.patient_context import build_biomarker_rules, get_patient

        p = get_patient("e5g")
        rules = build_biomarker_rules(p)
        # Non-oncology patient: no anti-EGFR exclusion, no KRAS rules
        assert "anti-EGFR" not in rules
        assert "G12S" not in rules

    def test_e5g_no_cross_contamination(self):
        """Erika's biomarker rules must not apply to e5g."""
        from oncoteam.patient_context import build_biomarker_rules, get_patient

        erika = get_patient("q1b")
        e5g = get_patient("e5g")
        erika_rules = build_biomarker_rules(erika)
        e5g_rules = build_biomarker_rules(e5g)
        assert "KRAS" in erika_rules
        assert "KRAS" not in e5g_rules

    def test_is_general_health_patient_z_code(self):
        from oncoteam.patient_context import get_patient, is_general_health_patient

        assert is_general_health_patient(get_patient("e5g")) is True

    def test_is_general_health_patient_oncology(self):
        from oncoteam.patient_context import get_patient, is_general_health_patient

        assert is_general_health_patient(get_patient("q1b")) is False

    def test_is_general_health_patient_empty_regimen(self):
        from oncoteam.patient_context import is_general_health_patient

        p = PatientProfile(
            name="Test",
            diagnosis_code="C50",
            diagnosis_description="Breast cancer",
            tumor_site="breast",
            treatment_regimen="",
        )
        # Empty regimen triggers general health path (per CLAUDE.md spec)
        assert is_general_health_patient(p) is True


class TestGeneticProfile:
    @pytest.mark.asyncio
    async def test_genetic_profile_returns_static_when_oncofiles_unavailable(self):
        with patch("oncoteam.patient_context.oncofiles_client") as mock:
            mock.search_documents = AsyncMock(side_effect=Exception("offline"))
            profile = await get_genetic_profile()
        # Should have all static biomarkers from PATIENT
        assert "G12S" in profile["KRAS"]
        assert "negative" in profile["HER2"]

    @pytest.mark.asyncio
    async def test_genetic_profile_enriches_from_documents(self):
        mock_docs = {"documents": [{"id": 42}]}
        mock_content = {"ocr_text": "TMB: 8.5 mut/Mb"}
        with patch("oncoteam.patient_context.oncofiles_client") as mock:
            mock.search_documents = AsyncMock(return_value=mock_docs)
            mock.view_document = AsyncMock(return_value=mock_content)
            profile = await get_genetic_profile()
        # Static biomarkers preserved, new ones added
        assert "G12S" in profile["KRAS"]
        assert "8.5" in profile["TMB"]

    @pytest.mark.asyncio
    async def test_genetic_profile_does_not_overwrite_existing(self):
        mock_docs = {"documents": [{"id": 1}]}
        mock_content = {"ocr_text": "HER2: positive\nKRAS: wild-type"}
        with patch("oncoteam.patient_context.oncofiles_client") as mock:
            mock.search_documents = AsyncMock(return_value=mock_docs)
            mock.view_document = AsyncMock(return_value=mock_content)
            profile = await get_genetic_profile()
        # Existing values must not be overwritten
        assert "negative" in profile["HER2"]
        assert "G12S" in profile["KRAS"]

    @pytest.mark.asyncio
    async def test_genetic_profile_searches_multiple_terms(self):
        with patch("oncoteam.patient_context.oncofiles_client") as mock:
            mock.search_documents = AsyncMock(return_value={"documents": []})
            await get_genetic_profile()
        assert mock.search_documents.call_count == len(_GENETIC_SEARCH_TERMS)
        # Verify no category filter is used
        for call in mock.search_documents.call_args_list:
            assert "category" not in call.kwargs

    @pytest.mark.asyncio
    async def test_genetic_profile_deduplicates_documents(self):
        mock_docs = {"documents": [{"id": 42}]}
        mock_content = {"ocr_text": "KRAS: wild-type"}
        with patch("oncoteam.patient_context.oncofiles_client") as mock:
            mock.search_documents = AsyncMock(return_value=mock_docs)
            mock.view_document = AsyncMock(return_value=mock_content)
            await get_genetic_profile()
        # Doc 42 appears in every search result but should be viewed only once
        mock.view_document.assert_called_once_with("42", token=None)


class TestContextTags:
    def test_includes_treatment_regimen(self):
        tags = get_context_tags()
        assert any("FOLFOX" in t for t in tags)

    def test_includes_tumor_site(self):
        tags = get_context_tags()
        assert "sigmoid_colon" in tags

    def test_includes_diagnosis_term(self):
        tags = get_context_tags()
        # diagnosis_description now says "AdenoCa colon sigmoideum"
        assert any(t in tags for t in ["colorectal", "colon", "rectal", "sigmoid"])

    def test_includes_biomarkers(self):
        tags = get_context_tags()
        assert any("HER2" in t for t in tags)
        assert any("KRAS" in t for t in tags)

    def test_returns_list(self):
        tags = get_context_tags()
        assert isinstance(tags, list)
        assert len(tags) >= 3


class TestBiomarkerExtraction:
    def test_extract_text_from_dict(self):
        assert _extract_text({"ocr_text": "hello"}) == "hello"
        assert _extract_text({"content": {"ocr_text": "nested"}}) == "nested"
        assert _extract_text("plain") == "plain"

    def test_update_biomarkers(self):
        profile = {}
        _update_biomarkers(profile, "KRAS: mutant, TMB: 12.3 mut/Mb")
        assert profile["KRAS"] == "mutant"
        assert "12.3" in profile["TMB"]

    def test_update_biomarkers_skip_existing(self):
        profile = {"KRAS": "wild-type"}
        _update_biomarkers(profile, "KRAS: mutant")
        assert profile["KRAS"] == "wild-type"
