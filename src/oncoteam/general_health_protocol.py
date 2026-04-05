"""General health protocol data for non-oncology patients (preventive care).

EU/WHO/ESC reference ranges and preventive screening schedules.
Parallel structure to clinical_protocol.py but for general health management.
"""

from __future__ import annotations

import copy
import functools

from .locale import L, resolve

# EU/WHO/ESC reference ranges for general adult health (male)
GENERAL_HEALTH_LAB_RANGES: dict[str, dict] = {
    "glucose_fasting": {
        "max": 5.6,
        "unit": "mmol/L",
        "guideline": "WHO/IDF",
        "note": L("nalačno", "fasting"),
    },
    "HbA1c": {
        "max": 42,
        "unit": "mmol/mol",
        "guideline": "WHO",
    },
    "cholesterol_total": {
        "max": 5.0,
        "unit": "mmol/L",
        "guideline": "ESC/EAS 2019",
    },
    "HDL": {
        "min": 1.0,
        "unit": "mmol/L",
        "note": L("muž", "male"),
        "guideline": "ESC/EAS 2019",
    },
    "LDL": {
        "max": 3.0,
        "unit": "mmol/L",
        "guideline": "ESC/EAS 2019",
    },
    "triglycerides": {
        "max": 1.7,
        "unit": "mmol/L",
        "guideline": "ESC/EAS 2019",
    },
    "TSH": {
        "min": 0.4,
        "max": 4.0,
        "unit": "mIU/L",
        "guideline": "ATA",
    },
    "creatinine": {
        "min": 62,
        "max": 106,
        "unit": "\u00b5mol/L",
        "note": L("muž", "male"),
        "guideline": "KDIGO",
    },
    "eGFR": {
        "min": 90,
        "unit": "mL/min/1.73m\u00b2",
        "guideline": "KDIGO",
    },
    "ALT": {
        "max": 45,
        "unit": "U/L",
        "guideline": L("štandardný dospelý muž", "standard adult male"),
    },
    "AST": {
        "max": 35,
        "unit": "U/L",
        "guideline": L("štandardný dospelý muž", "standard adult male"),
    },
    "bilirubin": {
        "max": 17,
        "unit": "\u00b5mol/L",
        "guideline": L("štandardný dospelý", "standard adult"),
    },
    "WBC": {
        "min": 4.0,
        "max": 10.0,
        "unit": "G/L",
        "guideline": L("štandardný dospelý", "standard adult"),
    },
    "hemoglobin": {
        "min": 130,
        "max": 175,
        "unit": "g/L",
        "note": L("muž", "male"),
    },
    "PLT": {
        "min": 150,
        "max": 400,
        "unit": "G/L",
        "guideline": L("štandardný dospelý", "standard adult"),
    },
    "vitamin_D": {
        "min": 75,
        "unit": "nmol/L",
        "guideline": "Endocrine Society",
    },
    "ferritin": {
        "min": 30,
        "max": 300,
        "unit": "\u00b5g/L",
        "note": L("muž", "male"),
    },
    "PSA": {
        "max": 4.0,
        "unit": "ng/mL",
        "guideline": "EAU",
        "note": L("muž >50, zdieľané rozhodovanie", "male >50, shared decision"),
    },
}

# EU preventive care screening schedule
PREVENTIVE_SCREENING_SCHEDULE: list[dict] = [
    {
        "screening": L("Kolonoskopia", "Colonoscopy"),
        "age": "50+",
        "interval": L("každých 10 rokov", "every 10 years"),
        "guideline": "EU Council 2022",
    },
    {
        "screening": "FOBT/FIT",
        "age": "50-74",
        "interval": L("každé 2 roky", "every 2 years"),
        "guideline": "EU Council 2022",
    },
    {
        "screening": L("Zubná prehliadka", "Dental checkup"),
        "age": L("všetci", "all"),
        "interval": L("každých 6 mesiacov", "every 6 months"),
    },
    {
        "screening": L("Očné vyšetrenie", "Ophthalmology"),
        "age": "40+",
        "interval": L("každé 2 roky", "every 2 years"),
    },
    {
        "screening": L("Dermatológia", "Dermatology"),
        "age": "35+",
        "interval": L("každé 2 roky", "every 2 years"),
        "guideline": "Euromelanoma",
    },
    {
        "screening": L("KV riziko (SCORE2)", "CV risk (SCORE2)"),
        "age": "40+",
        "interval": L("každých 5 rokov", "every 5 years"),
        "guideline": "ESC 2021",
    },
    {
        "screening": "PSA",
        "age": L("muž 50+", "male 50+"),
        "interval": L("každé 2 roky", "every 2 years"),
        "guideline": "EAU",
    },
    {
        "screening": L("Lipidový panel", "Lipid panel"),
        "age": "40+",
        "interval": L("každých 5 rokov", "every 5 years"),
        "guideline": "ESC/EAS",
    },
    {
        "screening": L("Glykémia nalačno", "Fasting glucose"),
        "age": "45+",
        "interval": L("každé 3 roky", "every 3 years"),
        "guideline": "WHO",
    },
    {
        "screening": L("Očkovanie proti chrípke", "Flu vaccine"),
        "age": "50+",
        "interval": L("ročne", "annual"),
        "guideline": "ECDC",
    },
    {
        "screening": L("Tetanus booster", "Tetanus booster"),
        "age": L("všetci", "all"),
        "interval": L("každých 10 rokov", "every 10 years"),
    },
]


# System prompt section for general health autonomous agents
GENERAL_HEALTH_SYSTEM_PROMPT = """\
# Lab Analysis -- General Health Protocol
Use EU/WHO/ESC reference ranges (NOT oncology thresholds):
- Metabolic: glucose fasting <5.6 mmol/L, HbA1c <42 mmol/mol
- Lipids: total cholesterol <5.0, HDL >1.0 (male), LDL <3.0, TG <1.7 (ESC/EAS 2019)
- Thyroid: TSH 0.4-4.0 mIU/L (ATA)
- Renal: creatinine 62-106 \u00b5mol/L (male), eGFR >90 (KDIGO)
- Hepatic: ALT <45, AST <35, bilirubin <17 \u00b5mol/L (standard adult male)
- CBC: WBC 4-10, HGB 130-175 g/L, PLT 150-400 (standard adult)
- Vitamins: vitamin D >75 nmol/L (Endocrine Society), ferritin 30-300 \u00b5g/L (male)
- Screening: PSA <4.0 ng/mL (EAU, male >50, shared decision)

DO NOT: calculate oncology inflammation indices, reference oncology chemo protocols,
suggest pre-cycle checklists.
DO: flag out-of-range values, compare to EU/WHO guidelines, track trends, end with \
"Preventive care reminders" section.

# EU Preventive Care Screening
Track and remind based on age/sex:
- Colonoscopy: 50+, every 10y (EU Council 2022)
- FOBT/FIT: 50-74, every 2y
- Dental: every 6 months
- Ophthalmology: 40+, every 2y
- Dermatology: 35+, every 2y (Euromelanoma)
- CV risk (SCORE2): 40+, every 5y (ESC 2021)
- PSA: 50+ male, every 2y (EAU)
- Lipid panel: 40+, every 5y (ESC/EAS)
- Fasting glucose: 45+, every 3y (WHO)
- Flu vaccine: 50+, annual (ECDC)
- Tetanus booster: every 10y

# Document Processing
When reviewing uploaded documents:
1. Read via view_document() -- extract date, institution, doctor, key findings, ICD codes
2. Store lab values via store_lab_values() with general health parameters
3. Create treatment_event (event_type: "checkup"/"screening"/"vaccination"/"procedure")
4. For handwritten notes: flag OCR uncertainties with [?]
5. Identify gaps in screening compliance

# Oncofiles Integration
- Patient uses `patient_type="general"` in oncofiles context
- 3 specific categories: vaccination, dental, preventive (alongside standard labs/imaging/etc.)
- Folder structure excludes chemo_sheet/pathology/genetics
- Use `get_lab_safety_check` -- automatically uses general health thresholds for this patient
"""


@functools.lru_cache(maxsize=2)
def _resolve_general_health_cached(lang: str) -> dict:
    """Resolve bilingual values for the general health protocol."""
    lab_ranges = {k: resolve(v, lang) for k, v in GENERAL_HEALTH_LAB_RANGES.items()}
    screening = [resolve(item, lang) for item in PREVENTIVE_SCREENING_SCHEDULE]
    return {
        "lab_ranges": lab_ranges,
        "screening_schedule": screening,
        "protocol_type": "general_health",
        # Empty oncology sections -- dashboard can check protocol_type
        "lab_thresholds": {},
        "dose_modifications": {},
        "milestones": [],
        "monitoring_schedule": {},
        "safety_flags": {},
        "second_line_options": [],
        "watched_trials": [],
        "cumulative_dose": {},
        "cycle_delay_rules": {},
        "nutrition_escalation": {},
    }


def resolve_general_health_protocol(lang: str = "sk") -> dict:
    """Return general health protocol data with bilingual values resolved."""
    return copy.deepcopy(_resolve_general_health_cached(lang))
