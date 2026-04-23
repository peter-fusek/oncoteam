from __future__ import annotations

import json
import logging
import os

from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

import oncoteam.dashboard_api as _dashboard_mod

from . import clinicaltrials_client, github_client, oncofiles_client, pubmed_client
from .activity_logger import (
    get_session_id,
    get_suppressed_errors,
    log_activity,
    log_to_diary,
    record_suppressed_error,
)
from .config import (
    DASHBOARD_ALLOWED_ORIGINS,
    GIT_COMMIT,
    MCP_BASE_URL,
    MCP_BEARER_TOKEN,
    MCP_HOST,
    MCP_PORT,
    MCP_TRANSPORT,
)
from .dashboard_api import (
    VERSION,
    _check_api_auth,
    api_access_rights_get,
    api_access_rights_set,
    api_activity,
    api_agent_config,
    api_agent_runs,
    api_agent_runs_all,
    api_agents,
    api_approve_user,
    api_assess_funnel,
    api_autonomous,
    api_autonomous_cost,
    api_autonomous_status,
    api_briefings,
    api_bug_report,
    api_cors_preflight,
    api_cumulative_dose,
    api_detail,
    api_diagnostics,
    api_document_webhook,
    api_documents,
    api_facts,
    api_family_update,
    api_funnel_stages_get,
    api_funnel_stages_save,
    api_health_deep,
    api_labs,
    api_log_whatsapp,
    api_medications,
    api_onboard_patient,
    api_onboarding_status,
    api_patient,
    api_patients,
    api_preventive_care,
    api_protocol,
    api_protocol_cycles,
    api_research,
    api_resolve_patient,
    api_sessions,
    api_stats,
    api_status,
    api_timeline,
    api_toxicity,
    api_trigger_agent,
    api_weight,
    api_whatsapp_chat,
    api_whatsapp_history,
    api_whatsapp_media,
    api_whatsapp_status,
    api_whatsapp_voice,
    load_approved_phones,
    load_patient_tokens,
)
from .eligibility import check_eligibility
from .models import ResearchSource
from .patient_context import (
    DEFAULT_PATIENT_ID,
    get_context_tags,
    get_genetic_profile,
    get_patient,
    get_patient_profile_text,
    get_patient_token,
    get_research_terms_text,
)
from .scheduler import start_scheduler

# ── Auth ────────────────────────────────────────
auth = None
if MCP_BASE_URL:
    from fastmcp.server.auth.auth import ClientRegistrationOptions

    from .auth_provider import FileOAuthProvider

    auth = FileOAuthProvider(
        base_url=MCP_BASE_URL,
        client_registration_options=ClientRegistrationOptions(enabled=True),
    )
elif MCP_BEARER_TOKEN:
    from fastmcp.server.auth import StaticTokenVerifier

    # Build token map: primary token maps to default patient,
    # additional MCP_BEARER_TOKEN_<ID> env vars map to specific patients.
    _mcp_tokens: dict[str, dict] = {
        MCP_BEARER_TOKEN: {"client_id": DEFAULT_PATIENT_ID, "scopes": []},
    }
    for key, val in os.environ.items():
        if key.startswith("MCP_BEARER_TOKEN_") and val:
            pid = key[len("MCP_BEARER_TOKEN_") :].lower()
            _mcp_tokens[val] = {"client_id": pid, "scopes": []}
    auth = StaticTokenVerifier(tokens=_mcp_tokens)
elif MCP_TRANSPORT != "stdio":
    raise RuntimeError(
        "MCP_BASE_URL or MCP_BEARER_TOKEN must be set for HTTP transport. "
        "Set MCP_BASE_URL for OAuth or MCP_BEARER_TOKEN for static token auth, "
        "or use MCP_TRANSPORT=stdio for local development."
    )


def _get_mcp_patient_token() -> tuple[str, str | None]:
    """Get (patient_id, token) for the current MCP session."""
    pid = _get_current_patient_id()
    return pid, get_patient_token(pid)


def _get_current_patient_id() -> str:
    """Get patient_id for the current MCP session.

    Resolves from the MCP session's bearer token via client_id claim.
    Falls back to DEFAULT_PATIENT_ID for stdio transport or unauthenticated sessions.
    """
    try:
        from fastmcp.server.dependencies import get_access_token

        token = get_access_token()
        if token and token.client_id:
            return token.client_id
    except (ImportError, RuntimeError):
        pass
    return DEFAULT_PATIENT_ID


mcp = FastMCP(
    "Oncoteam",
    instructions=(
        "Oncoteam is a persistent AI agent for cancer treatment management. "
        "It searches PubMed and ClinicalTrials.gov for relevant research, "
        "tracks treatment events, and provides lab trend analysis. "
        "All data is persisted through the Oncofiles MCP server.\n\n"
        #
        # --- BIOMARKER SAFETY ---
        #
        "BIOMARKER SAFETY:\n"
        "- ALWAYS check patient biomarkers via get_patient_context before suggesting therapies.\n"
        "- NEVER suggest therapies listed in the patient's excluded_therapies.\n"
        "- anti-EGFR eligible ONLY if KRAS WT AND NRAS WT AND BRAF WT.\n"
        "- KRAS G12C-specific inhibitors (sotorasib, adagrasib) ONLY for G12C mutations.\n"
        "- Checkpoint monotherapy ONLY for MSI-H/dMMR, NOT for pMMR/MSS.\n"
        "- Always verify biomarker status before making treatment recommendations.\n\n"
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
        "LAB PERSISTENCE — after every lab analysis:\n"
        "1. Call store_lab_values(document_id, lab_date, values_json) to persist parsed values.\n"
        "   - Extract: WBC, ABS_NEUT, ABS_LYMPH, PLT, HGB, CEA, CA19_9\n"
        "   - Compute and include: SII, NE_LY_RATIO\n"
        "2. Call get_lab_trends_by_parameter('CEA') (or other param) to compare with history.\n"
        "3. Include trend direction in your analysis (rising/stable/falling vs previous).\n\n"
        #
        # --- CLINICAL TRIAL SEARCH ---
        #
        "CLINICAL TRIAL SEARCH:\n"
        "- Search nearby countries based on patient location.\n"
        "- Eligibility check: biomarker status, comorbidities, ECOG, prior lines.\n"
        "- Use get_patient_context to get the patient's biomarkers and excluded therapies.\n"
        "- Filter trials by cancer type — exclude unrelated tumor types.\n\n"
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
        "5. Then call summarize_session() as usual.\n\n"
        #
        # --- SOURCE ATTRIBUTION RULES ---
        #
        "SOURCE ATTRIBUTION RULES:\n"
        "Every piece of information displayed to the user MUST be traceable to its source.\n\n"
        "1. Document sources: When referencing data from oncofiles documents, include the "
        "gdrive_url (computed from gdrive_file_id) so the user can open the original.\n"
        "2. Research sources: PubMed articles must link to "
        "https://pubmed.ncbi.nlm.nih.gov/{pmid}/, clinical trials to "
        "https://clinicaltrials.gov/study/{nct_id}.\n"
        "3. Lab trend sources: Each lab data point must reference the document_id "
        "(oncofiles treatment_event ID) it was extracted from.\n"
        "4. Cross-references: When multiple documents relate to the same visit or event, "
        "list them together with their types (e.g., 'Lab report + CT scan, 2026-03-01').\n"
        "5. Display strategy: Sources appear in a 'Sources' footer section. "
        "In drilldown panels, show full source chain. In summaries, show inline citations.\n"
        "6. Generated content (briefings, summaries) must include a ## Sources section "
        "listing all referenced oncofiles IDs and external URLs.\n"
        "7. If a source is unavailable or unverifiable, mark it explicitly as "
        "'[source pending]' — never silently omit attribution."
    ),
    auth=auth,
)


# ── Resources ───────────────────────────────────


@mcp.resource("oncoteam://patient-profile", description="Patient treatment profile")
def patient_profile() -> str:
    return get_patient_profile_text(_get_current_patient_id())


@mcp.resource("oncoteam://research-terms", description="Curated PubMed search terms")
def research_terms() -> str:
    return get_research_terms_text(_get_current_patient_id())


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
    _pid, _tok = _get_mcp_patient_token()
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
                token=_tok,
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
        country: Optional country filter (e.g. "Slovakia", "Czech Republic").
            When omitted, falls back to patient.home_region.country_code so
            agents default to enrollable trials instead of global sweeps (#394).

    Returns:
        JSON with list of matching clinical trials.
    """
    _pid, _tok = _get_mcp_patient_token()
    # #394: if the caller didn't specify a country, use the patient's home
    # country. Agents rarely remember to pass country when they should, and
    # a Houston-based trial for a Bratislava patient wastes tokens + signal.
    if country is None:
        try:
            _patient = get_patient(_pid)
            if _patient.home_region is not None:
                country = _patient.home_region.country
        except Exception as e:  # patient registry lookup should not break tool
            record_suppressed_error("search_clinical_trials", "home_country_resolve", e)
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
                token=_tok,
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
    _pid, _tok = _get_mcp_patient_token()
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
                tags=["res:adjacent-countries", *trial.conditions[:3]],
                raw_data=trial.model_dump_json(),
                token=_tok,
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
async def search_clinical_trials_eu(
    condition: str = "colorectal cancer",
    intervention: str | None = None,
    max_per_country: int = 3,
) -> str:
    """Search ClinicalTrials.gov across EU countries with major CRC trial activity.

    Covers: SK, CZ, AT, HU, DE, PL, IT, NL, BE, FR, DK, SE, CH.
    Searches in parallel and deduplicates by NCT ID.

    Args:
        condition: Medical condition to search for
        intervention: Optional intervention/treatment filter
        max_per_country: Maximum results per country (default 3)

    Returns:
        JSON with deduplicated trials from EU countries.
    """
    _pid, _tok = _get_mcp_patient_token()
    trials = await clinicaltrials_client.search_trials_eu(
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
                tags=["res:eu-trials", *trial.conditions[:3]],
                raw_data=trial.model_dump_json(),
                token=_tok,
            )
        except Exception as e:
            record_suppressed_error("search_clinical_trials_eu", "store_research", e)

    return json.dumps(
        {
            "condition": condition,
            "intervention": intervention,
            "countries": clinicaltrials_client.EU_TRIAL_COUNTRIES,
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
    _pid, _tok = _get_mcp_patient_token()
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
    _pid, _tok = _get_mcp_patient_token()
    trial = await clinicaltrials_client.fetch_trial(nct_id)
    if trial is None:
        return json.dumps({"error": f"Trial {nct_id} not found"})
    return json.dumps({"trial": trial.model_dump()})


@mcp.tool()
@log_activity
async def check_trial_eligibility(nct_id: str) -> str:
    """Check if a clinical trial is eligible for this patient based on biomarker rules.

    Fetches the trial from ClinicalTrials.gov and checks against the patient's
    molecular profile and excluded therapies.

    Args:
        nct_id: ClinicalTrials.gov ID (e.g. "NCT00001234")

    Returns:
        JSON with eligibility result: {eligible, flags, warnings, summary}
    """
    _pid, _tok = _get_mcp_patient_token()
    trial = await clinicaltrials_client.fetch_trial(nct_id)
    if trial is None:
        return json.dumps({"error": f"Trial {nct_id} not found"})

    patient = get_patient(_get_current_patient_id())
    result = check_eligibility(trial, patient)
    return json.dumps({"eligibility": result.model_dump()})


@mcp.tool()
@log_activity
async def daily_briefing() -> str:
    """Run preset research queries for Erika's case and compile a summary.

    Searches PubMed with curated terms and ClinicalTrials.gov for recruiting studies.

    Returns:
        JSON summary of all research findings from today's briefing.
    """
    _pid, _tok = _get_mcp_patient_token()
    results = {"pubmed": [], "clinical_trials": []}
    seen_pmids: set[str] = set()

    # PubMed searches — use top 3 terms to stay within rate limits
    from .patient_context import get_patient_research_terms

    research_terms = get_patient_research_terms(_get_current_patient_id())
    for term in research_terms[:3]:
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
                        tags=["task:daily-briefing"],
                        raw_data=article.model_dump_json(),
                        token=_tok,
                    )
                except Exception as e:
                    record_suppressed_error("daily_briefing", "store_pubmed", e)
        except Exception:
            results["pubmed"].append({"query": term, "error": "search failed"})

    # ClinicalTrials.gov — search adjacent countries using patient's diagnosis
    patient = get_patient(_get_current_patient_id())
    trial_condition = patient.diagnosis_description or "metastatic colorectal cancer"
    try:
        trials = await clinicaltrials_client.search_trials_adjacent(
            condition=trial_condition,
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
                    tags=["task:daily-briefing", "res:adjacent-countries"],
                    raw_data=trial.model_dump_json(),
                    token=_tok,
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
    _pid, _tok = _get_mcp_patient_token()
    try:
        result = await oncofiles_client.search_documents(
            text="lab", category="labs", limit=limit, token=_tok
        )
        docs = result.get("documents", []) if isinstance(result, dict) else result
        lab_data = {"documents": docs, "total": len(docs)}
        return json.dumps({"source": "oncofiles", "lab_documents": lab_data})
    except Exception as e:
        return json.dumps({"error": str(e), "hint": "Oncofiles MCP may not be available"})


@mcp.tool()
@log_activity
async def store_lab_values(document_id: int, lab_date: str, values_json: str) -> str:
    """Persist parsed lab values to Oncofiles for trend tracking.

    Call this after analyzing a lab document to store extracted values.

    Args:
        document_id: Oncofiles document ID of the source lab report
        lab_date: Date of the lab results (YYYY-MM-DD)
        values_json: JSON object with lab parameters, e.g.
            {"WBC": 5.2, "ABS_NEUT": 3.1, "ABS_LYMPH": 1.5, "PLT": 220,
             "HGB": 12.5, "CEA": 4.8, "CA19_9": 18.0, "SII": 456, "NE_LY_RATIO": 2.07}

    Returns:
        JSON confirmation of stored values.
    """
    _pid, _tok = _get_mcp_patient_token()
    try:
        result = await oncofiles_client.store_lab_values(
            document_id, lab_date, values_json, token=_tok
        )
        return json.dumps(result)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
@log_activity
async def get_lab_trends_by_parameter(parameter: str, limit: int = 20) -> str:
    """Retrieve historical lab values for a specific parameter for trend analysis.

    Args:
        parameter: Lab parameter name. One of: WBC, ABS_NEUT, ABS_LYMPH, PLT,
            HGB, CEA, CA19_9, SII, NE_LY_RATIO
        limit: Maximum number of data points to retrieve

    Returns:
        JSON with historical values sorted by date.
    """
    _pid, _tok = _get_mcp_patient_token()
    try:
        result = await oncofiles_client.get_lab_trends_data(parameter, limit, token=_tok)
        return json.dumps(result)
    except Exception as e:
        return json.dumps({"error": str(e)})


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
    _pid, _tok = _get_mcp_patient_token()
    try:
        result = await oncofiles_client.search_documents(text, category, limit=200, token=_tok)
        docs = result.get("documents", []) if isinstance(result, dict) else result
        results = {"documents": docs, "total": len(docs)}
        return json.dumps({"query": text, "category": category, "results": results})
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
@log_activity
async def get_patient_context() -> str:
    """Return the full patient treatment profile with dynamic genetic data.

    Returns:
        JSON with patient diagnosis, treatment, biomarkers (enriched from oncofiles), and hospitals.
    """
    _pid, _tok = _get_mcp_patient_token()
    patient = get_patient(_get_current_patient_id())
    data = patient.model_dump()
    try:
        genetic = await get_genetic_profile(_pid, token=_tok)
        data["biomarkers"] = genetic
    except Exception as e:
        record_suppressed_error("get_patient_context", "genetic_profile", e)
    return json.dumps(data, default=str)


@mcp.tool()
@log_activity
async def view_document(file_id: str | None = None, document_id: int | str | None = None) -> str:
    """View full document content with OCR text and images from Oncofiles.

    Args:
        file_id: The document file ID (string like "file_011CZZ...").
        document_id: Alternative — numeric document ID (resolved to file_id automatically).

    Returns:
        JSON with document content.
    """
    _pid, _tok = _get_mcp_patient_token()
    try:
        # Accept either file_id or document_id (agents may use either)
        raw_id = file_id or str(document_id or "")
        if not raw_id:
            return json.dumps({"error": "Provide file_id or document_id"})

        # If a numeric ID was passed, resolve to file_id via oncofiles
        resolved_file_id = raw_id
        stripped = raw_id.strip()
        if stripped.isdigit():
            doc = await oncofiles_client.get_document(int(stripped), token=_tok)
            if isinstance(doc, dict) and doc.get("file_id"):
                resolved_file_id = doc["file_id"]
            else:
                return json.dumps({"error": f"Could not resolve document ID {stripped} to file_id"})
        result = await oncofiles_client.view_document(resolved_file_id, token=_tok)
        return json.dumps({"file_id": resolved_file_id, "content": result})
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
    _pid, _tok = _get_mcp_patient_token()
    try:
        result = await oncofiles_client.analyze_labs(file_id, limit, token=_tok)
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
    _pid, _tok = _get_mcp_patient_token()
    try:
        result = await oncofiles_client.compare_labs(file_id_a, file_id_b, token=_tok)
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
    _pid, _tok = _get_mcp_patient_token()
    await log_to_diary(
        title=decision,
        content=reasoning,
        entry_type="decision",
        tags=tags,
        token=_tok,
    )
    return "Decision logged."


@mcp.tool()
async def funnel_propose_trial(
    nct_id: str,
    title: str = "",
    rationale: str = "",
    biomarker_match: dict | None = None,
    geographic_score: float | None = None,
    sites_in_scope: list[dict] | None = None,
    source_agent: str = "",
    source_run_id: str = "",
) -> str:
    """Post a trial to the clinical funnel PROPOSALS lane (agent-writable).

    Agents must use this tool (not log_research_decision) for every new NCT
    they discover. The proposals lane is reviewed by a physician before any
    trial enters the clinical funnel — AI proposes, humans dispose (#395).

    Re-surfacing: if the NCT is already on the board (any lane, any stage,
    even archived), this tool records a `re_surfaced` audit event on the
    existing card instead of creating a duplicate. Physicians see a
    "previously seen" warning so nothing slips through.

    Args:
        nct_id: ClinicalTrials.gov identifier (required).
        title: Short trial title.
        rationale: Why this trial matches the patient — biomarker / geography / line fit.
        biomarker_match: Dict of marker→match status (e.g. {"ATM": "biallelic", "KRAS": "G12S"}).
        geographic_score: 0.0–1.0 proximity score from the enrollment geography pass (#394).
        sites_in_scope: List of enrollable sites with facility/city/country/status.
        source_agent: Name of the scanning agent (e.g. "ddr_monitor", "trial_monitor").
        source_run_id: Unique run identifier for audit traceability.
    """
    from .funnel_audit import create_agent_proposal

    _pid, _tok = _get_mcp_patient_token()
    result = await create_agent_proposal(
        patient_id=_pid,
        nct_id=nct_id.strip().upper(),
        title=title,
        source_agent=source_agent or "mcp_agent",
        source_run_id=source_run_id,
        biomarker_match=biomarker_match,
        geographic_score=geographic_score,
        sites_in_scope=sites_in_scope,
        rationale=rationale,
        actor_id=source_agent or "mcp_agent",
        actor_display_name=source_agent or "mcp_agent",
        token=_tok,
    )
    return json.dumps(result)


@mcp.tool()
async def log_session_note(note: str, tags: list[str] | None = None) -> str:
    """Record an observation, context note, or diary entry.

    Use this to capture important observations, session summaries, or
    contextual information worth preserving.

    Args:
        note: The note content
        tags: Optional tags for categorization
    """
    _pid, _tok = _get_mcp_patient_token()
    await log_to_diary(
        title=note[:100],
        content=note,
        entry_type="note",
        tags=tags,
        token=_tok,
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
    _pid, _tok = _get_mcp_patient_token()
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
        tags=["sys:session"],
        token=_tok,
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
    _pid, _tok = _get_mcp_patient_token()
    sid = session_id or get_session_id()

    # Fetch activity log for this session
    activity = {}
    try:
        activity = await oncofiles_client.search_activity_log(session_id=sid, token=_tok)
    except Exception as e:
        record_suppressed_error("review_session", "fetch_activity", e)

    # Fetch session conversations
    conversations = {}
    try:
        conversations = await oncofiles_client.search_conversations(tags=f"sid:{sid}", token=_tok)
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

    return json.dumps(
        {
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
        }
    )


@mcp.tool()
@log_activity
async def create_improvement_issue(
    repo: str, title: str, body: str, labels: list[str] | None = None
) -> str:
    """Create a GitHub issue for a usage-driven improvement idea.

    Args:
        repo: GitHub repo ("peter-fusek/oncoteam" or "peter-fusek/oncofiles")
        title: Issue title (concise)
        body: Markdown body with context
        labels: GitHub labels (default: ["enhancement"])

    Returns:
        JSON with issue number and URL.
    """
    _pid, _tok = _get_mcp_patient_token()
    result = await github_client.create_issue(
        repo=repo,
        title=title,
        body=body,
        labels=labels or ["enhancement"],
    )
    return json.dumps(result)


@mcp.tool()
@log_activity
async def get_lab_safety_check() -> str:
    """Pre-cycle lab safety check against mFOLFOX6 thresholds.

    Returns green/yellow/red/missing status per parameter (ANC, PLT, HGB, WBC,
    bilirubin, creatinine, ALT, AST, eGFR) with NCCN/SmPC source attribution.
    """
    _pid, _tok = _get_mcp_patient_token()
    result = await oncofiles_client.get_lab_safety_check(token=_tok)
    return json.dumps(result) if isinstance(result, dict) else str(result)


@mcp.tool()
@log_activity
async def get_precycle_checklist(cycle_number: int = 3) -> str:
    """Full pre-cycle checklist: lab safety + toxicity assessment + VTE monitoring.

    Args:
        cycle_number: Current cycle number (default: 3).

    Returns:
        Checklist with guideline source URLs per item. Lab items auto-populate
        with latest patient values.
    """
    _pid, _tok = _get_mcp_patient_token()
    result = await oncofiles_client.get_precycle_checklist(cycle_number, token=_tok)
    return json.dumps(result) if isinstance(result, dict) else str(result)


@mcp.tool()
@log_activity
async def get_clinical_protocol(section: str | None = None, lang: str = "en") -> str:
    """Get the clinical protocol data (thresholds, dose mods, milestones, etc.).

    Returns the full mFOLFOX6 protocol as structured JSON, or a single section.
    Useful for external agents and clients that need protocol data without
    importing Python code.

    Args:
        section: Optional section filter. One of: lab_thresholds, reference_ranges,
            health_direction, dose_modifications, milestones, monitoring_schedule,
            watched_trials, second_line_options, cumulative_dose, cycle_delay_rules,
            nutrition_escalation, safety_flags. Returns all sections if not specified.
        lang: Language for bilingual content ('sk' or 'en', default 'en').
    """
    _pid, _tok = _get_mcp_patient_token()
    from .clinical_protocol import PROTOCOL_SECTIONS, resolve_protocol
    from .general_health_protocol import resolve_general_health_protocol
    from .patient_context import get_patient, is_general_health_patient

    patient = get_patient(_pid)
    if is_general_health_patient(patient):
        protocol = resolve_general_health_protocol(lang)
    else:
        protocol = resolve_protocol(lang)
    if section:
        if section not in PROTOCOL_SECTIONS:
            return json.dumps(
                {"error": f"Unknown section: {section}", "available": sorted(PROTOCOL_SECTIONS)}
            )
        return json.dumps({section: protocol[section]}, default=str)
    return json.dumps(protocol, default=str)


# ── Multi-patient tools ────────────────────────────


@mcp.tool()
@log_activity
async def list_patients() -> str:
    """List all active patients with document counts and current selection.

    Returns:
        JSON array of patients with slug, name, doc_count, patient_type,
        and is_current flag.
    """
    _pid, _tok = _get_mcp_patient_token()
    try:
        result = await oncofiles_client.list_patients(token=_tok)
        return json.dumps(result, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
@log_activity
async def select_patient(patient_slug: str) -> str:
    """Switch the active patient for this session.

    All subsequent tool calls will return data for the selected patient.
    Pass slug (e.g. 'q1b', 'e5g') or UUID.

    Args:
        patient_slug: Patient slug or UUID to switch to.

    Returns:
        JSON with switch confirmation, patient slug, and document count.
    """
    _pid, _tok = _get_mcp_patient_token()
    try:
        result = await oncofiles_client.select_patient(patient_slug, token=_tok)
        return json.dumps(result, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})


# ── Health check ────────────────────────────────


@mcp.custom_route("/health", methods=["GET"])
async def health(request: Request) -> JSONResponse:
    from .config import AUTONOMOUS_ENABLED
    from .scheduler import get_scheduler_status

    sched = get_scheduler_status()
    data: dict = {
        "status": "ok",
        "server": "oncoteam",
        "version": VERSION,
    }
    # Include detailed info only for authenticated requests
    auth = request.headers.get("authorization", "")
    from .config import DASHBOARD_API_KEY

    if auth.startswith("Bearer ") and DASHBOARD_API_KEY and auth[7:] == DASHBOARD_API_KEY:
        data["commit"] = GIT_COMMIT
        data["autonomous_enabled"] = AUTONOMOUS_ENABLED
        data["scheduler"] = sched
    else:
        data["scheduler"] = {"running": sched.get("running", False), "jobs": sched.get("jobs", 0)}
    return JSONResponse(data)


mcp.custom_route("/health/deep", methods=["GET"])(api_health_deep)


# ── Dashboard API routes ────────────────────────

_API_ROUTES = [
    ("/api/status", api_status),
    ("/api/activity", api_activity),
    ("/api/stats", api_stats),
    ("/api/timeline", api_timeline),
    ("/api/facts", api_facts),
    ("/api/patient", api_patient),
    ("/api/research", api_research),
    ("/api/sessions", api_sessions),
    ("/api/autonomous", api_autonomous),
    ("/api/autonomous/cost", api_autonomous_cost),
    ("/api/autonomous/status", api_autonomous_status),
    ("/api/protocol", api_protocol),
    ("/api/protocol/cycles", api_protocol_cycles),
    ("/api/briefings", api_briefings),
    ("/api/toxicity", api_toxicity),
    ("/api/labs", api_labs),
    ("/api/diagnostics", api_diagnostics),
    ("/api/documents", api_documents),
    ("/api/medications", api_medications),
    ("/api/preventive-care", api_preventive_care),
    ("/api/weight", api_weight),
    ("/api/family-update", api_family_update),
    ("/api/cumulative-dose", api_cumulative_dose),
    ("/api/agents", api_agents),
    ("/api/patients", api_patients),
    ("/api/whatsapp/status", api_whatsapp_status),
    ("/api/whatsapp/history", api_whatsapp_history),
]

_POST_ROUTES = {"/api/toxicity", "/api/labs", "/api/medications", "/api/family-update"}


def _auth_wrap(handler):
    """Wrap an API handler with auth check and CORS origin tracking."""

    async def wrapper(request: Request) -> JSONResponse:
        err = _check_api_auth(request)
        if err is not None:
            return err
        _token = _dashboard_mod._CURRENT_REQUEST.set(request)
        try:
            return await handler(request)
        finally:
            _dashboard_mod._CURRENT_REQUEST.reset(_token)

    wrapper.__name__ = handler.__name__
    return wrapper


for _path, _handler in _API_ROUTES:
    mcp.custom_route(_path, methods=["GET"])(_auth_wrap(_handler))
    if _path in _POST_ROUTES:
        mcp.custom_route(_path, methods=["POST"])(_auth_wrap(_handler))
    mcp.custom_route(_path, methods=["OPTIONS"])(api_cors_preflight)

# Parameterized routes (can't go in the loop above)
mcp.custom_route("/api/detail/{type}/{id}", methods=["GET"])(_auth_wrap(api_detail))
mcp.custom_route("/api/detail/{type}/{id}", methods=["OPTIONS"])(api_cors_preflight)
mcp.custom_route("/api/agent-runs", methods=["GET"])(_auth_wrap(api_agent_runs_all))
mcp.custom_route("/api/agent-runs", methods=["OPTIONS"])(api_cors_preflight)
mcp.custom_route("/api/agents/{id}/runs", methods=["GET"])(_auth_wrap(api_agent_runs))
mcp.custom_route("/api/agents/{id}/runs", methods=["OPTIONS"])(api_cors_preflight)
mcp.custom_route("/api/agents/{id}/config", methods=["GET"])(_auth_wrap(api_agent_config))
mcp.custom_route("/api/agents/{id}/config", methods=["OPTIONS"])(api_cors_preflight)

# Internal API routes (POST-only, used by dashboard webhook)
mcp.custom_route("/api/internal/log-whatsapp", methods=["POST"])(_auth_wrap(api_log_whatsapp))
mcp.custom_route("/api/internal/log-whatsapp", methods=["OPTIONS"])(api_cors_preflight)
mcp.custom_route("/api/internal/whatsapp-chat", methods=["POST"])(_auth_wrap(api_whatsapp_chat))
mcp.custom_route("/api/internal/whatsapp-chat", methods=["OPTIONS"])(api_cors_preflight)
mcp.custom_route("/api/internal/resolve-patient", methods=["POST"])(_auth_wrap(api_resolve_patient))
mcp.custom_route("/api/internal/resolve-patient", methods=["OPTIONS"])(api_cors_preflight)
_doc_webhook = _auth_wrap(api_document_webhook)
mcp.custom_route("/api/internal/document-webhook", methods=["POST"])(_doc_webhook)
mcp.custom_route("/api/internal/document-webhook", methods=["OPTIONS"])(api_cors_preflight)
_trigger_agent = _auth_wrap(api_trigger_agent)
mcp.custom_route("/api/internal/trigger-agent", methods=["POST"])(_trigger_agent)
mcp.custom_route("/api/internal/trigger-agent", methods=["OPTIONS"])(api_cors_preflight)
_whatsapp_media = _auth_wrap(api_whatsapp_media)
mcp.custom_route("/api/internal/whatsapp-media", methods=["POST"])(_whatsapp_media)
mcp.custom_route("/api/internal/whatsapp-media", methods=["OPTIONS"])(api_cors_preflight)
_whatsapp_voice = _auth_wrap(api_whatsapp_voice)
mcp.custom_route("/api/internal/whatsapp-voice", methods=["POST"])(_whatsapp_voice)
mcp.custom_route("/api/internal/whatsapp-voice", methods=["OPTIONS"])(api_cors_preflight)
_onboard_patient = _auth_wrap(api_onboard_patient)
mcp.custom_route("/api/internal/onboard-patient", methods=["POST"])(_onboard_patient)
mcp.custom_route("/api/internal/onboard-patient", methods=["OPTIONS"])(api_cors_preflight)
_onboarding_status = _auth_wrap(api_onboarding_status)
mcp.custom_route("/api/internal/onboarding-status", methods=["POST"])(_onboarding_status)
mcp.custom_route("/api/internal/onboarding-status", methods=["OPTIONS"])(api_cors_preflight)
_approve_user = _auth_wrap(api_approve_user)
mcp.custom_route("/api/internal/approve-user", methods=["POST"])(_approve_user)
mcp.custom_route("/api/internal/approve-user", methods=["OPTIONS"])(api_cors_preflight)
mcp.custom_route("/api/internal/access-rights", methods=["GET"])(_auth_wrap(api_access_rights_get))
mcp.custom_route("/api/internal/access-rights", methods=["POST"])(_auth_wrap(api_access_rights_set))
mcp.custom_route("/api/internal/access-rights", methods=["OPTIONS"])(api_cors_preflight)
mcp.custom_route("/api/bug-report", methods=["POST"])(_auth_wrap(api_bug_report))
mcp.custom_route("/api/bug-report", methods=["OPTIONS"])(api_cors_preflight)
mcp.custom_route("/api/research/assess-funnel", methods=["POST"])(_auth_wrap(api_assess_funnel))
mcp.custom_route("/api/research/assess-funnel", methods=["OPTIONS"])(api_cors_preflight)
# Clinical funnel two-lane API (#395)
from .api_funnel import (  # noqa: E402
    api_funnel_audit_for_card,
    api_funnel_audit_for_patient,
    api_funnel_cards_get,
    api_funnel_cards_post,
    api_funnel_proposals_get,
    api_funnel_proposals_post,
)

mcp.custom_route("/api/funnel/proposals", methods=["GET"])(_auth_wrap(api_funnel_proposals_get))
mcp.custom_route("/api/funnel/proposals", methods=["POST"])(_auth_wrap(api_funnel_proposals_post))
mcp.custom_route("/api/funnel/proposals", methods=["OPTIONS"])(api_cors_preflight)
mcp.custom_route("/api/funnel/cards", methods=["GET"])(_auth_wrap(api_funnel_cards_get))
mcp.custom_route("/api/funnel/cards", methods=["POST"])(_auth_wrap(api_funnel_cards_post))
mcp.custom_route("/api/funnel/cards", methods=["OPTIONS"])(api_cors_preflight)
mcp.custom_route("/api/funnel/audit/patient", methods=["GET"])(
    _auth_wrap(api_funnel_audit_for_patient)
)
mcp.custom_route("/api/funnel/audit/patient", methods=["OPTIONS"])(api_cors_preflight)
mcp.custom_route("/api/funnel/audit/{card_id}", methods=["GET"])(
    _auth_wrap(api_funnel_audit_for_card)
)
mcp.custom_route("/api/funnel/audit/{card_id}", methods=["OPTIONS"])(api_cors_preflight)

mcp.custom_route("/api/research/funnel-stages", methods=["GET"])(_auth_wrap(api_funnel_stages_get))
mcp.custom_route("/api/research/funnel-stages", methods=["POST"])(
    _auth_wrap(api_funnel_stages_save)
)
mcp.custom_route("/api/research/funnel-stages", methods=["OPTIONS"])(api_cors_preflight)


# ── Entry point ─────────────────────────────────


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    if MCP_TRANSPORT == "stdio":
        start_scheduler()
        mcp.run()
    else:
        import asyncio

        from starlette.middleware import Middleware
        from starlette.middleware.cors import CORSMiddleware
        from starlette.types import ASGIApp, Receive, Scope, Send

        class SecurityHeadersMiddleware:
            """Add standard security headers to all HTTP responses."""

            def __init__(self, app: ASGIApp) -> None:
                self.app = app

            async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
                if scope["type"] != "http":
                    await self.app(scope, receive, send)
                    return

                async def send_with_headers(message: dict) -> None:
                    if message["type"] == "http.response.start":
                        security = [
                            (b"x-content-type-options", b"nosniff"),
                            (b"x-frame-options", b"DENY"),
                            (b"referrer-policy", b"strict-origin-when-cross-origin"),
                            (b"strict-transport-security", b"max-age=31536000; includeSubDomains"),
                        ]
                        existing = message.get("headers", [])
                        message["headers"] = list(existing) + security
                    await send(message)

                await self.app(scope, receive, send_with_headers)

        async def _run_http():
            # FastMCP 3.x lifespan is broken in HTTP transport (double-wrap bug).
            # Start the autonomous scheduler explicitly within the event loop.
            start_scheduler()

            # Non-critical startup I/O: loading persisted state from oncofiles.
            # MUST NOT block server startup — when oncofiles is down, waiting
            # for these would delay port-binding past Railway's healthcheck
            # window, Railway marks the deploy FAILED, and oncoteam goes down
            # even though nothing's wrong with its own code. Treat oncofiles
            # as a peer service: we notify the user via degraded-state banners
            # (#424 circuit-breaker UI), but we BOOT regardless.
            #
            # Fire-and-forget: each task has its own short timeout + try/except
            # inside; the top-level create_task ensures the await in this
            # function returns immediately so mcp.run_async binds the port.
            async def _safe_bg(coro, label):
                try:
                    await asyncio.wait_for(coro, timeout=8.0)
                except TimeoutError:
                    logging.warning(
                        "%s timed out at startup — proceeding with empty state. "
                        "Will retry on first live request.",
                        label,
                    )
                except Exception as e:
                    logging.warning("%s failed at startup: %s", label, e)

            asyncio.create_task(_safe_bg(load_approved_phones(), "load_approved_phones"))
            asyncio.create_task(_safe_bg(load_patient_tokens(), "load_patient_tokens"))

            await mcp.run_async(
                transport=MCP_TRANSPORT,
                host=MCP_HOST,
                port=MCP_PORT,
                middleware=[
                    Middleware(SecurityHeadersMiddleware),
                    Middleware(
                        CORSMiddleware,
                        allow_origins=DASHBOARD_ALLOWED_ORIGINS or ["*"],
                        allow_credentials=False,
                        allow_methods=["GET", "POST", "OPTIONS", "DELETE"],
                        allow_headers=["Authorization", "Content-Type", "mcp-protocol-version"],
                    ),
                ],
            )

        asyncio.run(_run_http())


if __name__ == "__main__":
    main()
