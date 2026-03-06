from __future__ import annotations

import contextlib
import re
from datetime import date

from . import oncofiles_client
from .models import PatientProfile

PATIENT = PatientProfile(
    name="Erika Fusekova",
    diagnosis_code="C18.7",
    diagnosis_description="AdenoCa colon sigmoideum, G3, mCRC",
    tumor_site="Sigmoid colon",
    diagnosis_date=date(2025, 12, 1),
    biomarkers={
        "KRAS": "mutant G12S (c.34G>A)",
        "KRAS_G12C": False,
        "NRAS": "wild-type",
        "BRAF_V600E": "wild-type",
        "HER2": "negative (ratio 1.3, copy number 3)",
        "MSI": "pMMR / MSS",
        "anti_EGFR_eligible": False,
        "anti_EGFR_reason": "KRAS G12S mutation",
    },
    treatment_regimen="mFOLFOX6 90%",
    hospitals=["NOU (Narodny onkologicky ustav)", "Bory Nemocnica"],
    notes="Left-sided mCRC. 1L mFOLFOX6 90% dose. Active VJI thrombosis on Clexane.",
    staging="IV (liver mets, peritoneal carcinomatosis, LN, Krukenberg tumor l.dx.)",
    histology="Adenocarcinoma Grade 3",
    tumor_laterality="left-sided",
    metastases=[
        "liver (C78.7)",
        "peritoneum (C78.6)",
        "retroperitoneum",
        "Krukenberg (ovary l.dx., C79.6)",
        "mediastinal LN",
        "hilar LN",
        "retrocrural LN",
        "portal LN (C77.8)",
        "pulmonary nodules (<=5mm, monitor)",
    ],
    comorbidities=["VJI thrombosis (active, Clexane 0.6ml SC 2x/day)"],
    surgeries=[
        {
            "date": "2026-01-18",
            "institution": "Bory Nemocnica",
            "type": "palliative resection",
            "result": "AdenoCa G3",
        }
    ],
    treating_physician="MUDr. Stefan Porsok, PhD., MPH — primar OKO G, NOU Bratislava",
    admitting_physician="MUDr. Natalia Pazderova — NOU Bratislava",
    current_cycle=2,
    ecog="unknown — verify",
    excluded_therapies={
        "anti-EGFR (cetuximab, panitumumab)": "KRAS G12S mutation",
        "checkpoint monotherapy (pembrolizumab, nivolumab)": "pMMR/MSS",
        "HER2-targeted (trastuzumab, pertuzumab)": "HER2 negative",
        "BRAF inhibitors (encorafenib)": "BRAF wild-type",
        "KRAS G12C-specific (sotorasib, adagrasib)": "patient has G12S, not G12C",
    },
)

# Curated PubMed search terms for Erika's confirmed molecular profile
RESEARCH_TERMS: list[str] = [
    "KRAS G12S metastatic colorectal cancer treatment",
    "mCRC FOLFOX first-line KRAS mutant",
    "pan-KRAS inhibitor colorectal cancer",
    "SOS1 inhibitor KRAS colorectal BI-1701963",
    "MSS colorectal cancer immunotherapy combination",
    "botensilimab balstilimab MSS CRC",
    "bevacizumab VTE thrombosis colorectal cancer safety",
    "FOLFOX oxaliplatin neurotoxicity prevention",
    "mCRC left-sided KRAS mutant prognosis",
    "ivonescimab FOLFOX colorectal HARMONi",
]


def get_patient_profile_text() -> str:
    """Return formatted patient profile for MCP resource."""
    p = PATIENT
    biomarkers = "\n".join(f"  - {k}: {v}" for k, v in p.biomarkers.items())
    hospitals = ", ".join(p.hospitals)
    metastases = ", ".join(p.metastases) if p.metastases else "none listed"
    comorbidities = ", ".join(p.comorbidities) if p.comorbidities else "none"
    excluded = "\n".join(f"  - {k}: {v}" for k, v in p.excluded_therapies.items())

    tumor = (
        f"- **Tumor site**: {p.tumor_site} ({p.tumor_laterality})"
        if p.tumor_laterality
        else f"- **Tumor site**: {p.tumor_site}"
    )
    treatment = (
        f"- **Treatment**: {p.treatment_regimen} (cycle {p.current_cycle})"
        if p.current_cycle
        else f"- **Treatment**: {p.treatment_regimen}"
    )
    parts = [
        "# Patient Profile\n",
        f"- **Name**: {p.name}",
        f"- **Diagnosis**: {p.diagnosis_description} ({p.diagnosis_code})",
        f"- **Staging**: {p.staging}" if p.staging else "",
        f"- **Histology**: {p.histology}" if p.histology else "",
        tumor,
        f"- **Biomarkers**:\n{biomarkers}",
        treatment,
        f"- **ECOG**: {p.ecog}" if p.ecog else "",
        f"- **Metastases**: {metastases}",
        f"- **Comorbidities**: {comorbidities}",
        f"- **Hospitals**: {hospitals}",
        f"- **Treating physician**: {p.treating_physician}" if p.treating_physician else "",
        f"- **Excluded therapies**:\n{excluded}" if p.excluded_therapies else "",
        f"- **Notes**: {p.notes}",
    ]
    return "\n".join(line for line in parts if line) + "\n"


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
