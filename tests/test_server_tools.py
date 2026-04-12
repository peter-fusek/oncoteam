"""Tests for server.py MCP tool functions.

Covers all 6 tools: search_pubmed, search_clinical_trials, daily_briefing,
get_lab_trends, search_documents, get_patient_context.

Mocks external clients (pubmed, clinicaltrials, oncofiles) at module level
so we test the tool-layer logic: JSON formatting, oncofiles storage, error handling.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from oncoteam.models import ClinicalTrial, PubMedArticle
from oncoteam.server import (
    analyze_labs,
    check_trial_eligibility,
    compare_labs,
    daily_briefing,
    fetch_pubmed_article,
    fetch_trial_details,
    get_lab_trends,
    get_patient_context,
    log_research_decision,
    log_session_note,
    search_clinical_trials,
    search_documents,
    search_pubmed,
    summarize_session,
    view_document,
)

# ── Mock data ──────────────────────────────────────


@pytest.fixture(autouse=True)
def _mock_mcp_patient_token():
    """MCP tools resolve patient from bearer token — mock to return q1b/None."""
    with patch("oncoteam.server._get_mcp_patient_token", return_value=("q1b", None)):
        yield


MOCK_ARTICLES = [
    PubMedArticle(
        pmid="12345678",
        title="FOLFOX in colorectal cancer",
        abstract="A study on FOLFOX efficacy in sigmoid colon cancer.",
        authors=["John Smith"],
        journal="Journal of Oncology",
        pub_date="2025-06",
        doi="10.1234/test",
    ),
    PubMedArticle(
        pmid="87654321",
        title="Oxaliplatin neurotoxicity",
    ),
]

MOCK_TRIALS = [
    ClinicalTrial(
        nct_id="NCT00001234",
        title="FOLFOX Plus Immunotherapy",
        status="RECRUITING",
        phase="PHASE3",
        conditions=["Colorectal Cancer"],
        interventions=["FOLFOX", "Pembrolizumab"],
        summary="A phase 3 trial combining FOLFOX with immunotherapy.",
    ),
]

MOCK_ONCOFILES_DOCS = {
    "documents": [
        {"id": 1, "title": "Blood work 2025-01", "category": "labs"},
        {"id": 2, "title": "CBC results", "category": "labs"},
    ]
}


# ── search_pubmed ──────────────────────────────────


class TestSearchPubmedTool:
    @pytest.mark.asyncio
    @patch("oncoteam.oncofiles_client.add_research_entry", new_callable=AsyncMock)
    @patch("oncoteam.pubmed_client.search_pubmed", new_callable=AsyncMock)
    async def test_returns_articles_json(self, mock_search, mock_store):
        mock_search.return_value = MOCK_ARTICLES

        result = json.loads(await search_pubmed("colorectal cancer", max_results=5))

        assert result["query"] == "colorectal cancer"
        assert result["count"] == 2
        assert len(result["articles"]) == 2
        assert result["articles"][0]["pmid"] == "12345678"
        assert result["articles"][0]["title"] == "FOLFOX in colorectal cancer"
        mock_search.assert_called_once_with("colorectal cancer", 5)

    @pytest.mark.asyncio
    @patch("oncoteam.oncofiles_client.add_research_entry", new_callable=AsyncMock)
    @patch("oncoteam.pubmed_client.search_pubmed", new_callable=AsyncMock)
    async def test_stores_each_article_in_oncofiles(self, mock_search, mock_store):
        mock_search.return_value = MOCK_ARTICLES

        await search_pubmed("colorectal cancer")

        assert mock_store.call_count == 2
        first_call = mock_store.call_args_list[0]
        assert first_call.kwargs["source"] == "pubmed"
        assert first_call.kwargs["external_id"] == "12345678"
        assert first_call.kwargs["title"] == "FOLFOX in colorectal cancer"
        # Tags should come from patient context, not hardcoded
        tags = first_call.kwargs["tags"]
        assert any("FOLFOX" in t for t in tags)
        assert isinstance(tags, list)

    @pytest.mark.asyncio
    @patch("oncoteam.oncofiles_client.add_research_entry", new_callable=AsyncMock)
    @patch("oncoteam.pubmed_client.search_pubmed", new_callable=AsyncMock)
    async def test_empty_results(self, mock_search, mock_store):
        mock_search.return_value = []

        result = json.loads(await search_pubmed("nonexistent query"))

        assert result["count"] == 0
        assert result["articles"] == []
        mock_store.assert_not_called()

    @pytest.mark.asyncio
    @patch(
        "oncoteam.oncofiles_client.add_research_entry",
        new_callable=AsyncMock,
        side_effect=Exception("storage failed"),
    )
    @patch("oncoteam.pubmed_client.search_pubmed", new_callable=AsyncMock)
    async def test_continues_when_storage_fails(self, mock_search, mock_store):
        mock_search.return_value = MOCK_ARTICLES

        result = json.loads(await search_pubmed("colorectal cancer"))

        # Search succeeds despite oncofiles storage failure
        assert result["count"] == 2
        assert len(result["articles"]) == 2


# ── search_clinical_trials ─────────────────────────


class TestSearchClinicalTrialsTool:
    @pytest.mark.asyncio
    @patch("oncoteam.oncofiles_client.add_research_entry", new_callable=AsyncMock)
    @patch("oncoteam.clinicaltrials_client.search_trials", new_callable=AsyncMock)
    async def test_returns_trials_json(self, mock_search, mock_store):
        mock_search.return_value = MOCK_TRIALS

        result = json.loads(await search_clinical_trials("colorectal cancer", "FOLFOX", 10))

        assert result["condition"] == "colorectal cancer"
        assert result["intervention"] == "FOLFOX"
        assert result["count"] == 1
        assert result["trials"][0]["nct_id"] == "NCT00001234"
        mock_search.assert_called_once_with("colorectal cancer", "FOLFOX", 10, None)

    @pytest.mark.asyncio
    @patch("oncoteam.oncofiles_client.add_research_entry", new_callable=AsyncMock)
    @patch("oncoteam.clinicaltrials_client.search_trials", new_callable=AsyncMock)
    async def test_stores_in_oncofiles(self, mock_search, mock_store):
        mock_search.return_value = MOCK_TRIALS

        await search_clinical_trials("colorectal cancer")

        assert mock_store.call_count == 1
        first_call = mock_store.call_args_list[0]
        assert first_call.kwargs["source"] == "clinicaltrials"
        assert first_call.kwargs["external_id"] == "NCT00001234"

    @pytest.mark.asyncio
    @patch("oncoteam.oncofiles_client.add_research_entry", new_callable=AsyncMock)
    @patch("oncoteam.clinicaltrials_client.search_trials", new_callable=AsyncMock)
    async def test_empty_results(self, mock_search, mock_store):
        mock_search.return_value = []

        result = json.loads(await search_clinical_trials("nonexistent condition"))

        assert result["count"] == 0
        assert result["trials"] == []
        mock_store.assert_not_called()

    @pytest.mark.asyncio
    @patch(
        "oncoteam.oncofiles_client.add_research_entry",
        new_callable=AsyncMock,
        side_effect=Exception("storage failed"),
    )
    @patch("oncoteam.clinicaltrials_client.search_trials", new_callable=AsyncMock)
    async def test_continues_when_storage_fails(self, mock_search, mock_store):
        mock_search.return_value = MOCK_TRIALS

        result = json.loads(await search_clinical_trials("colorectal cancer"))

        assert result["count"] == 1


# ── daily_briefing ─────────────────────────────────


class TestDailyBriefingTool:
    @pytest.mark.asyncio
    @patch("oncoteam.oncofiles_client.add_research_entry", new_callable=AsyncMock)
    @patch("oncoteam.clinicaltrials_client.search_trials_adjacent", new_callable=AsyncMock)
    @patch("oncoteam.pubmed_client.search_pubmed", new_callable=AsyncMock)
    async def test_compiles_full_briefing(self, mock_pubmed, mock_ct, mock_store):
        mock_pubmed.return_value = MOCK_ARTICLES
        mock_ct.return_value = MOCK_TRIALS

        result = json.loads(await daily_briefing())

        assert result["briefing"] == "daily"
        assert result["pubmed_articles"] > 0
        assert result["clinical_trials"] > 0
        # Uses top 3 RESEARCH_TERMS
        assert mock_pubmed.call_count == 3
        # Each call uses max_results=5
        for call in mock_pubmed.call_args_list:
            assert call.kwargs.get("max_results", call.args[1] if len(call.args) > 1 else None) == 5

    @pytest.mark.asyncio
    @patch("oncoteam.oncofiles_client.add_research_entry", new_callable=AsyncMock)
    @patch("oncoteam.clinicaltrials_client.search_trials_adjacent", new_callable=AsyncMock)
    @patch("oncoteam.pubmed_client.search_pubmed", new_callable=AsyncMock)
    async def test_handles_all_searches_failing(self, mock_pubmed, mock_ct, mock_store):
        mock_pubmed.side_effect = Exception("PubMed down")
        mock_ct.side_effect = Exception("ClinicalTrials down")

        result = json.loads(await daily_briefing())

        assert result["briefing"] == "daily"
        # All 3 PubMed searches should produce error entries
        pubmed_errors = [r for r in result["results"]["pubmed"] if "error" in r]
        assert len(pubmed_errors) == 3
        # ClinicalTrials should also have error
        ct_errors = [r for r in result["results"]["clinical_trials"] if "error" in r]
        assert len(ct_errors) == 1

    @pytest.mark.asyncio
    @patch("oncoteam.oncofiles_client.add_research_entry", new_callable=AsyncMock)
    @patch("oncoteam.clinicaltrials_client.search_trials_adjacent", new_callable=AsyncMock)
    @patch("oncoteam.pubmed_client.search_pubmed", new_callable=AsyncMock)
    async def test_stores_results_in_oncofiles(self, mock_pubmed, mock_ct, mock_store):
        mock_pubmed.return_value = MOCK_ARTICLES
        mock_ct.return_value = MOCK_TRIALS

        await daily_briefing()

        # 2 unique articles (deduped across 3 searches) + 1 trial = 3 storage calls
        assert mock_store.call_count == 3
        # All storage calls should have "task:daily-briefing" tag
        for call in mock_store.call_args_list:
            assert "task:daily-briefing" in call.kwargs["tags"]


# ── get_lab_trends ─────────────────────────────────


class TestGetLabTrendsTool:
    @pytest.mark.asyncio
    @patch("oncoteam.oncofiles_client.search_documents", new_callable=AsyncMock)
    async def test_returns_lab_documents(self, mock_search):
        mock_search.return_value = MOCK_ONCOFILES_DOCS

        result = json.loads(await get_lab_trends(limit=5))

        assert result["source"] == "oncofiles"
        assert len(result["lab_documents"]["documents"]) == 2
        mock_search.assert_called_once_with(text="lab", category="labs", limit=5, token=None)

    @pytest.mark.asyncio
    @patch(
        "oncoteam.oncofiles_client.search_documents",
        new_callable=AsyncMock,
        side_effect=Exception("connection refused"),
    )
    async def test_returns_error_when_oncofiles_unavailable(self, mock_search):
        result = json.loads(await get_lab_trends())

        assert "error" in result
        assert "hint" in result
        assert "Oncofiles" in result["hint"]


# ── search_documents ───────────────────────────────


class TestSearchDocumentsTool:
    @pytest.mark.asyncio
    @patch("oncoteam.oncofiles_client.search_documents", new_callable=AsyncMock)
    async def test_returns_documents(self, mock_search):
        mock_search.return_value = MOCK_ONCOFILES_DOCS

        result = json.loads(await search_documents("lab report", "labs"))

        assert result["query"] == "lab report"
        assert result["category"] == "labs"
        assert "results" in result
        mock_search.assert_called_once_with("lab report", "labs", limit=200, token=None)

    @pytest.mark.asyncio
    @patch("oncoteam.oncofiles_client.search_documents", new_callable=AsyncMock)
    async def test_works_without_category(self, mock_search):
        mock_search.return_value = {"documents": []}

        result = json.loads(await search_documents("blood work"))

        assert result["query"] == "blood work"
        assert result["category"] is None
        mock_search.assert_called_once_with("blood work", None, limit=200, token=None)

    @pytest.mark.asyncio
    @patch(
        "oncoteam.oncofiles_client.search_documents",
        new_callable=AsyncMock,
        side_effect=Exception("timeout"),
    )
    async def test_returns_error_on_failure(self, mock_search):
        result = json.loads(await search_documents("blood work"))

        assert "error" in result


# ── get_patient_context ────────────────────────────


class TestGetPatientContextTool:
    @pytest.mark.asyncio
    async def test_returns_patient_profile(self):
        result = json.loads(await get_patient_context())

        assert result["name"] == "Erika F."
        assert result["diagnosis_code"] == "C18.7"
        assert "FOLFOX" in result["treatment_regimen"]
        assert "HER2" in result["biomarkers"]
        assert "KRAS" in result["biomarkers"]

    @pytest.mark.asyncio
    async def test_includes_hospitals_and_tumor_site(self):
        result = json.loads(await get_patient_context())

        assert result["tumor_site"] == "Sigmoid colon"
        assert len(result["hospitals"]) == 2
        assert any("NOU" in h for h in result["hospitals"])


# ── log_research_decision ────────────────────────


class TestLogResearchDecisionTool:
    @pytest.mark.asyncio
    @patch("oncoteam.server.log_to_diary", new_callable=AsyncMock)
    async def test_logs_decision(self, mock_diary):
        result = await log_research_decision(
            "Switch to CAPOX", "Lower neurotoxicity risk", tags=["treatment"]
        )

        assert result == "Decision logged."
        mock_diary.assert_called_once_with(
            title="Switch to CAPOX",
            content="Lower neurotoxicity risk",
            entry_type="decision",
            tags=["treatment"],
            token=None,
        )


# ── log_session_note ─────────────────────────────


class TestLogSessionNoteTool:
    @pytest.mark.asyncio
    @patch("oncoteam.server.log_to_diary", new_callable=AsyncMock)
    async def test_logs_note(self, mock_diary):
        result = await log_session_note("Patient tolerating treatment well", tags=["observation"])

        assert result == "Note logged."
        mock_diary.assert_called_once_with(
            title="Patient tolerating treatment well",
            content="Patient tolerating treatment well",
            entry_type="note",
            tags=["observation"],
            token=None,
        )

    @pytest.mark.asyncio
    @patch("oncoteam.server.log_to_diary", new_callable=AsyncMock)
    async def test_truncates_title_to_100_chars(self, mock_diary):
        long_note = "A" * 200

        await log_session_note(long_note)

        kwargs = mock_diary.call_args.kwargs
        assert len(kwargs["title"]) == 100
        assert kwargs["content"] == long_note


# ── summarize_session ──────────────────────────────


class TestSummarizeSessionTool:
    @pytest.mark.asyncio
    @patch("oncoteam.server.log_to_diary", new_callable=AsyncMock)
    async def test_logs_basic_summary(self, mock_diary):
        result = await summarize_session("Reviewed lab results and discussed treatment")

        assert result == "Session summary logged."
        mock_diary.assert_called_once()
        kwargs = mock_diary.call_args.kwargs
        assert kwargs["entry_type"] == "session_summary"
        assert "sys:session" in kwargs["tags"]
        assert "Reviewed lab results" in kwargs["content"]

    @pytest.mark.asyncio
    @patch("oncoteam.server.log_to_diary", new_callable=AsyncMock)
    async def test_includes_decisions_and_follow_ups(self, mock_diary):
        result = await summarize_session(
            "Treatment review",
            decisions=["Continue FOLFOX cycle 4"],
            follow_ups=["Schedule CT scan", "Check CEA levels"],
        )

        assert result == "Session summary logged."
        content = mock_diary.call_args.kwargs["content"]
        assert "Continue FOLFOX cycle 4" in content
        assert "Schedule CT scan" in content
        assert "Check CEA levels" in content

    @pytest.mark.asyncio
    @patch("oncoteam.server.log_to_diary", new_callable=AsyncMock)
    async def test_truncates_title(self, mock_diary):
        long_summary = "A" * 200
        await summarize_session(long_summary)

        title = mock_diary.call_args.kwargs["title"]
        # "Session: " (9 chars) + 80 chars = 89 max
        assert len(title) <= 89

    @pytest.mark.asyncio
    @patch("oncoteam.server.log_to_diary", new_callable=AsyncMock)
    async def test_works_without_optional_params(self, mock_diary):
        await summarize_session("Quick check-in")

        kwargs = mock_diary.call_args.kwargs
        assert kwargs["content"] == "Quick check-in"


# ── view_document ──────────────────────────────────


class TestViewDocumentTool:
    @pytest.mark.asyncio
    @patch("oncoteam.oncofiles_client.view_document", new_callable=AsyncMock)
    async def test_returns_document_content(self, mock_view):
        mock_view.return_value = {"text": "OCR content here", "images": []}

        result = json.loads(await view_document("abc123"))

        assert result["file_id"] == "abc123"
        assert result["content"]["text"] == "OCR content here"
        mock_view.assert_called_once_with("abc123", token=None)

    @pytest.mark.asyncio
    @patch(
        "oncoteam.oncofiles_client.view_document",
        new_callable=AsyncMock,
        side_effect=Exception("not found"),
    )
    async def test_returns_error_on_failure(self, mock_view):
        result = json.loads(await view_document("bad_id"))

        assert "error" in result


# ── analyze_labs ───────────────────────────────────


class TestAnalyzeLabsTool:
    @pytest.mark.asyncio
    @patch("oncoteam.oncofiles_client.analyze_labs", new_callable=AsyncMock)
    async def test_returns_analysis(self, mock_analyze):
        mock_analyze.return_value = {"summary": "Normal ranges"}

        result = json.loads(await analyze_labs(file_id="abc123", limit=5))

        assert result["analysis"]["summary"] == "Normal ranges"
        mock_analyze.assert_called_once_with("abc123", 5, token=None)

    @pytest.mark.asyncio
    @patch("oncoteam.oncofiles_client.analyze_labs", new_callable=AsyncMock)
    async def test_works_without_file_id(self, mock_analyze):
        mock_analyze.return_value = {"summary": "All labs"}

        result = json.loads(await analyze_labs())

        assert "analysis" in result
        mock_analyze.assert_called_once_with(None, 10, token=None)

    @pytest.mark.asyncio
    @patch(
        "oncoteam.oncofiles_client.analyze_labs",
        new_callable=AsyncMock,
        side_effect=Exception("timeout"),
    )
    async def test_returns_error_on_failure(self, mock_analyze):
        result = json.loads(await analyze_labs())

        assert "error" in result


# ── compare_labs ───────────────────────────────────


class TestCompareLabsTool:
    @pytest.mark.asyncio
    @patch("oncoteam.oncofiles_client.compare_labs", new_callable=AsyncMock)
    async def test_returns_comparison(self, mock_compare):
        mock_compare.return_value = {"diff": ["WBC increased"]}

        result = json.loads(await compare_labs("id_a", "id_b"))

        assert result["comparison"]["diff"] == ["WBC increased"]
        mock_compare.assert_called_once_with("id_a", "id_b", token=None)

    @pytest.mark.asyncio
    @patch(
        "oncoteam.oncofiles_client.compare_labs",
        new_callable=AsyncMock,
        side_effect=Exception("not found"),
    )
    async def test_returns_error_on_failure(self, mock_compare):
        result = json.loads(await compare_labs("id_a", "id_b"))

        assert "error" in result


# ── search_clinical_trials country filter ──────────


class TestSearchClinicalTrialsCountryFilter:
    @pytest.mark.asyncio
    @patch("oncoteam.oncofiles_client.add_research_entry", new_callable=AsyncMock)
    @patch("oncoteam.clinicaltrials_client.search_trials", new_callable=AsyncMock)
    async def test_passes_country_param(self, mock_search, mock_store):
        mock_search.return_value = MOCK_TRIALS

        result = json.loads(await search_clinical_trials("colorectal cancer", country="Slovakia"))

        assert result["count"] == 1
        mock_search.assert_called_once_with("colorectal cancer", None, 10, "Slovakia")


# ── fetch_pubmed_article ──────────────────────────


class TestFetchPubmedArticleTool:
    @pytest.mark.asyncio
    @patch("oncoteam.pubmed_client.fetch_article", new_callable=AsyncMock)
    async def test_returns_article(self, mock_fetch):
        mock_fetch.return_value = MOCK_ARTICLES[0]

        result = json.loads(await fetch_pubmed_article("12345678"))

        assert result["article"]["pmid"] == "12345678"
        assert result["article"]["title"] == "FOLFOX in colorectal cancer"
        mock_fetch.assert_called_once_with("12345678")

    @pytest.mark.asyncio
    @patch("oncoteam.pubmed_client.fetch_article", new_callable=AsyncMock)
    async def test_returns_error_when_not_found(self, mock_fetch):
        mock_fetch.return_value = None

        result = json.loads(await fetch_pubmed_article("00000000"))

        assert "error" in result
        assert "00000000" in result["error"]


# ── fetch_trial_details ──────────────────────────


class TestFetchTrialDetailsTool:
    @pytest.mark.asyncio
    @patch("oncoteam.clinicaltrials_client.fetch_trial", new_callable=AsyncMock)
    async def test_returns_trial(self, mock_fetch):
        mock_fetch.return_value = MOCK_TRIALS[0]

        result = json.loads(await fetch_trial_details("NCT00001234"))

        assert result["trial"]["nct_id"] == "NCT00001234"
        assert result["trial"]["title"] == "FOLFOX Plus Immunotherapy"
        mock_fetch.assert_called_once_with("NCT00001234")

    @pytest.mark.asyncio
    @patch("oncoteam.clinicaltrials_client.fetch_trial", new_callable=AsyncMock)
    async def test_returns_error_when_not_found(self, mock_fetch):
        mock_fetch.return_value = None

        result = json.loads(await fetch_trial_details("NCT99999999"))

        assert "error" in result


# ── check_trial_eligibility ──────────────────────


class TestCheckTrialEligibilityTool:
    @pytest.mark.asyncio
    @patch("oncoteam.clinicaltrials_client.fetch_trial", new_callable=AsyncMock)
    async def test_eligible_trial(self, mock_fetch):
        mock_fetch.return_value = ClinicalTrial(
            nct_id="NCT00001234",
            title="FOLFOX Trial",
            interventions=["FOLFOX"],
            conditions=["Colorectal Cancer"],
        )

        result = json.loads(await check_trial_eligibility("NCT00001234"))

        assert result["eligibility"]["eligible"] is True
        assert result["eligibility"]["flags"] == []

    @pytest.mark.asyncio
    @patch("oncoteam.clinicaltrials_client.fetch_trial", new_callable=AsyncMock)
    async def test_excluded_trial(self, mock_fetch):
        mock_fetch.return_value = ClinicalTrial(
            nct_id="NCT00009999",
            title="Cetuximab Trial",
            interventions=["Cetuximab"],
            conditions=["Colorectal Cancer"],
        )

        result = json.loads(await check_trial_eligibility("NCT00009999"))

        assert result["eligibility"]["eligible"] is False
        assert len(result["eligibility"]["flags"]) > 0

    @pytest.mark.asyncio
    @patch("oncoteam.clinicaltrials_client.fetch_trial", new_callable=AsyncMock)
    async def test_returns_error_when_trial_not_found(self, mock_fetch):
        mock_fetch.return_value = None

        result = json.loads(await check_trial_eligibility("NCT99999999"))

        assert "error" in result


# ── daily_briefing deduplication ─────────────────


class TestDailyBriefingDedup:
    @pytest.mark.asyncio
    @patch("oncoteam.oncofiles_client.add_research_entry", new_callable=AsyncMock)
    @patch("oncoteam.clinicaltrials_client.search_trials_adjacent", new_callable=AsyncMock)
    @patch("oncoteam.pubmed_client.search_pubmed", new_callable=AsyncMock)
    async def test_deduplicates_across_search_terms(self, mock_pubmed, mock_ct, mock_store):
        # All 3 PubMed searches return overlapping articles
        shared_article = PubMedArticle(pmid="11111111", title="Shared Article", abstract="Shared")
        unique_article = PubMedArticle(pmid="22222222", title="Unique Article", abstract="Unique")
        mock_pubmed.side_effect = [
            [shared_article, unique_article],  # term 1: shared + unique
            [shared_article],  # term 2: shared (duplicate)
            [shared_article],  # term 3: shared (duplicate)
        ]
        mock_ct.return_value = []

        result = json.loads(await daily_briefing())

        # Should only have 2 unique articles, not 4
        pubmed_results = result["results"]["pubmed"]
        pmids = [r["pmid"] for r in pubmed_results]
        assert pmids == ["11111111", "22222222"]
        assert result["pubmed_articles"] == 2

    @pytest.mark.asyncio
    @patch("oncoteam.oncofiles_client.add_research_entry", new_callable=AsyncMock)
    @patch("oncoteam.clinicaltrials_client.search_trials_adjacent", new_callable=AsyncMock)
    @patch("oncoteam.pubmed_client.search_pubmed", new_callable=AsyncMock)
    async def test_dedup_reduces_storage_calls(self, mock_pubmed, mock_ct, mock_store):
        shared = PubMedArticle(pmid="11111111", title="Shared", abstract="x")
        mock_pubmed.return_value = [shared]  # Same article from all 3 terms
        mock_ct.return_value = []

        await daily_briefing()

        # Should only store once, not 3 times
        pubmed_stores = [c for c in mock_store.call_args_list if c.kwargs.get("source") == "pubmed"]
        assert len(pubmed_stores) == 1
