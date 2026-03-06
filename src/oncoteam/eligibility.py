"""Programmatic eligibility checker for clinical trials against patient profile."""

from __future__ import annotations

import re

from .models import ClinicalTrial, EligibilityFlag, EligibilityResult, PatientProfile

# Drug names mapped to rules
_ANTI_EGFR = {"cetuximab", "panitumumab"}
_KRAS_G12C = {"sotorasib", "adagrasib"}
_HER2_TARGETED = {"trastuzumab", "pertuzumab", "trastuzumab deruxtecan", "t-dxd"}
_BRAF_INHIBITORS = {"encorafenib", "dabrafenib", "vemurafenib"}
_CHECKPOINT_MONO = {
    "pembrolizumab", "nivolumab", "atezolizumab", "durvalumab", "ipilimumab",
}
_BEVACIZUMAB = {"bevacizumab"}
_CHEMO_NAMES = {
    "folfox", "folfiri", "capox", "oxaliplatin",
    "irinotecan", "fluorouracil", "capecitabine",
}


def _drugs_in_trial(trial: ClinicalTrial) -> set[str]:
    """Extract lowercase drug names from interventions + eligibility text."""
    text = " ".join(trial.interventions) + " " + trial.eligibility_criteria
    return {w.lower() for w in re.findall(r"[a-zA-Z]\w+", text)}


def _fmt(names: set[str]) -> str:
    return ", ".join(sorted(names))


def check_eligibility(
    trial: ClinicalTrial, patient: PatientProfile,
) -> EligibilityResult:
    """Check trial eligibility against patient's molecular and clinical profile."""
    flags: list[EligibilityFlag] = []
    warnings: list[str] = []
    drugs = _drugs_in_trial(trial)

    # Rule 1: KRAS mutant -> no anti-EGFR
    matched = _ANTI_EGFR & drugs
    if matched:
        flags.append(EligibilityFlag(
            rule="KRAS_G12S_anti_EGFR",
            status="excluded",
            reason=(
                f"Anti-EGFR ({_fmt(matched)}) contraindicated"
                " — KRAS G12S mutant"
            ),
        ))

    # Rule 2: G12S != G12C -> no G12C-specific drugs
    matched = _KRAS_G12C & drugs
    if matched:
        flags.append(EligibilityFlag(
            rule="KRAS_G12S_not_G12C",
            status="excluded",
            reason=(
                f"KRAS G12C inhibitors ({_fmt(matched)})"
                " not applicable — patient has G12S"
            ),
        ))

    # Rule 3: pMMR/MSS -> checkpoint monotherapy not indicated
    checkpoint_found = _CHECKPOINT_MONO & drugs
    if checkpoint_found:
        has_chemo = bool(drugs & _CHEMO_NAMES)
        if not has_chemo and len(trial.interventions) <= 2:
            flags.append(EligibilityFlag(
                rule="pMMR_MSS_checkpoint_mono",
                status="excluded",
                reason=(
                    f"Checkpoint monotherapy ({_fmt(checkpoint_found)})"
                    " not indicated — pMMR/MSS"
                ),
            ))
        else:
            warnings.append(
                f"Checkpoint inhibitor ({_fmt(checkpoint_found)})"
                " in combination — acceptable for pMMR/MSS,"
                " monitor response"
            )

    # Rule 4: HER2 negative -> no HER2-targeted therapy
    matched = _HER2_TARGETED & drugs
    if matched:
        flags.append(EligibilityFlag(
            rule="HER2_negative",
            status="excluded",
            reason=(
                f"HER2-targeted therapy ({_fmt(matched)})"
                " not indicated — HER2 negative"
            ),
        ))

    # Rule 5: BRAF wild-type -> no BRAF inhibitors alone
    matched = _BRAF_INHIBITORS & drugs
    if matched:
        flags.append(EligibilityFlag(
            rule="BRAF_wildtype",
            status="excluded",
            reason=(
                f"BRAF inhibitors ({_fmt(matched)})"
                " not indicated — BRAF V600E wild-type"
            ),
        ))

    # Rule 6: Active VTE -> bevacizumab high risk
    if _BEVACIZUMAB & drugs:
        has_vte = any(
            "thrombosis" in c.lower() or "vte" in c.lower()
            for c in patient.comorbidities
        )
        if has_vte:
            flags.append(EligibilityFlag(
                rule="VTE_bevacizumab",
                status="warning",
                reason="Bevacizumab HIGH RISK — active VJI thrombosis on Clexane",
            ))
            warnings.append(
                "Active VTE + bevacizumab requires oncologist discussion"
            )

    excluded = any(f.status == "excluded" for f in flags)
    eligible = not excluded

    # Build summary
    if not flags and not warnings:
        summary = f"No biomarker contraindications found for {trial.nct_id}."
    else:
        parts = []
        if excluded:
            excl = [f for f in flags if f.status == "excluded"]
            parts.append(
                f"{len(excl)} exclusion(s): "
                + "; ".join(f.reason for f in excl)
            )
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
