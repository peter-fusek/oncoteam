from __future__ import annotations

import contextlib
import json

from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

from . import clinicaltrials_client, oncofiles_client, pubmed_client
from .activity_logger import log_activity, log_to_diary
from .config import MCP_BEARER_TOKEN, MCP_HOST, MCP_PORT, MCP_TRANSPORT
from .models import ResearchSource
from .patient_context import (
    PATIENT,
    RESEARCH_TERMS,
    get_context_tags,
    get_genetic_profile,
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
        "All data is persisted through the Oncofiles MCP server.\n\n"
        "MANDATORY LOGGING — follow these rules every session:\n"
        "1. At the END of every conversation, call summarize_session() with a summary "
        "of what was discussed, decided, and any follow-up actions.\n"
        "2. Call log_research_decision() whenever you make or recommend a "
        "clinical/research decision.\n"
        "3. Call log_session_note() for important observations or context worth preserving.\n"
        "4. All tool calls are automatically logged for audit purposes.\n\n"
        "IMPORTANT: Never skip the summarize_session() call — it is the primary audit trail."
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
@log_activity
async def search_pubmed(query: str, max_results: int = 10) -> str:
    """Search PubMed for articles and store results in Oncofiles.

    Args:
        query: PubMed search query (e.g. "colorectal cancer FOLFOX")
        max_results: Maximum number of articles to return (default 10)

    Returns:
        JSON with list of matching articles.
    """
    articles = await pubmed_client.search_pubmed(query, max_results)

    # Store each article in oncofiles (don't fail search if storage fails)
    for article in articles:
        with contextlib.suppress(Exception):
            await oncofiles_client.add_research_entry(
                source=ResearchSource.PUBMED,
                external_id=article.pmid,
                title=article.title,
                summary=article.abstract[:500] if article.abstract else "",
                tags=get_context_tags(),
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
@log_activity
async def search_clinical_trials(
    condition: str = "colorectal cancer",
    intervention: str | None = None,
    max_results: int = 10,
    country: str | None = None,
) -> str:
    """Search ClinicalTrials.gov for recruiting studies and store results in Oncofiles.

    Args:
        condition: Medical condition to search for
        intervention: Optional intervention/treatment filter
        max_results: Maximum number of trials to return (default 10)
        country: Optional country filter (e.g. "Slovakia", "Czech Republic")

    Returns:
        JSON with list of matching clinical trials.
    """
    trials = await clinicaltrials_client.search_trials(
        condition,
        intervention,
        max_results,
        country,
    )

    for trial in trials:
        with contextlib.suppress(Exception):
            await oncofiles_client.add_research_entry(
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
@log_activity
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
                    await oncofiles_client.add_research_entry(
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
                await oncofiles_client.add_research_entry(
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
@log_activity
async def get_lab_trends(limit: int = 10) -> str:
    """Query Oncofiles for lab-related documents and format for trend analysis.

    Args:
        limit: Maximum number of lab documents to retrieve

    Returns:
        JSON with lab documents for trend analysis.
    """
    try:
        result = await oncofiles_client.search_documents(text="lab", category="labs", limit=limit)
        return json.dumps({"source": "oncofiles", "lab_documents": result})
    except Exception as e:
        return json.dumps({"error": str(e), "hint": "Oncofiles MCP may not be available"})


@mcp.tool()
@log_activity
async def search_documents(text: str, category: str | None = None) -> str:
    """Search medical documents stored in Oncofiles.

    Args:
        text: Search text
        category: Optional category filter (e.g. 'labs', 'reports', 'imaging')

    Returns:
        JSON with matching documents.
    """
    try:
        result = await oncofiles_client.search_documents(text, category)
        return json.dumps({"query": text, "category": category, "results": result})
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
@log_activity
async def get_patient_context() -> str:
    """Return the full patient treatment profile with dynamic genetic data.

    Returns:
        JSON with patient diagnosis, treatment, biomarkers (enriched from oncofiles), and hospitals.
    """
    data = PATIENT.model_dump()
    with contextlib.suppress(Exception):
        genetic = await get_genetic_profile()
        data["biomarkers"] = genetic
    return json.dumps(data, default=str)


@mcp.tool()
@log_activity
async def view_document(file_id: str) -> str:
    """View full document content with OCR text and images from Oncofiles.

    Args:
        file_id: The document file ID in Oncofiles

    Returns:
        JSON with document content.
    """
    try:
        result = await oncofiles_client.view_document(file_id)
        return json.dumps({"file_id": file_id, "content": result})
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
@log_activity
async def analyze_labs(file_id: str | None = None, limit: int = 10) -> str:
    """Analyze lab results in oncology context via Oncofiles.

    Args:
        file_id: Optional specific lab document file ID
        limit: Maximum number of lab results to analyze (default 10)

    Returns:
        JSON with lab analysis.
    """
    try:
        result = await oncofiles_client.analyze_labs(file_id, limit)
        return json.dumps({"analysis": result})
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
@log_activity
async def compare_labs(file_id_a: str, file_id_b: str) -> str:
    """Compare two lab documents for trend analysis via Oncofiles.

    Args:
        file_id_a: First lab document file ID
        file_id_b: Second lab document file ID

    Returns:
        JSON with lab comparison.
    """
    try:
        result = await oncofiles_client.compare_labs(file_id_a, file_id_b)
        return json.dumps({"comparison": result})
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
async def log_research_decision(
    decision: str, reasoning: str, tags: list[str] | None = None
) -> str:
    """Record a clinical/research decision with reasoning.

    Use this when making or recommending treatment decisions, protocol changes,
    or research directions.

    Args:
        decision: Short description of the decision
        reasoning: Detailed reasoning behind the decision
        tags: Optional tags for categorization
    """
    await log_to_diary(
        title=decision,
        content=reasoning,
        entry_type="decision",
        tags=tags,
    )
    return "Decision logged."


@mcp.tool()
async def log_session_note(note: str, tags: list[str] | None = None) -> str:
    """Record an observation, context note, or diary entry.

    Use this to capture important observations, session summaries, or
    contextual information worth preserving.

    Args:
        note: The note content
        tags: Optional tags for categorization
    """
    await log_to_diary(
        title=note[:100],
        content=note,
        entry_type="note",
        tags=tags,
    )
    return "Note logged."


@mcp.tool()
async def summarize_session(
    summary: str, decisions: list[str] | None = None, follow_ups: list[str] | None = None
) -> str:
    """Log a session summary. MUST be called at the end of every conversation.

    Args:
        summary: What was discussed and accomplished this session
        decisions: Key decisions made (if any)
        follow_ups: Action items or follow-up tasks identified

    Returns:
        Confirmation that the session was logged.
    """
    parts = [summary]
    if decisions:
        parts.append("\n\nDecisions:\n" + "\n".join(f"- {d}" for d in decisions))
    if follow_ups:
        parts.append("\n\nFollow-ups:\n" + "\n".join(f"- {f}" for f in follow_ups))
    content = "".join(parts)

    await log_to_diary(
        title=f"Session: {summary[:80]}",
        content=content,
        entry_type="session_summary",
        tags=["session"],
    )
    return "Session summary logged."


# ── Health check ────────────────────────────────


@mcp.custom_route("/health", methods=["GET"])
async def health(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok", "server": "oncoteam", "version": "0.3.0"})


# ── Entry point ─────────────────────────────────


def main() -> None:
    if MCP_TRANSPORT == "stdio":
        mcp.run()
    else:
        mcp.run(transport=MCP_TRANSPORT, host=MCP_HOST, port=MCP_PORT)


if __name__ == "__main__":
    main()
