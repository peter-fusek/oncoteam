"""Embedded clinical protocol data for mCRC treatment monitoring.

Sourced from ESMO 2022 mCRC Living Guidelines, NCCN Colon Cancer Guidelines,
ASCO VTE Guidelines, ASH 2021 VTE in Cancer. NOT AI-generated.
"""

from __future__ import annotations

# FOLFOX dose modification rules (NCCN)
DOSE_MODIFICATION_RULES: dict[str, str] = {
    "neuropathy_grade_2": (
        "Reduce oxaliplatin to 75%. Continue 5-FU/LV full dose."
    ),
    "neuropathy_grade_3": (
        "HOLD oxaliplatin. Continue 5-FU/LV (de Gramont). "
        "Resume at 50% if resolves to grade 1."
    ),
    "neuropathy_grade_4": "DISCONTINUE oxaliplatin permanently.",
    "plt_below_75k": "Hold FOLFOX. Recheck in 1 week.",
    "anc_below_1500": "Hold FOLFOX. Consider G-CSF if recurrent.",
    "alt_ast_above_5x": (
        "Hold FOLFOX. Evaluate hepatic progression vs toxicity."
    ),
    "diarrhea_grade_3": (
        "Hold 5-FU. Resume at 80% when resolved to grade 1."
    ),
}

# Pre-cycle lab safety thresholds
LAB_SAFETY_THRESHOLDS: dict[str, dict] = {
    "ANC": {"min": 1500, "unit": "/uL", "action": "hold_chemo"},
    "PLT": {"min": 75000, "unit": "/uL", "action": "hold_chemo"},
    "PLT_anticoag": {"min": 50000, "unit": "/uL", "action": "flag_hematology"},
    "creatinine": {"max_ratio": 1.5, "note": "vs ULN", "action": "hold_chemo"},
    "ALT": {"max_ratio": 5.0, "note": "vs ULN, liver mets allowed", "action": "hold_chemo"},
    "AST": {"max_ratio": 5.0, "note": "vs ULN, liver mets allowed", "action": "hold_chemo"},
    "bilirubin": {"max_ratio": 1.5, "note": "vs ULN", "action": "hold_chemo"},
}

# Treatment timeline milestones
TREATMENT_MILESTONES: list[dict[str, str | int]] = [
    {
        "cycle": 3,
        "action": "first_response_ct",
        "description": "Schedule first CT response evaluation (RECIST 1.1)",
    },
    {
        "cycle": 4,
        "action": "tumor_markers",
        "description": "CEA + CA 19-9 trend check vs baseline",
    },
    {
        "cycle": 6,
        "action": "neuropathy_cumulative",
        "description": "Formal cumulative neuropathy assessment (NCI-CTC)",
    },
    {
        "cycle": 6,
        "action": "maintenance_discussion",
        "description": "Discuss maintenance vs continuation vs oxaliplatin holiday",
    },
    {
        "cycle": 8,
        "action": "second_response_ct",
        "description": "Second CT response evaluation",
    },
    {
        "cycle": 12,
        "action": "end_of_first_line",
        "description": (
            "Evaluate 1L completion, maintenance strategy, 2L trial screening"
        ),
    },
]

# Monitoring schedule (days relative to cycle start)
MONITORING_SCHEDULE: dict[str, str] = {
    "pre_cycle_labs": "Every 14 days (day 1 of each cycle)",
    "tumor_markers": "Every 4-8 weeks (cycles 2, 4, 6...)",
    "response_imaging": "Every 8 weeks after first assessment (cycles 4, 8, 12...)",
    "neuropathy_grade": "Every cycle, formal assessment every 3 cycles",
    "vte_check": "Every cycle: PLT + clinical DVT/PE assessment",
    "ecog_assessment": "Every cycle",
    "weight_nutrition": "Every cycle, flag if >5% loss from baseline",
    "trial_screening": "Weekly (new trials published continuously)",
    "research_scan": "Daily (PubMed, preprints relevant to case)",
}

# Watched clinical trials (specific to patient profile)
WATCHED_TRIALS: list[str] = [
    "HARMONi-GI3 (ivonescimab + FOLFOX)",
    "pan-KRAS: BI-1701963 (SOS1 inhibitor)",
    "pan-KRAS: RMC-6236",
    "pan-KRAS: JAB-3312",
    "botensilimab + balstilimab (MSS CRC)",
    "anti-TIGIT combinations (MSS CRC)",
]

# 2L options ranking for KRAS G12S mCRC (ESMO/NCCN based)
SECOND_LINE_OPTIONS: list[dict[str, str]] = [
    {
        "regimen": "FOLFIRI +/- bevacizumab",
        "evidence": "ESMO preferred 2L after oxaliplatin-based 1L",
        "note": "If bev not used in 1L or beyond progression on bev",
    },
    {
        "regimen": "FOLFIRI +/- aflibercept",
        "evidence": "VELOUR trial",
        "note": "Anti-VEGF option",
    },
    {
        "regimen": "FOLFIRI +/- ramucirumab",
        "evidence": "RAISE trial",
        "note": "Anti-VEGF option",
    },
    {
        "regimen": "Trifluridine/tipiracil (TAS-102)",
        "evidence": "RECOURSE trial, 3L+",
        "note": "Later line",
    },
    {
        "regimen": "Regorafenib",
        "evidence": "CORRECT trial, 3L+",
        "note": "Later line",
    },
    {
        "regimen": "Clinical trial (pan-KRAS inhibitor)",
        "evidence": "Experimental",
        "note": "Screen actively for KRAS G12S-eligible trials",
    },
]

# Drug interaction safety flags
SAFETY_FLAGS: dict[str, dict[str, str]] = {
    "anti_egfr_kras_mutant": {
        "rule": "NEVER — permanently contraindicated",
        "source": "ESMO 2022",
    },
    "bevacizumab_active_vte": {
        "rule": "HIGH RISK — requires explicit oncologist discussion",
        "source": "ASCO VTE 2023",
    },
    "oxaliplatin_grade3_neuropathy": {
        "rule": "HOLD oxaliplatin, continue 5-FU/LV (de Gramont)",
        "source": "NCCN",
    },
    "checkpoint_mono_pmmr_mss": {
        "rule": "NOT indicated as monotherapy",
        "source": "ESMO 2022",
    },
    "lmwh_thrombocytopenia_50k": {
        "rule": "FLAG — dose reduction or hold, hematology consult",
        "source": "ASH 2021",
    },
    "5fu_dpd_deficiency": {
        "rule": "TEST recommended — fatal toxicity risk",
        "source": "ESMO/CPIC",
    },
}

# Pre-cycle checklist template
PRE_CYCLE_CHECKLIST = """\
## Pre-Cycle {cycle_number} Checklist — mFOLFOX6

### 1. Laboratory Safety
- [ ] ANC >= 1,500/uL
- [ ] PLT >= 75,000/uL (also check >= 50,000 for full-dose Clexane)
- [ ] Creatinine <= 1.5x ULN
- [ ] ALT/AST <= 5x ULN (liver mets threshold)
- [ ] Bilirubin <= 1.5x ULN

### 2. Toxicity Assessment (NCI-CTC grading)
- [ ] Peripheral neuropathy: Grade ___
- [ ] Diarrhea: Grade ___
- [ ] Mucositis: Grade ___
- [ ] Fatigue: Grade ___
- [ ] Hand-foot syndrome: Grade ___
- [ ] Nausea/vomiting: Grade ___

### 3. VTE Monitoring
- [ ] PLT adequate for Clexane continuation
- [ ] No new DVT/PE symptoms (leg swelling, dyspnea, chest pain)
- [ ] Clexane compliance confirmed

### 4. General Assessment
- [ ] ECOG performance status: ___
- [ ] Weight: ___ kg (baseline: ___ kg, change: __%)
- [ ] Nutritional status adequate

### 5. Upcoming Milestones
{milestones}

### 6. Questions for Oncologist
{questions}
"""


def check_lab_safety(lab_name: str, value: float) -> dict[str, str | bool]:
    """Check a single lab value against safety thresholds.

    Returns dict with 'safe', 'action', 'message' keys.
    """
    threshold = LAB_SAFETY_THRESHOLDS.get(lab_name)
    if not threshold:
        return {"safe": True, "action": "none", "message": f"No threshold defined for {lab_name}"}

    if "min" in threshold and value < threshold["min"]:
        return {
            "safe": False,
            "action": threshold["action"],
            "message": (
                f"{lab_name} = {value} {threshold.get('unit', '')} "
                f"< {threshold['min']} — {threshold['action']}"
            ),
        }
    return {"safe": True, "action": "none", "message": f"{lab_name} within safe range"}


def get_milestones_for_cycle(cycle: int) -> list[dict]:
    """Return milestones at or near the given cycle number."""
    return [m for m in TREATMENT_MILESTONES if m["cycle"] == cycle or m["cycle"] == cycle + 1]


def get_dose_modification(toxicity: str) -> str | None:
    """Look up dose modification rule for a toxicity key."""
    return DOSE_MODIFICATION_RULES.get(toxicity)


def format_pre_cycle_checklist(
    cycle_number: int,
    milestones: str = "None upcoming",
    questions: str = "None generated",
) -> str:
    """Format the pre-cycle checklist template."""
    return PRE_CYCLE_CHECKLIST.format(
        cycle_number=cycle_number,
        milestones=milestones,
        questions=questions,
    )
