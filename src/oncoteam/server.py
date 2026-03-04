from __future__ import annotations

import contextlib
import json

from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

from . import clinicaltrials_client, erika_client, pubmed_client
from .config import MCP_BEARER_TOKEN, MCP_HOST, MCP_PORT, MCP_TRANSPORT
from .models import ResearchSource
from .patient_context import (
    PATIENT,
    RESEARCH_TERMS,
    get_patient_profile_text,
    get_research_terms_text,
)

# ── Auth ────────────────────────────────────────
auth = None
if MCP_BEARER_TOKEN:
    from fastmcp.server.auth import StaticTokenVerifier

    auth = StaticTokenVerifier(tokens={MCP_BEARER_TOKEN: {"client_id": "claude-ai", "scopes": []}})

mcp = FastMCP(
    "Oncoteam",
    instructions=(
        "Oncoteam is a persistent AI agent for cancer treatment management. "
        "It searches PubMed and ClinicalTrials.gov for relevant research, "
        "tracks treatment events, and provides lab trend analysis. "
        "All data is persisted through the Erika Files MCP server."
    ),
    auth=auth,
)


# ── Resources ───────────────────────────────────


@mcp.resource("oncoteam://patient-profile", description="Patient treatment profile")
def patient_profile() -> str:
    return get_patient_profile_text()


@mcp.resource("oncoteam://research-terms", description="Curated PubMed search terms")
def research_terms() -> str:
    return get_research_terms_text()


# ── Tools ───────────────────────────────────────


@mcp.tool()
async def search_pubmed(query: str, max_results: int = 10) -> str:
    """Search PubMed for articles and store results in Erika.

    Args:
        query: PubMed search query (e.g. "colorectal cancer FOLFOX")
        max_results: Maximum number of articles to return (default 10)

    Returns:
        JSON with list of matching articles.
    """
    articles = await pubmed_client.search_pubmed(query, max_results)

    # Store each article in erika (don't fail search if storage fails)
    for article in articles:
        with contextlib.suppress(Exception):
            await erika_client.add_research_entry(
                source=ResearchSource.PUBMED,
                external_id=article.pmid,
                title=article.title,
                summary=article.abstract[:500] if article.abstract else "",
                tags=["FOLFOX", "colorectal"],
                raw_data=article.model_dump_json(),
            )

    return json.dumps(
        {
            "query": query,
            "count": len(articles),
            "articles": [a.model_dump() for a in articles],
        }
    )


@mcp.tool()
async def search_clinical_trials(
    condition: str = "colorectal cancer",
    intervention: str | None = None,
    max_results: int = 10,
) -> str:
    """Search ClinicalTrials.gov for recruiting studies and store results in Erika.

    Args:
        condition: Medical condition to search for
        intervention: Optional intervention/treatment filter
        max_results: Maximum number of trials to return (default 10)

    Returns:
        JSON with list of matching clinical trials.
    """
    trials = await clinicaltrials_client.search_trials(condition, intervention, max_results)

    for trial in trials:
        with contextlib.suppress(Exception):
            await erika_client.add_research_entry(
                source=ResearchSource.CLINICALTRIALS,
                external_id=trial.nct_id,
                title=trial.title,
                summary=trial.summary[:500] if trial.summary else "",
                tags=trial.conditions[:5],
                raw_data=trial.model_dump_json(),
            )

    return json.dumps(
        {
            "condition": condition,
            "intervention": intervention,
            "count": len(trials),
            "trials": [t.model_dump() for t in trials],
        }
    )


@mcp.tool()
async def daily_briefing() -> str:
    """Run preset research queries for Erika's case and compile a summary.

    Searches PubMed with curated terms and ClinicalTrials.gov for recruiting studies.

    Returns:
        JSON summary of all research findings from today's briefing.
    """
    results = {"pubmed": [], "clinical_trials": []}

    # PubMed searches — use top 3 terms to stay within rate limits
    for term in RESEARCH_TERMS[:3]:
        try:
            articles = await pubmed_client.search_pubmed(term, max_results=5)
            for article in articles:
                results["pubmed"].append(
                    {"query": term, "pmid": article.pmid, "title": article.title}
                )
                with contextlib.suppress(Exception):
                    await erika_client.add_research_entry(
                        source=ResearchSource.PUBMED,
                        external_id=article.pmid,
                        title=article.title,
                        summary=article.abstract[:500] if article.abstract else "",
                        tags=["daily_briefing"],
                        raw_data=article.model_dump_json(),
                    )
        except Exception:
            results["pubmed"].append({"query": term, "error": "search failed"})

    # ClinicalTrials.gov
    try:
        condition = f"{PATIENT.diagnosis_description} {PATIENT.treatment_regimen}"
        trials = await clinicaltrials_client.search_trials(condition, max_results=10)
        for trial in trials:
            results["clinical_trials"].append(
                {"nct_id": trial.nct_id, "title": trial.title, "status": trial.status}
            )
            with contextlib.suppress(Exception):
                await erika_client.add_research_entry(
                    source=ResearchSource.CLINICALTRIALS,
                    external_id=trial.nct_id,
                    title=trial.title,
                    summary=trial.summary[:500] if trial.summary else "",
                    tags=["daily_briefing"],
                    raw_data=trial.model_dump_json(),
                )
    except Exception:
        results["clinical_trials"].append({"error": "search failed"})

    return json.dumps(
        {
            "briefing": "daily",
            "pubmed_articles": len(results["pubmed"]),
            "clinical_trials": len(results["clinical_trials"]),
            "results": results,
        }
    )


@mcp.tool()
async def get_lab_trends(limit: int = 10) -> str:
    """Query Erika for lab-related documents and format for trend analysis.

    Args:
        limit: Maximum number of lab documents to retrieve

    Returns:
        JSON with lab documents for trend analysis.
    """
    try:
        result = await erika_client.search_documents(text="lab", category="labs")
        return json.dumps({"source": "erika", "lab_documents": result})
    except Exception as e:
        return json.dumps({"error": str(e), "hint": "Erika MCP may not be available"})


@mcp.tool()
async def search_erika_documents(text: str, category: str | None = None) -> str:
    """Search medical documents stored in Erika.

    Args:
        text: Search text
        category: Optional category filter (e.g. 'labs', 'reports', 'imaging')

    Returns:
        JSON with matching documents.
    """
    try:
        result = await erika_client.search_documents(text, category)
        return json.dumps({"query": text, "category": category, "results": result})
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
async def get_patient_context() -> str:
    """Return the full patient treatment profile.

    Returns:
        JSON with patient diagnosis, treatment, biomarkers, and hospitals.
    """
    return json.dumps(PATIENT.model_dump(), default=str)


# ── Health check ────────────────────────────────


@mcp.custom_route("/health", methods=["GET"])
async def health(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok", "server": "oncoteam", "version": "0.1.0"})


# ── Entry point ─────────────────────────────────


def main() -> None:
    if MCP_TRANSPORT == "stdio":
        mcp.run()
    else:
        mcp.run(transport=MCP_TRANSPORT, host=MCP_HOST, port=MCP_PORT)


if __name__ == "__main__":
    main()
