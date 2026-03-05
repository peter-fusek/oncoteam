from datetime import date

from oncoteam.models import PatientProfile
from oncoteam.patient_context import (
    PATIENT,
    RESEARCH_TERMS,
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
