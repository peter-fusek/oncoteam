from __future__ import annotations

import json

from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

from . import clinicaltrials_client, github_client, oncofiles_client, pubmed_client
from .activity_logger import (
    get_session_id,
    get_suppressed_errors,
    log_activity,
    log_to_diary,
    record_suppressed_error,
)
from .config import MCP_BEARER_TOKEN, MCP_HOST, MCP_PORT, MCP_TRANSPORT
from .eligibility import check_eligibility
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
        #
        # --- BIOMARKER RULES ENGINE ---
        #
        "BIOMARKER RULES (NEVER violate):\n"
        "- Patient has KRAS G12S (c.34G>A). This is NOT G12C.\n"
        "- anti-EGFR (cetuximab, panitumumab) is PERMANENTLY CONTRAINDICATED (any RAS mutation).\n"
        "- anti-EGFR eligible ONLY if KRAS WT AND NRAS WT AND BRAF WT — patient fails this.\n"
        "- KRAS G12C-specific inhibitors (sotorasib, adagrasib) do NOT apply to G12S.\n"
        "- Patient is pMMR/MSS — checkpoint inhibitor MONOTHERAPY not indicated.\n"
        "- HER2 negative — HER2-targeted therapy not indicated.\n"
        "- BRAF V600E wild-type — BRAF inhibitors alone not indicated.\n"
        "- Active VJI thrombosis + Clexane — bevacizumab is HIGH RISK (discuss with oncologist).\n"
        "- Checkpoint inhibitors ARE compatible with anticoagulation.\n\n"
        #
        # --- EXCLUDED THERAPIES ---
        #
        "NEVER SUGGEST these therapies:\n"
        "- Anti-EGFR: cetuximab, panitumumab (KRAS G12S)\n"
        "- Checkpoint monotherapy: pembrolizumab, nivolumab (pMMR/MSS)\n"
        "- HER2-targeted: trastuzumab, pertuzumab, T-DXd (HER2 neg)\n"
        "- BRAF inhibitors alone: encorafenib (BRAF wt)\n"
        "- KRAS G12C-specific: sotorasib, adagrasib (patient has G12S)\n\n"
        #
        # --- DOCUMENT READING PROTOCOL ---
        #
        "DOCUMENT READING PROTOCOL:\n"
        "- For pathology/genetics documents: ALWAYS call view_document() to read content.\n"
        "- NEVER rely on metadata alone for pathology or genetics documents.\n"
        "- After reading: extract biomarker data and note in session log.\n"
        "- If document is unreadable: log as 'needs re-upload with OCR'.\n\n"
        #
        # --- LAB ANALYSIS PROTOCOL ---
        #
        "LAB ANALYSIS — always include:\n"
        "1. SII (Systemic Immune-Inflammation Index) = (abs_NEUT x PLT) / abs_LYMPH\n"
        "   - >1800 = high inflammatory burden; >30% decline after C1 = favorable\n"
        "2. Ne/Ly ratio: >3.0 poor prognosis, <2.5 improving\n"
        "3. CBC delta table: [Parameter | Baseline | Current | Change% | Reference | Status]\n"
        "4. Liver enzyme pattern: hepatocellular (ALT/AST up) vs "
        "cholestatic (GMT/ALP up) vs mixed\n"
        "   - Relate to known hepatic mets (C78.7)\n"
        "5. PLT + thrombosis cross-check: if PLT elevated + active VTE, FLAG immediately\n"
        "6. Tumor markers: CEA, CA19-9 trends (need baseline pre-treatment values)\n"
        "7. End every analysis with 'Questions for oncologist' section (2-4 specific questions)\n\n"
        #
        # --- CLINICAL TRIAL SEARCH ---
        #
        "CLINICAL TRIAL SEARCH for SK patient:\n"
        "- Search: SK, CZ, AT (Vienna=60km), HU (Budapest=2h)\n"
        "- Eligibility check: KRAS status, VTE active, ECOG, prior lines\n"
        "- Monitor: HARMONi-GI3, pan-KRAS (BI-1701963, RMC-6236, JAB-3312)\n"
        "- MSS CRC combinations: botensilimab+balstilimab, anti-TIGIT\n"
        "- CRC-only filter: exclude pediatric/HCC/biliary trials\n\n"
        #
        # --- MANDATORY LOGGING ---
        #
        "MANDATORY LOGGING — follow these rules every session:\n"
        "1. At the END of every conversation, call summarize_session() with a summary "
        "of what was discussed, decided, and any follow-up actions.\n"
        "2. Call log_research_decision() whenever you make or recommend a "
        "clinical/research decision.\n"
        "3. Call log_session_note() for important observations or context worth preserving.\n"
        "4. All tool calls are automatically logged for audit purposes.\n\n"
        "IMPORTANT: Never skip the summarize_session() call — it is the primary audit trail.\n\n"
        #
        # --- QA REVIEW PROTOCOL ---
        #
        "QA REVIEW PROTOCOL:\n"
        "After every session (before summarize_session), or when asked to review:\n"
        "1. Call review_session() to get the full timeline and error data.\n"
        "2. Analyze: errors, suppressed errors, slow tools, failed storage, missing data.\n"
        "3. For actionable findings, call create_improvement_issue() with the right repo.\n"
        "4. Log the QA summary via log_session_note(tags=['qa_review']).\n"
        "5. Then call summarize_session() as usual."
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
        try:
            await oncofiles_client.add_research_entry(
                source=ResearchSource.PUBMED,
                external_id=article.pmid,
                title=article.title,
                summary=article.abstract[:500] if article.abstract else "",
                tags=get_context_tags(),
                raw_data=article.model_dump_json(),
            )
        except Exception as e:
            record_suppressed_error("search_pubmed", "store_research", e)

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
        try:
            await oncofiles_client.add_research_entry(
                source=ResearchSource.CLINICALTRIALS,
                external_id=trial.nct_id,
                title=trial.title,
                summary=trial.summary[:500] if trial.summary else "",
                tags=trial.conditions[:5],
                raw_data=trial.model_dump_json(),
            )
        except Exception as e:
            record_suppressed_error("search_clinical_trials", "store_research", e)

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
async def search_clinical_trials_adjacent(
    condition: str = "colorectal cancer",
    intervention: str | None = None,
    max_per_country: int = 5,
) -> str:
    """Search ClinicalTrials.gov across SK and adjacent countries (CZ, AT, HU).

    Searches in parallel and deduplicates by NCT ID.

    Args:
        condition: Medical condition to search for
        intervention: Optional intervention/treatment filter
        max_per_country: Maximum results per country (default 5)

    Returns:
        JSON with deduplicated trials from all countries.
    """
    trials = await clinicaltrials_client.search_trials_adjacent(
        condition,
        intervention,
        max_per_country,
    )

    for trial in trials:
        try:
            await oncofiles_client.add_research_entry(
                source=ResearchSource.CLINICALTRIALS,
                external_id=trial.nct_id,
                title=trial.title,
                summary=trial.summary[:500] if trial.summary else "",
                tags=["adjacent_countries", *trial.conditions[:3]],
                raw_data=trial.model_dump_json(),
            )
        except Exception as e:
            record_suppressed_error("search_clinical_trials_adjacent", "store_research", e)

    return json.dumps(
        {
            "condition": condition,
            "intervention": intervention,
            "countries": clinicaltrials_client.ADJACENT_COUNTRIES,
            "count": len(trials),
            "trials": [t.model_dump() for t in trials],
        }
    )


@mcp.tool()
@log_activity
async def fetch_pubmed_article(pmid: str) -> str:
    """Fetch a specific PubMed article by PMID.

    Args:
        pmid: PubMed ID (e.g. "12345678")

    Returns:
        JSON with article details, or error if not found.
    """
    article = await pubmed_client.fetch_article(pmid)
    if article is None:
        return json.dumps({"error": f"Article {pmid} not found"})
    return json.dumps({"article": article.model_dump()})


@mcp.tool()
@log_activity
async def fetch_trial_details(nct_id: str) -> str:
    """Fetch details for a specific clinical trial by NCT ID.

    Args:
        nct_id: ClinicalTrials.gov ID (e.g. "NCT00001234")

    Returns:
        JSON with trial details including eligibility criteria.
    """
    trial = await clinicaltrials_client.fetch_trial(nct_id)
    if trial is None:
        return json.dumps({"error": f"Trial {nct_id} not found"})
    return json.dumps({"trial": trial.model_dump()})


@mcp.tool()
@log_activity
async def check_trial_eligibility(nct_id: str) -> str:
    """Check if a clinical trial is eligible for this patient based on biomarker rules.

    Fetches the trial from ClinicalTrials.gov and checks against the patient's
    molecular profile (KRAS G12S, pMMR/MSS, HER2 neg, BRAF wt, active VTE).

    Args:
        nct_id: ClinicalTrials.gov ID (e.g. "NCT00001234")

    Returns:
        JSON with eligibility result: {eligible, flags, warnings, summary}
    """
    trial = await clinicaltrials_client.fetch_trial(nct_id)
    if trial is None:
        return json.dumps({"error": f"Trial {nct_id} not found"})

    result = check_eligibility(trial, PATIENT)
    return json.dumps({"eligibility": result.model_dump()})


@mcp.tool()
@log_activity
async def daily_briefing() -> str:
    """Run preset research queries for Erika's case and compile a summary.

    Searches PubMed with curated terms and ClinicalTrials.gov for recruiting studies.

    Returns:
        JSON summary of all research findings from today's briefing.
    """
    results = {"pubmed": [], "clinical_trials": []}
    seen_pmids: set[str] = set()

    # PubMed searches — use top 3 terms to stay within rate limits
    for term in RESEARCH_TERMS[:3]:
        try:
            articles = await pubmed_client.search_pubmed(term, max_results=5)
            for article in articles:
                if article.pmid in seen_pmids:
                    continue
                seen_pmids.add(article.pmid)
                results["pubmed"].append(
                    {"query": term, "pmid": article.pmid, "title": article.title}
                )
                try:
                    await oncofiles_client.add_research_entry(
                        source=ResearchSource.PUBMED,
                        external_id=article.pmid,
                        title=article.title,
                        summary=article.abstract[:500] if article.abstract else "",
                        tags=["daily_briefing"],
                        raw_data=article.model_dump_json(),
                    )
                except Exception as e:
                    record_suppressed_error("daily_briefing", "store_pubmed", e)
        except Exception:
            results["pubmed"].append({"query": term, "error": "search failed"})

    # ClinicalTrials.gov — search adjacent countries for KRAS-mutant mCRC
    try:
        trials = await clinicaltrials_client.search_trials_adjacent(
            condition="KRAS mutant metastatic colorectal cancer",
            max_per_country=5,
        )
        for trial in trials:
            results["clinical_trials"].append(
                {"nct_id": trial.nct_id, "title": trial.title, "status": trial.status}
            )
            try:
                await oncofiles_client.add_research_entry(
                    source=ResearchSource.CLINICALTRIALS,
                    external_id=trial.nct_id,
                    title=trial.title,
                    summary=trial.summary[:500] if trial.summary else "",
                    tags=["daily_briefing", "adjacent_countries"],
                    raw_data=trial.model_dump_json(),
                )
            except Exception as e:
                record_suppressed_error("daily_briefing", "store_trial", e)
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
    try:
        genetic = await get_genetic_profile()
        data["biomarkers"] = genetic
    except Exception as e:
        record_suppressed_error("get_patient_context", "genetic_profile", e)
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


# ── QA Tools ────────────────────────────────────


@mcp.tool()
@log_activity
async def review_session(session_id: str | None = None) -> str:
    """Review a session: reconstruct timeline, surface errors, compute stats.

    Args:
        session_id: Session to review (default: current session).

    Returns:
        JSON with timeline, stats, errors, suppressed_errors, and session_summary.
    """
    sid = session_id or get_session_id()

    # Fetch activity log for this session
    activity = {}
    try:
        activity = await oncofiles_client.search_activity_log(session_id=sid)
    except Exception as e:
        record_suppressed_error("review_session", "fetch_activity", e)

    # Fetch session conversations
    conversations = {}
    try:
        conversations = await oncofiles_client.search_conversations(tags=f"sid:{sid}")
    except Exception as e:
        record_suppressed_error("review_session", "fetch_conversations", e)

    # Get suppressed errors from in-memory buffer
    suppressed = get_suppressed_errors()

    # Build timeline and stats
    entries = activity.get("entries", []) if isinstance(activity, dict) else []
    timeline = [
        {
            "tool": e.get("tool_name"),
            "status": e.get("status"),
            "duration_ms": e.get("duration_ms"),
            "input": e.get("input_summary"),
            "output": e.get("output_summary"),
            "error": e.get("error_message"),
            "timestamp": e.get("created_at"),
        }
        for e in entries
    ]

    error_entries = [e for e in entries if e.get("status") == "error"]
    durations = [e.get("duration_ms", 0) for e in entries if e.get("duration_ms")]
    tools_used = list({e.get("tool_name") for e in entries if e.get("tool_name")})

    stats = {
        "session_id": sid,
        "total_calls": len(entries),
        "errors": len(error_entries),
        "suppressed_errors": len(suppressed),
        "avg_duration_ms": int(sum(durations) / len(durations)) if durations else 0,
        "tools_used": tools_used,
    }

    # Extract session summary from conversations if available
    conv_entries = conversations.get("entries", []) if isinstance(conversations, dict) else []
    session_summary = None
    for ce in conv_entries:
        if ce.get("entry_type") == "session_summary":
            session_summary = ce.get("content")
            break

    return json.dumps({
        "timeline": timeline,
        "stats": stats,
        "errors": [
            {
                "tool": e.get("tool_name"),
                "error": e.get("error_message"),
                "timestamp": e.get("created_at"),
            }
            for e in error_entries
        ],
        "suppressed_errors": suppressed,
        "session_summary": session_summary,
    })


@mcp.tool()
@log_activity
async def create_improvement_issue(
    repo: str, title: str, body: str, labels: list[str] | None = None
) -> str:
    """Create a GitHub issue for a usage-driven improvement idea.

    Args:
        repo: GitHub repo ("instarea-sk/oncoteam" or "instarea-sk/oncofiles")
        title: Issue title (concise)
        body: Markdown body with context
        labels: GitHub labels (default: ["enhancement"])

    Returns:
        JSON with issue number and URL.
    """
    result = await github_client.create_issue(
        repo=repo,
        title=title,
        body=body,
        labels=labels or ["enhancement"],
    )
    return json.dumps(result)


# ── Health check ────────────────────────────────


@mcp.custom_route("/health", methods=["GET"])
async def health(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok", "server": "oncoteam", "version": "0.6.0"})


# ── Entry point ─────────────────────────────────


def main() -> None:
    if MCP_TRANSPORT == "stdio":
        mcp.run()
    else:
        mcp.run(transport=MCP_TRANSPORT, host=MCP_HOST, port=MCP_PORT)


if __name__ == "__main__":
    main()
