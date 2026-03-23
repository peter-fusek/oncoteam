from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from datetime import date

from . import oncofiles_client
from .activity_logger import record_suppressed_error
from .locale import L, resolve
from .models import PatientProfile

# ── Recipient Registry ────────────────────────────
# WhatsApp message recipients with role-aware formatting.


@dataclass(frozen=True)
class Recipient:
    """A WhatsApp message recipient with role and language preference."""

    name: str
    role: str  # "patient", "caregiver", "physician"
    phone: str
    language: str = "sk"  # ISO 639-1


# Pre-populated care team for current patient.
RECIPIENTS: dict[str, Recipient] = {
    "caregiver": Recipient(
        name="Peter",
        role="caregiver",
        phone="+421905123456",
        language="sk",
    ),
    "physician": Recipient(
        name="MUDr. Porsok",
        role="physician",
        phone="",  # not used — physician gets dashboard only
        language="sk",
    ),
}

# Default recipient for all agent WhatsApp messages.
DEFAULT_RECIPIENT = RECIPIENTS["caregiver"]


def format_whatsapp_header(
    title: str,
    recipient: Recipient | None = None,
    date_str: str = "",
) -> str:
    """Format a standardized WhatsApp message header.

    Returns lines like:
        *Pre-cycle check (cyklus 3)*
        Pre: Peter (opatrovateľ)
        Dátum: 2026-03-23
    """
    r = recipient or DEFAULT_RECIPIENT
    role_labels = {
        "caregiver": "opatrovateľ" if r.language == "sk" else "caregiver",
        "physician": "lekár" if r.language == "sk" else "physician",
        "patient": "pacient" if r.language == "sk" else "patient",
    }
    lines = [f"*{title}*"]
    lines.append(f"Pre: {r.name} ({role_labels.get(r.role, r.role)})")
    if date_str:
        lines.append(f"Dátum: {date_str}")
    lines.append("")  # blank line before content
    return "\n".join(lines)


# Therapy type categories for display grouping and badges
THERAPY_CATEGORIES: dict[str, dict] = {
    "chemo": {"label": "Chemoterapia", "label_en": "Chemotherapy", "color": "#e53e3e"},
    "targeted": {"label": "Cielená terapia", "label_en": "Targeted therapy", "color": "#dd6b20"},
    "immuno": {"label": "Imunoterapia", "label_en": "Immunotherapy", "color": "#805ad5"},
    "supportive": {"label": "Podporná liečba", "label_en": "Supportive care", "color": "#3182ce"},
    "surgery": {"label": "Chirurgia", "label_en": "Surgery", "color": "#2f855a"},
    "anticoagulation": {
        "label": "Antikoagulácia",
        "label_en": "Anticoagulation",
        "color": "#d69e2e",
    },
}


PATIENT = PatientProfile(
    patient_id="erika",
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
    hospitals=["NOU (Národný onkologický ústav)", "Nemocnica Bory"],
    notes="Left-sided mCRC. 1L mFOLFOX6 90% dose. Active VJI thrombosis on Clexane.",
    staging="IV",
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
            "institution": "Nemocnica Bory",
            "type": "palliative resection",
            "result": "AdenoCa G3",
        }
    ],
    treating_physician="MUDr. Stefan Porsok, PhD., MPH — primár OKO G, NOU Bratislava",
    admitting_physician="MUDr. Natália Pazderová — NOU Bratislava",
    baseline_weight_kg=72.0,
    current_cycle=3,
    ecog="unknown — verify",
    excluded_therapies={
        "anti-EGFR (cetuximab, panitumumab)": "KRAS G12S mutation",
        "checkpoint monotherapy (pembrolizumab, nivolumab)": "pMMR/MSS",
        "HER2-targeted (trastuzumab, pertuzumab)": "HER2 negative",
        "BRAF inhibitors (encorafenib)": "BRAF wild-type",
        "KRAS G12C-specific (sotorasib, adagrasib)": "patient has G12S, not G12C",
    },
    patient_ids={
        "rodne_cislo": "XXXXXX/XXXX",
        "nou_id": "overiť",
    },
    active_therapies=[
        {
            "name": "mFOLFOX6 90%",
            "category": "chemo",
            "drugs": [
                {
                    "name": "Oxaliplatin",
                    "dose": "76.5 mg/m²",
                    "lay": "Platinový liek, ktorý poškodzuje DNA nádorových buniek",
                    "medical": "3rd-gen platinum analog; forms inter/intra-strand DNA crosslinks",
                },
                {
                    "name": "Leucovorin (calcium folinate)",
                    "dose": "400 mg/m²",
                    "lay": "Vitamín, ktorý zosilňuje účinok 5-FU",
                    "medical": "Reduced folate; potentiates 5-FU by stabilizing FdUMP-TS complex",
                },
                {
                    "name": "5-Fluorouracil (5-FU)",
                    "dose": "400 mg/m² bolus + 2400 mg/m² 46h infúzia",
                    "lay": "Antimetabolit, ktorý bráni deleniu nádorových buniek",
                    "medical": "Fluoropyrimidine antimetabolite; inhibits thymidylate synthase",
                },
            ],
            "status": "active",
            "cycle": 3,
        },
        {
            "name": "Clexane (enoxaparin)",
            "category": "anticoagulation",
            "drugs": [
                {
                    "name": "Enoxaparin",
                    "dose": "0.6 ml SC 2x/deň",
                    "lay": "Riedenie krvi — prevencia zhoršenia krvnej zrazeniny v žile",
                    "medical": "LMWH anticoagulation for active VJI thrombosis",
                },
            ],
            "status": "active",
            "indication": "VJI thrombosis",
        },
        {
            "name": "Bevacizumab",
            "category": "targeted",
            "drugs": [
                {
                    "name": "Bevacizumab",
                    "dose": "5 mg/kg q2w",
                    "lay": (
                        "Protilátka blokujúca rast ciev nádoru — VYSOKÉ RIZIKO pre aktívnu trombózu"
                    ),
                    "medical": "Anti-VEGF mAb; HIGH RISK due to active VJI thrombosis + Clexane",
                },
            ],
            "status": "planned",
            "warning": "HIGH RISK — requires explicit oncologist discussion due to active VTE",
        },
    ],
)

# ── Bilingual overlay for dashboard display ──────────────────────────────
# Keys match PATIENT fields. Values are L(sk, en) bilingual dicts.
# Fields not listed here are displayed as-is (e.g. name, diagnosis_code).

_PATIENT_L10N: dict = {
    "tumor_site": L("Sigmoideum (hrubé črevo)", "Sigmoid colon"),
    "histology": L("Adenokarcinóm G3", "Adenocarcinoma Grade 3"),
    "tumor_laterality": L("ľavostranný", "left-sided"),
    "staging": L(
        "IV (metastázy pečene, peritoneálna karcinomatóza, LU, Krukenbergov tumor l.dx.)",
        "IV (liver mets, peritoneal carcinomatosis, LN, Krukenberg tumor l.dx.)",
    ),
    "ecog": L("neznámy — overiť", "unknown — verify"),
    "notes": L(
        "Ľavostranný mCRC. 1L mFOLFOX6 90% dávka. Aktívna VJI trombóza na Clexane.",
        "Left-sided mCRC. 1L mFOLFOX6 90% dose. Active VJI thrombosis on Clexane.",
    ),
    "metastases": [
        L("pečeň (C78.7)", "liver (C78.7)"),
        L("pobrušnica (C78.6)", "peritoneum (C78.6)"),
        L("retroperitoneum", "retroperitoneum"),
        L("Krukenbergov tumor (vaječník l.dx., C79.6)", "Krukenberg (ovary l.dx., C79.6)"),
        L("mediastinálne LU", "mediastinal LN"),
        L("hilové LU", "hilar LN"),
        L("retrokrurálne LU", "retrocrural LN"),
        L("portálne LU (C77.8)", "portal LN (C77.8)"),
        L("pľúcne uzlíky (<=5mm, sledovanie)", "pulmonary nodules (<=5mm, monitor)"),
    ],
    "comorbidities": [
        L(
            "VJI trombóza (aktívna, Clexane 0,6ml SC 2x/deň)",
            "VJI thrombosis (active, Clexane 0.6ml SC 2x/day)",
        ),
    ],
    "excluded_therapies": [
        {
            "therapy": L(
                "anti-EGFR (cetuximab, panitumumab)", "anti-EGFR (cetuximab, panitumumab)"
            ),
            "reason": L("KRAS G12S mutácia", "KRAS G12S mutation"),
        },
        {
            "therapy": L(
                "checkpoint monoterapia (pembrolizumab, nivolumab)",
                "checkpoint monotherapy (pembrolizumab, nivolumab)",
            ),
            "reason": L("pMMR/MSS", "pMMR/MSS"),
        },
        {
            "therapy": L(
                "HER2-cielená terapia (trastuzumab, pertuzumab)",
                "HER2-targeted (trastuzumab, pertuzumab)",
            ),
            "reason": L("HER2 negatívny", "HER2 negative"),
        },
        {
            "therapy": L("BRAF inhibítory (encorafenib)", "BRAF inhibitors (encorafenib)"),
            "reason": L("BRAF wild-type", "BRAF wild-type"),
        },
        {
            "therapy": L(
                "KRAS G12C-špecifické (sotorasib, adagrasib)",
                "KRAS G12C-specific (sotorasib, adagrasib)",
            ),
            "reason": L("pacient má G12S, nie G12C", "patient has G12S, not G12C"),
        },
    ],
    "biomarker_annotations": {
        "KRAS": L("Riadiaca mutácia liečby", "Treatment driver mutation"),
        "MSI": L("Marker eligibility imunoterapie", "Immunotherapy eligibility marker"),
    },
    # patient_ids values are IDs, not translatable — labels come from frontend i18n
    "active_therapies": [
        {
            "name": "mFOLFOX6 90%",
            "category": "chemo",
            "drugs": [
                {
                    "name": "Oxaliplatin",
                    "dose": "76.5 mg/m²",
                    "lay": L(
                        "Platinový liek, ktorý poškodzuje DNA nádorových buniek",
                        "Platinum drug that damages cancer cell DNA",
                    ),
                    "medical": L(
                        "Platinový analóg 3. generácie; tvorí inter/intra-reťazcové"
                        " DNA krížové väzby",
                        "3rd-gen platinum analog; forms inter/intra-strand DNA crosslinks",
                    ),
                },
                {
                    "name": "Leucovorin",
                    "dose": "400 mg/m²",
                    "lay": L(
                        "Vitamín, ktorý zosilňuje účinok 5-FU",
                        "Vitamin that enhances 5-FU effect",
                    ),
                    "medical": L(
                        "Redukovaný folát; zosilňuje 5-FU stabilizáciou komplexu FdUMP-TS",
                        "Reduced folate; potentiates 5-FU by stabilizing FdUMP-TS complex",
                    ),
                },
                {
                    "name": "5-Fluorouracil (5-FU)",
                    "dose": L(
                        "400 mg/m² bolus + 2400 mg/m² 46h infúzia",
                        "400 mg/m² bolus + 2400 mg/m² 46h infusion",
                    ),
                    "lay": L(
                        "Antimetabolit, ktorý bráni deleniu nádorových buniek",
                        "Antimetabolite that prevents cancer cell division",
                    ),
                    "medical": L(
                        "Fluoropyrimidínový antimetabolit; inhibuje tymidylátsyntetázu",
                        "Fluoropyrimidine antimetabolite; inhibits thymidylate synthase",
                    ),
                },
            ],
            "status": L("aktívna", "active"),
        },
        {
            "name": L("Clexane (enoxaparín)", "Clexane (enoxaparin)"),
            "category": "anticoagulation",
            "drugs": [
                {
                    "name": L("Enoxaparín", "Enoxaparin"),
                    "dose": "0.6 ml SC 2x/deň",
                    "lay": L(
                        "Riedenie krvi — prevencia zhoršenia krvnej zrazeniny v žile",
                        "Blood thinner — prevents worsening of the blood clot in the vein",
                    ),
                    "medical": L(
                        "LMWH antikoagulácia pre aktívnu VJI trombózu",
                        "LMWH anticoagulation for active VJI thrombosis",
                    ),
                },
            ],
            "status": L("aktívna", "active"),
            "indication": L("VJI trombóza", "VJI thrombosis"),
        },
        {
            "name": "Bevacizumab",
            "category": "targeted",
            "drugs": [
                {
                    "name": "Bevacizumab",
                    "dose": "5 mg/kg q2w",
                    "lay": L(
                        "Protilátka blokujúca rast ciev nádoru — VYSOKÉ RIZIKO",
                        "Antibody blocking tumor blood vessel growth — HIGH RISK",
                    ),
                    "medical": L(
                        "Anti-VEGF mAb; VYSOKÉ RIZIKO kvôli aktívnej VJI trombóze + Clexane",
                        "Anti-VEGF mAb; HIGH RISK due to active VJI thrombosis + Clexane",
                    ),
                },
            ],
            "status": L("plánovaná", "planned"),
            "warning": L(
                "VYSOKÉ RIZIKO — vyžaduje výslovný súhlas onkológa kvôli aktívnej VTE",
                "HIGH RISK — requires explicit oncologist discussion due to active VTE",
            ),
        },
    ],
    "surgeries": [
        {
            "date": "2026-01-18",
            "institution": "Nemocnica Bory",
            "type": L("paliatívna resekcia", "palliative resection"),
            "result": "AdenoCa G3",
        }
    ],
}


def get_patient_localized(lang: str = "sk") -> dict:
    """Return patient profile dict with bilingual fields resolved to requested language."""
    data = PATIENT.model_dump()
    # Convert date to ISO string
    if data.get("diagnosis_date"):
        data["diagnosis_date"] = str(data["diagnosis_date"])

    # Overlay bilingual fields
    for key, bilingual_value in _PATIENT_L10N.items():
        if key == "biomarker_annotations":
            # Special: this is extra data not in PATIENT model
            data["biomarker_annotations"] = resolve(bilingual_value, lang)
            continue
        data[key] = resolve(bilingual_value, lang)

    return data


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


# ── Patient Registry ──────────────────────────────
# In-memory registry of loaded patient profiles. Erika is pre-seeded.
# Future patients load from oncofiles on first access.

_patient_registry: dict[str, PatientProfile] = {"erika": PATIENT}

# Per-patient bearer tokens for oncofiles. Token scopes all data automatically.
# Erika uses the default ONCOFILES_MCP_TOKEN from config.
_patient_tokens: dict[str, str] = {}  # patient_id → bearer token

# Per-patient research terms. Erika's are hardcoded; others derived from profile.
_patient_research_terms: dict[str, list[str]] = {"erika": RESEARCH_TERMS}

# Per-patient recipients. Erika's are hardcoded; others loaded from oncofiles.
_patient_recipients: dict[str, dict[str, Recipient]] = {"erika": RECIPIENTS}

DEFAULT_PATIENT_ID = "erika"


def get_patient(patient_id: str = DEFAULT_PATIENT_ID) -> PatientProfile:
    """Get a patient profile by ID. Returns Erika by default."""
    if patient_id in _patient_registry:
        return _patient_registry[patient_id]
    raise KeyError(f"Patient '{patient_id}' not found. Register via register_patient().")


def register_patient(
    patient_id: str,
    token: str,
    profile: PatientProfile,
    research_terms: list[str] | None = None,
    recipients: dict[str, Recipient] | None = None,
) -> PatientProfile:
    """Register a new patient in the in-memory registry.

    Args:
        patient_id: Unique patient identifier (e.g. "jan_novak")
        token: Dedicated oncofiles bearer token — scopes all data to this patient
        profile: Patient profile with diagnosis, biomarkers, treatment plan
        research_terms: Curated PubMed search terms (derived from diagnosis if None)
        recipients: Care team recipients for WhatsApp (empty if None)
    """
    profile.patient_id = patient_id
    _patient_registry[patient_id] = profile
    _patient_tokens[patient_id] = token
    _patient_research_terms[patient_id] = research_terms or _derive_research_terms(profile)
    _patient_recipients[patient_id] = recipients or {}
    return profile


def _derive_research_terms(patient: PatientProfile) -> list[str]:
    """Auto-generate PubMed search terms from a patient's profile."""
    terms = []
    dx = patient.diagnosis_description.lower()
    regimen = patient.treatment_regimen

    # Cancer type + treatment
    if dx and regimen:
        terms.append(f"{dx} {regimen} treatment")

    # Biomarker-specific searches
    for marker, value in patient.biomarkers.items():
        if isinstance(value, str) and value.lower() not in ("wild-type", "negative", "false"):
            terms.append(f"{marker} {value} {dx}")

    # Treatment + side effects
    if regimen:
        terms.append(f"{regimen} toxicity management")
        terms.append(f"{regimen} dose modification")

    # General prognosis
    if patient.staging:
        terms.append(f"{dx} stage {patient.staging} prognosis")

    return terms or [f"{dx} treatment"]


def get_patient_token(patient_id: str = DEFAULT_PATIENT_ID) -> str | None:
    """Get the oncofiles bearer token for a patient.

    Returns None for Erika (uses default ONCOFILES_MCP_TOKEN from config).
    For other patients, returns their dedicated token which scopes all
    oncofiles data to that patient automatically.
    """
    return _patient_tokens.get(patient_id)


def get_patient_recipients(
    patient_id: str = DEFAULT_PATIENT_ID,
) -> dict[str, Recipient]:
    """Get recipients for a patient."""
    return _patient_recipients.get(patient_id, {})


def get_patient_research_terms(
    patient_id: str = DEFAULT_PATIENT_ID,
) -> list[str]:
    """Get curated research terms for a patient."""
    return _patient_research_terms.get(patient_id, [])


def build_patient_profile_text(patient: PatientProfile) -> str:
    """Build formatted profile text for any patient (not just Erika)."""
    biomarkers = "\n".join(f"  - {k}: {v}" for k, v in patient.biomarkers.items())
    hospitals = ", ".join(patient.hospitals)
    metastases = ", ".join(patient.metastases) if patient.metastases else "none"
    comorbidities = ", ".join(patient.comorbidities) if patient.comorbidities else "none"
    excluded = "\n".join(f"  - {k}: {v}" for k, v in patient.excluded_therapies.items())
    parts = [
        "# Patient Profile\n",
        f"- **Patient ID**: {patient.patient_id}",
        f"- **Name**: {patient.name}",
        f"- **Diagnosis**: {patient.diagnosis_description} ({patient.diagnosis_code})",
        f"- **Staging**: {patient.staging}" if patient.staging else "",
        f"- **Histology**: {patient.histology}" if patient.histology else "",
        f"- **Tumor site**: {patient.tumor_site}",
        f"- **Biomarkers**:\n{biomarkers}",
        f"- **Treatment**: {patient.treatment_regimen}"
        + (f" (cycle {patient.current_cycle})" if patient.current_cycle else ""),
        f"- **ECOG**: {patient.ecog}" if patient.ecog else "",
        f"- **Metastases**: {metastases}",
        f"- **Comorbidities**: {comorbidities}",
        f"- **Hospitals**: {hospitals}",
        f"- **Treating physician**: {patient.treating_physician}"
        if patient.treating_physician
        else "",
        f"- **Excluded therapies**:\n{excluded}" if patient.excluded_therapies else "",
        f"- **Notes**: {patient.notes}",
    ]
    return "\n".join(line for line in parts if line) + "\n"


def build_biomarker_rules(patient: PatientProfile) -> str:
    """Generate biomarker safety rules from a patient's profile.

    These are the NEVER-violate rules that go into the system prompt.
    Derived dynamically from the patient's biomarkers and excluded therapies.
    """
    rules = ["# Biomarker Rules (NEVER violate)"]
    for marker, value in patient.biomarkers.items():
        rules.append(f"- {marker}: {value}")
    if patient.excluded_therapies:
        rules.append("\nExcluded therapies (NEVER suggest):")
        for therapy, reason in patient.excluded_therapies.items():
            rules.append(f"- {therapy}: {reason}")
    if patient.comorbidities:
        rules.append("\nComorbidity alerts:")
        for c in patient.comorbidities:
            rules.append(f"- {c}")
    return "\n".join(rules)


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
    """Fetch genetic/biomarker data from oncofiles documents.

    Uses asyncio.gather to batch search and view calls (fix N+1 #96).
    """
    profile = dict(PATIENT.biomarkers)

    # Batch all search calls in parallel
    async def _search(term: str) -> list[dict]:
        try:
            result = await oncofiles_client.search_documents(text=term)
            return result.get("documents", []) if isinstance(result, dict) else []
        except Exception as e:
            record_suppressed_error("patient_context", f"search_{term}", e)
            return []

    search_results = await asyncio.gather(*[_search(t) for t in _GENETIC_SEARCH_TERMS])

    # Collect unique doc IDs
    seen_ids: set[str] = set()
    doc_ids: list[str] = []
    for docs in search_results:
        for doc in docs:
            doc_id = str(doc.get("id", ""))
            if doc_id and doc_id not in seen_ids:
                seen_ids.add(doc_id)
                doc_ids.append(doc_id)

    # Batch all view calls in parallel
    async def _view(doc_id: str) -> str:
        try:
            content = await oncofiles_client.view_document(doc_id)
            return _extract_text(content)
        except Exception as e:
            record_suppressed_error("patient_context", f"view_{doc_id}", e)
            return ""

    texts = await asyncio.gather(*[_view(d) for d in doc_ids])
    for text in texts:
        if text:
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
