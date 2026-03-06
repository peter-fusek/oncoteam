import pytest
import respx
from httpx import Response

from oncoteam.clinicaltrials_client import (
    ADJACENT_COUNTRIES,
    _parse_studies,
    search_trials,
    search_trials_adjacent,
)
from oncoteam.config import CTGOV_BASE_URL

CTGOV_RESPONSE = {
    "studies": [
        {
            "protocolSection": {
                "identificationModule": {
                    "nctId": "NCT00001234",
                    "briefTitle": "FOLFOX Plus Immunotherapy for Colorectal Cancer",
                },
                "statusModule": {"overallStatus": "RECRUITING"},
                "designModule": {"phases": ["PHASE3"]},
                "conditionsModule": {"conditions": ["Colorectal Cancer", "Sigmoid Colon"]},
                "armsInterventionsModule": {
                    "interventions": [
                        {"name": "FOLFOX"},
                        {"name": "Pembrolizumab"},
                    ]
                },
                "contactsLocationsModule": {
                    "locations": [
                        {"facility": "National Cancer Institute"},
                    ]
                },
                "descriptionModule": {
                    "briefSummary": "A phase 3 trial combining FOLFOX with immunotherapy."
                },
            }
        },
        {
            "protocolSection": {
                "identificationModule": {
                    "nctId": "NCT00005678",
                    "briefTitle": "Novel Agent for Sigmoid Colon Cancer",
                },
                "statusModule": {"overallStatus": "RECRUITING"},
                "designModule": {},
                "conditionsModule": {"conditions": ["Sigmoid Colon Cancer"]},
                "armsInterventionsModule": {},
                "contactsLocationsModule": {},
                "descriptionModule": {},
            }
        },
    ]
}


class TestParseStudies:
    def test_parses_trials(self):
        trials = _parse_studies(CTGOV_RESPONSE)
        assert len(trials) == 2

        first = trials[0]
        assert first.nct_id == "NCT00001234"
        assert "FOLFOX" in first.title
        assert first.status == "RECRUITING"
        assert first.phase == "PHASE3"
        assert "Colorectal Cancer" in first.conditions
        assert "FOLFOX" in first.interventions
        assert "Pembrolizumab" in first.interventions
        assert "National Cancer Institute" in first.locations
        assert "phase 3" in first.summary.lower()

    def test_trial_with_minimal_data(self):
        trials = _parse_studies(CTGOV_RESPONSE)
        second = trials[1]
        assert second.nct_id == "NCT00005678"
        assert second.phase == ""
        assert second.interventions == []
        assert second.locations == []

    def test_empty_response(self):
        assert _parse_studies({"studies": []}) == []
        assert _parse_studies({}) == []


class TestSearchTrials:
    @respx.mock
    @pytest.mark.asyncio
    async def test_search_returns_trials(self):
        respx.get(f"{CTGOV_BASE_URL}/studies").mock(return_value=Response(200, json=CTGOV_RESPONSE))

        trials = await search_trials("colorectal cancer", intervention="FOLFOX")
        assert len(trials) == 2
        assert trials[0].nct_id == "NCT00001234"

    @respx.mock
    @pytest.mark.asyncio
    async def test_search_no_results(self):
        respx.get(f"{CTGOV_BASE_URL}/studies").mock(
            return_value=Response(200, json={"studies": []})
        )

        trials = await search_trials("nonexistent condition xyz")
        assert trials == []

    @respx.mock
    @pytest.mark.asyncio
    async def test_search_with_country_filter(self):
        route = respx.get(f"{CTGOV_BASE_URL}/studies").mock(
            return_value=Response(200, json=CTGOV_RESPONSE)
        )

        trials = await search_trials("colorectal cancer", country="Slovakia")
        assert len(trials) == 2
        # Verify country param was sent
        request = route.calls[0].request
        assert "query.locn" in str(request.url)
        assert "Slovakia" in str(request.url)


class TestSearchTrialsAdjacent:
    @respx.mock
    @pytest.mark.asyncio
    async def test_searches_all_adjacent_countries(self):
        route = respx.get(f"{CTGOV_BASE_URL}/studies").mock(
            return_value=Response(200, json=CTGOV_RESPONSE)
        )

        trials = await search_trials_adjacent("colorectal cancer")
        # Should have called the API once per country
        assert route.call_count == len(ADJACENT_COUNTRIES)
        # Deduplication: same NCT IDs returned each time → only 2 unique
        assert len(trials) == 2

    @respx.mock
    @pytest.mark.asyncio
    async def test_deduplicates_across_countries(self):
        # SK returns trial A, CZ returns trial A+B
        response_a = {"studies": [CTGOV_RESPONSE["studies"][0]]}
        response_ab = {"studies": CTGOV_RESPONSE["studies"]}
        responses = [response_a, response_ab, {"studies": []}, {"studies": []}]
        call_count = 0

        def side_effect(request, route):
            nonlocal call_count
            resp = responses[min(call_count, len(responses) - 1)]
            call_count += 1
            return Response(200, json=resp)

        respx.get(f"{CTGOV_BASE_URL}/studies").mock(side_effect=side_effect)

        trials = await search_trials_adjacent("CRC")
        nct_ids = [t.nct_id for t in trials]
        assert len(nct_ids) == len(set(nct_ids))  # no duplicates

    @respx.mock
    @pytest.mark.asyncio
    async def test_handles_partial_failures(self):
        call_count = 0

        def side_effect(request, route):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                return Response(500, text="Server Error")
            return Response(200, json=CTGOV_RESPONSE)

        respx.get(f"{CTGOV_BASE_URL}/studies").mock(side_effect=side_effect)

        # Should not raise; partial results returned
        trials = await search_trials_adjacent("CRC")
        assert len(trials) >= 1
