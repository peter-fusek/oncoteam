from __future__ import annotations

import contextlib
import re
from datetime import date

from . import oncofiles_client
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


def get_context_tags() -> list[str]:
    """Derive research tags from patient context."""
    tags = []
    if PATIENT.treatment_regimen:
        tags.append(PATIENT.treatment_regimen)
    if PATIENT.tumor_site:
        tags.append(PATIENT.tumor_site.lower().replace(" ", "_"))
    if PATIENT.diagnosis_description:
        # Extract key terms from diagnosis
        for term in ["colorectal", "sigmoid", "rectal", "colon"]:
            if term in PATIENT.diagnosis_description.lower():
                tags.append(term)
                break
    for marker, value in PATIENT.biomarkers.items():
        tags.append(f"{marker}_{value}")
    return tags


# ── Dynamic genetic profile ────────────────────

_BIOMARKER_PATTERNS: dict[str, list[re.Pattern]] = {
    "HER2": [re.compile(r"HER[\s-]*2[^:]*:\s*(positive|negative|equivocal)", re.I)],
    "KRAS": [re.compile(r"KRAS[^:]*:\s*(mutant|wild[\s-]*type|positive|negative)", re.I)],
    "NRAS": [re.compile(r"NRAS[^:]*:\s*(mutant|wild[\s-]*type|positive|negative)", re.I)],
    "BRAF": [re.compile(r"BRAF[^:]*:\s*(mutant|wild[\s-]*type|V600E|positive|negative)", re.I)],
    "MSI": [re.compile(r"MSI[^:]*:\s*(MSI[\s-]*H|MSS|MSI[\s-]*L|stable|high|low)", re.I)],
    "MMR": [re.compile(r"MMR[^:]*:\s*(deficient|proficient|dMMR|pMMR)", re.I)],
    "TMB": [re.compile(r"TMB[^:]*:\s*(\d+\.?\d*\s*mut/Mb|high|low|intermediate)", re.I)],
}


_GENETIC_SEARCH_TERMS = ["genetik", "HER2", "FISH", "NGS", "KRAS", "BRAF", "MSI", "pathology"]


async def get_genetic_profile() -> dict[str, str]:
    """Fetch genetic/biomarker data from oncofiles documents."""
    profile = dict(PATIENT.biomarkers)

    seen_ids: set[str] = set()
    for term in _GENETIC_SEARCH_TERMS:
        with contextlib.suppress(Exception):
            result = await oncofiles_client.search_documents(text=term)
            docs = result.get("documents", []) if isinstance(result, dict) else []

            for doc in docs:
                doc_id = str(doc.get("id", ""))
                if doc_id in seen_ids:
                    continue
                seen_ids.add(doc_id)
                with contextlib.suppress(Exception):
                    content = await oncofiles_client.view_document(doc_id)
                    text = _extract_text(content)
                    _update_biomarkers(profile, text)

    return profile


def _extract_text(content: dict | str) -> str:
    """Extract plain text from view_document response."""
    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        if "ocr_text" in content:
            return content["ocr_text"]
        if "content" in content and isinstance(content["content"], dict):
            return content["content"].get("ocr_text", "")
        return " ".join(str(v) for v in content.values() if isinstance(v, str))
    return ""


def _update_biomarkers(profile: dict[str, str], text: str) -> None:
    """Extract biomarker values from OCR text and update profile."""
    for marker, patterns in _BIOMARKER_PATTERNS.items():
        if marker in profile:
            continue
        for pattern in patterns:
            match = pattern.search(text)
            if match:
                profile[marker] = match.group(1).strip().lower()
                break
