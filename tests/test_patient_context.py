from datetime import date
from unittest.mock import AsyncMock, patch

import pytest

from oncoteam.models import PatientProfile
from oncoteam.patient_context import (
    PATIENT,
    RESEARCH_TERMS,
    _extract_text,
    _update_biomarkers,
    get_genetic_profile,
    get_patient_profile_text,
    get_research_terms_text,
)


class TestPatientContext:
    def test_patient_is_valid_profile(self):
        assert isinstance(PATIENT, PatientProfile)
        assert PATIENT.name == "Erika Fusekova"
        assert PATIENT.diagnosis_code == "C18.7"

    def test_patient_has_treatment(self):
        assert PATIENT.treatment_regimen == "FOLFOX"
        assert "NOU" in PATIENT.hospitals[0]

    def test_patient_diagnosis_date(self):
        assert PATIENT.diagnosis_date == date(2025, 12, 1)

    def test_patient_biomarkers(self):
        assert PATIENT.biomarkers["HER2"] == "negative"

    def test_research_terms_not_empty(self):
        assert len(RESEARCH_TERMS) > 0
        assert any("FOLFOX" in t for t in RESEARCH_TERMS)

    def test_profile_text_contains_key_info(self):
        text = get_patient_profile_text()
        assert "Erika Fusekova" in text
        assert "C18.7" in text
        assert "FOLFOX" in text
        assert "HER2" in text

    def test_research_terms_text(self):
        text = get_research_terms_text()
        assert "Research Search Terms" in text
        assert "colorectal" in text.lower()


class TestGeneticProfile:
    @pytest.mark.asyncio
    async def test_genetic_profile_returns_static_when_oncofiles_unavailable(self):
        with patch("oncoteam.patient_context.oncofiles_client") as mock:
            mock.search_documents = AsyncMock(side_effect=Exception("offline"))
            profile = await get_genetic_profile()
        assert profile == {"HER2": "negative"}

    @pytest.mark.asyncio
    async def test_genetic_profile_enriches_from_documents(self):
        mock_docs = {"documents": [{"id": 42}]}
        mock_content = {"ocr_text": "KRAS: wild-type\nBRAF: V600E\nMSI: MSS"}
        with patch("oncoteam.patient_context.oncofiles_client") as mock:
            mock.search_documents = AsyncMock(return_value=mock_docs)
            mock.view_document = AsyncMock(return_value=mock_content)
            profile = await get_genetic_profile()
        assert profile["HER2"] == "negative"
        assert profile["KRAS"] == "wild-type"
        assert profile["BRAF"] == "v600e"
        assert profile["MSI"] == "mss"

    @pytest.mark.asyncio
    async def test_genetic_profile_does_not_overwrite_existing(self):
        mock_docs = {"documents": [{"id": 1}]}
        mock_content = {"ocr_text": "HER2: positive"}
        with patch("oncoteam.patient_context.oncofiles_client") as mock:
            mock.search_documents = AsyncMock(return_value=mock_docs)
            mock.view_document = AsyncMock(return_value=mock_content)
            profile = await get_genetic_profile()
        assert profile["HER2"] == "negative"


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
