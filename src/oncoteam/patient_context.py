from __future__ import annotations

from datetime import date

from .models import PatientProfile

PATIENT = PatientProfile(
    name="Erika Fusekova",
    diagnosis_code="C18.7",
    diagnosis_description="Malignant neoplasm of sigmoid colon",
    tumor_site="Sigmoid colon",
    diagnosis_date=date(2025, 12, 1),
    biomarkers={"HER2": "negative"},
    treatment_regimen="FOLFOX",
    hospitals=["NOU (Narodny onkologicky ustav)", "Bory Nemocnica"],
    notes="Colorectal cancer, FOLFOX chemotherapy protocol.",
)

# Curated PubMed search terms for Erika's case
RESEARCH_TERMS: list[str] = [
    "colorectal cancer FOLFOX",
    "sigmoid colon adenocarcinoma chemotherapy",
    "FOLFOX oxaliplatin side effects management",
    "colorectal cancer HER2 negative treatment",
    "FOLFOX neurotoxicity prevention",
    "colorectal cancer immunotherapy advances",
    "stage III colorectal cancer adjuvant chemotherapy",
]


def get_patient_profile_text() -> str:
    """Return formatted patient profile for MCP resource."""
    p = PATIENT
    biomarkers = ", ".join(f"{k}: {v}" for k, v in p.biomarkers.items())
    hospitals = ", ".join(p.hospitals)
    return (
        f"# Patient Profile\n\n"
        f"- **Name**: {p.name}\n"
        f"- **Diagnosis**: {p.diagnosis_description} ({p.diagnosis_code})\n"
        f"- **Tumor site**: {p.tumor_site}\n"
        f"- **Biomarkers**: {biomarkers}\n"
        f"- **Treatment**: {p.treatment_regimen}\n"
        f"- **Hospitals**: {hospitals}\n"
        f"- **Notes**: {p.notes}\n"
    )


def get_research_terms_text() -> str:
    """Return formatted research terms for MCP resource."""
    terms = "\n".join(f"- {t}" for t in RESEARCH_TERMS)
    return f"# Research Search Terms\n\nCurated PubMed queries for this case:\n\n{terms}\n"
