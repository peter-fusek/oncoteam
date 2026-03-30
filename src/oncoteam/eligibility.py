"""Programmatic eligibility checker for clinical trials against patient profile."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .models import ClinicalTrial, EligibilityFlag, EligibilityResult, PatientProfile

# Drug names mapped to rules
_ANTI_EGFR = {"cetuximab", "panitumumab"}
_KRAS_G12C = {"sotorasib", "adagrasib"}
_HER2_TARGETED = {"trastuzumab", "pertuzumab", "trastuzumab deruxtecan", "t-dxd"}
_BRAF_INHIBITORS = {"encorafenib", "dabrafenib", "vemurafenib"}
_CHECKPOINT_MONO = {
    "pembrolizumab",
    "nivolumab",
    "atezolizumab",
    "durvalumab",
    "ipilimumab",
}
_BEVACIZUMAB = {"bevacizumab"}
_CHEMO_NAMES = {
    "folfox",
    "folfiri",
    "capox",
    "oxaliplatin",
    "irinotecan",
    "fluorouracil",
    "capecitabine",
}

# --- Research relevance scoring ---

# Contraindicated drug/target keywords → "not_applicable"
_CONTRAINDICATED_KEYWORDS = (
    _ANTI_EGFR | _KRAS_G12C | _HER2_TARGETED | {"anti-egfr", "anti egfr", "egfr inhibit"}
)

# High relevance: matches patient's specific profile
_HIGH_RELEVANCE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"kras\s*(?:g12\w|mutat)",
        r"(?:mcrc|metastatic\s+colorectal)",
        r"folfox",
        r"(?:first|1st|1l|first.line)\s*line",
        r"pan.kras",
        r"ras\s*mutat",
        r"left.sided\s*(?:colon|crc|colorectal)",
    ]
]

# Medium relevance: broadly related
_MEDIUM_RELEVANCE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"colorectal",
        r"\bcrc\b",
        r"colon\s*cancer",
        r"oxaliplatin",
        r"systemic\s*immune.inflammation",
        r"\bsii\b",
        r"liver\s*metast",
        r"peritoneal",
        r"anticoagul",
        r"thrombosis.*cancer",
        r"cancer.*thrombosis",
    ]
]


@dataclass
class ResearchRelevance:
    """Result of research relevance assessment."""

    score: str  # "high", "medium", "low", "not_applicable"
    reason: str


def assess_research_relevance(
    title: str,
    summary: str | None = None,
    *,
    patient: PatientProfile | None = None,
) -> ResearchRelevance:
    """Assess how relevant a research entry is to the patient's profile.

    Checks for contraindicated therapies (false hope), then scores
    by biomarker/treatment/disease match.
    """
    text = (title + " " + (summary or "")).lower()
    words = set(re.findall(r"[a-z][a-z0-9-]+", text))

    kras_val = (patient.biomarkers.get("KRAS", "") if patient else "G12S") or "mutant"
    her2_val = (patient.biomarkers.get("HER2", "") if patient else "negative") or "negative"

    # Rule 1: Contraindicated — false hope detection
    matched_contra = _CONTRAINDICATED_KEYWORDS & words
    if matched_contra:
        # Check if it's specifically about KRAS G12C (not general KRAS)
        if matched_contra & _KRAS_G12C:
            return ResearchRelevance(
                score="not_applicable",
                reason=f"KRAS G12C inhibitor — patient has {kras_val}, not G12C",
            )
        if matched_contra & (_ANTI_EGFR | {"anti-egfr", "anti egfr", "egfr inhibit"}):
            return ResearchRelevance(
                score="not_applicable",
                reason=f"Anti-EGFR therapy — contraindicated (KRAS {kras_val})",
            )
        if matched_contra & _HER2_TARGETED:
            return ResearchRelevance(
                score="not_applicable",
                reason=f"HER2-targeted therapy — patient is HER2 {her2_val}",
            )

    # Rule 1b: Later-line trials — patient is on 1L, these are 2L/3L+
    _later_line_re = re.compile(
        r"(?:second|third|2nd|3rd|2l|3l|later)\s*(?:-?\s*)?line"
        r"|previously\s+treated"
        r"|refractory"
        r"|after\s+(?:progression|failure)\s+(?:on|of)"
        r"|post[- ]?progression"
        r"|salvage\s+therap",
        re.IGNORECASE,
    )
    if _later_line_re.search(text):
        # Still relevant but not for current line — medium relevance with annotation
        return ResearchRelevance(
            score="medium",
            reason="Later-line trial (2L/3L+) — patient is on 1st line",
        )

    # Check for checkpoint monotherapy in MSS context
    checkpoint_words = _CHECKPOINT_MONO & words
    if checkpoint_words:
        has_combo = bool(words & _CHEMO_NAMES) or "combin" in text
        if not has_combo and ("mss" in text or "microsatellite stable" in text):
            return ResearchRelevance(
                score="not_applicable",
                reason="Checkpoint monotherapy for MSS — not indicated (pMMR/MSS)",
            )

    # Rule 2: High relevance — specific profile match
    for pattern in _HIGH_RELEVANCE_PATTERNS:
        if pattern.search(text):
            return ResearchRelevance(
                score="high",
                reason=f"Matches patient profile: {pattern.pattern}",
            )

    # Rule 3: Medium relevance — broadly related
    for pattern in _MEDIUM_RELEVANCE_PATTERNS:
        if pattern.search(text):
            return ResearchRelevance(
                score="medium",
                reason=f"Related to patient's condition: {pattern.pattern}",
            )

    # Rule 4: Low relevance — no specific match
    return ResearchRelevance(
        score="low",
        reason="No specific match to patient's biomarkers or treatment",
    )


def _drugs_in_trial(trial: ClinicalTrial) -> set[str]:
    """Extract lowercase drug names from interventions + eligibility text."""
    text = " ".join(trial.interventions) + " " + trial.eligibility_criteria
    return {w.lower() for w in re.findall(r"[a-zA-Z]\w+", text)}


def _fmt(names: set[str]) -> str:
    return ", ".join(sorted(names))


def check_eligibility(
    trial: ClinicalTrial,
    patient: PatientProfile,
) -> EligibilityResult:
    """Check trial eligibility against patient's molecular and clinical profile."""
    flags: list[EligibilityFlag] = []
    warnings: list[str] = []
    drugs = _drugs_in_trial(trial)

    kras_val = patient.biomarkers.get("KRAS", "mutant") or "mutant"
    her2_val = patient.biomarkers.get("HER2", "negative") or "negative"
    braf_val = patient.biomarkers.get("BRAF_V600E", "wild-type") or "wild-type"
    msi_val = patient.biomarkers.get("MSI", "pMMR/MSS") or "pMMR/MSS"

    # Rule 1: KRAS mutant -> no anti-EGFR
    matched = _ANTI_EGFR & drugs
    if matched:
        flags.append(
            EligibilityFlag(
                rule="KRAS_anti_EGFR",
                status="excluded",
                reason=f"Anti-EGFR ({_fmt(matched)}) contraindicated — KRAS {kras_val}",
            )
        )

    # Rule 2: KRAS G12C-specific drugs only for G12C
    matched = _KRAS_G12C & drugs
    if matched:
        flags.append(
            EligibilityFlag(
                rule="KRAS_not_G12C",
                status="excluded",
                reason=(
                    f"KRAS G12C inhibitors ({_fmt(matched)}) not applicable"
                    f" — patient has {kras_val}"
                ),
            )
        )

    # Rule 3: pMMR/MSS -> checkpoint monotherapy not indicated
    checkpoint_found = _CHECKPOINT_MONO & drugs
    if checkpoint_found:
        has_chemo = bool(drugs & _CHEMO_NAMES)
        if not has_chemo and len(trial.interventions) <= 2:
            flags.append(
                EligibilityFlag(
                    rule="pMMR_MSS_checkpoint_mono",
                    status="excluded",
                    reason=(
                        f"Checkpoint monotherapy ({_fmt(checkpoint_found)})"
                        f" not indicated — {msi_val}"
                    ),
                )
            )
        else:
            warnings.append(
                f"Checkpoint inhibitor ({_fmt(checkpoint_found)})"
                f" in combination — acceptable for {msi_val},"
                " monitor response"
            )

    # Rule 4: HER2 negative -> no HER2-targeted therapy
    matched = _HER2_TARGETED & drugs
    if matched:
        flags.append(
            EligibilityFlag(
                rule="HER2_negative",
                status="excluded",
                reason=f"HER2-targeted therapy ({_fmt(matched)}) not indicated — HER2 {her2_val}",
            )
        )

    # Rule 5: BRAF wild-type -> no BRAF inhibitors alone
    matched = _BRAF_INHIBITORS & drugs
    if matched:
        flags.append(
            EligibilityFlag(
                rule="BRAF_wildtype",
                status="excluded",
                reason=f"BRAF inhibitors ({_fmt(matched)}) not indicated — BRAF V600E {braf_val}",
            )
        )

    # Rule 6: Active VTE -> bevacizumab high risk
    if _BEVACIZUMAB & drugs:
        has_vte = any(
            "thrombosis" in c.lower() or "vte" in c.lower() for c in patient.comorbidities
        )
        if has_vte:
            vte_detail = next(
                (
                    c
                    for c in patient.comorbidities
                    if "thrombosis" in c.lower() or "vte" in c.lower()
                ),
                "active VTE",
            )
            flags.append(
                EligibilityFlag(
                    rule="VTE_bevacizumab",
                    status="warning",
                    reason=f"Bevacizumab HIGH RISK — {vte_detail}",
                )
            )
            warnings.append("Active VTE + bevacizumab requires oncologist discussion")

    excluded = any(f.status == "excluded" for f in flags)
    eligible = not excluded

    # Build summary
    if not flags and not warnings:
        summary = f"No biomarker contraindications found for {trial.nct_id}."
    else:
        parts = []
        if excluded:
            excl = [f for f in flags if f.status == "excluded"]
            parts.append(f"{len(excl)} exclusion(s): " + "; ".join(f.reason for f in excl))
        warn_flags = [f for f in flags if f.status == "warning"]
        if warn_flags or warnings:
            parts.append(f"{len(warn_flags) + len(warnings)} warning(s)")
        summary = ". ".join(parts)

    return EligibilityResult(
        nct_id=trial.nct_id,
        eligible=eligible,
        flags=flags,
        warnings=warnings,
        summary=summary,
    )
