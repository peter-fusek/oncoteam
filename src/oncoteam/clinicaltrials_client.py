from __future__ import annotations

import httpx

from .config import CTGOV_BASE_URL
from .models import ClinicalTrial


async def search_trials(
    condition: str,
    intervention: str | None = None,
    max_results: int = 10,
) -> list[ClinicalTrial]:
    """Search ClinicalTrials.gov API v2 for recruiting studies."""
    params: dict = {
        "query.cond": condition,
        "filter.overallStatus": "RECRUITING",
        "pageSize": min(max_results, 100),
        "format": "json",
        "fields": (
            "NCTId,BriefTitle,OverallStatus,Phase,Condition,"
            "InterventionName,LocationFacility,BriefSummary"
        ),
    }
    if intervention:
        params["query.intr"] = intervention

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(f"{CTGOV_BASE_URL}/studies", params=params)
        resp.raise_for_status()
        data = resp.json()

    return _parse_studies(data)


def _parse_studies(data: dict) -> list[ClinicalTrial]:
    """Parse ClinicalTrials.gov v2 JSON response."""
    trials = []
    for study in data.get("studies", []):
        proto = study.get("protocolSection", {})
        ident = proto.get("identificationModule", {})
        status_mod = proto.get("statusModule", {})
        design = proto.get("designModule", {})
        conditions_mod = proto.get("conditionsModule", {})
        interventions_mod = proto.get("armsInterventionsModule", {})
        locations_mod = proto.get("contactsLocationsModule", {})
        desc = proto.get("descriptionModule", {})

        nct_id = ident.get("nctId", "")
        title = ident.get("briefTitle", "")
        status = status_mod.get("overallStatus", "")

        phases = design.get("phases", [])
        phase = ", ".join(phases) if phases else ""

        conditions = conditions_mod.get("conditions", [])

        interventions = []
        for intr in interventions_mod.get("interventions", []):
            name = intr.get("name", "")
            if name:
                interventions.append(name)

        locations = []
        for loc in locations_mod.get("locations", []):
            facility = loc.get("facility", "")
            if facility:
                locations.append(facility)

        summary = desc.get("briefSummary", "")

        trials.append(
            ClinicalTrial(
                nct_id=nct_id,
                title=title,
                status=status,
                phase=phase,
                conditions=conditions,
                interventions=interventions,
                locations=locations,
                summary=summary,
            )
        )

    return trials
