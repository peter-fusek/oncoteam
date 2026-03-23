"""Tests for github_client.py."""

from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest
import respx

from oncoteam.github_client import create_issue


class TestCreateIssue:
    @respx.mock
    @pytest.mark.asyncio
    @patch("oncoteam.github_client.GITHUB_TOKEN", "ghp_test123")
    async def test_creates_issue(self):
        route = respx.post("https://api.github.com/repos/peter-fusek/oncoteam/issues").mock(
            return_value=httpx.Response(
                201,
                json={
                    "number": 42,
                    "html_url": "https://github.com/peter-fusek/oncoteam/issues/42",
                },
            )
        )

        result = await create_issue(
            repo="peter-fusek/oncoteam",
            title="Test issue",
            body="Test body",
            labels=["enhancement"],
        )

        assert result == {"number": 42, "url": "https://github.com/peter-fusek/oncoteam/issues/42"}
        assert route.called
        request = route.calls[0].request
        import json as _json

        payload = _json.loads(request.content)
        assert payload["title"] == "Test issue"
        assert payload["labels"] == ["enhancement"]
        assert request.headers["Authorization"] == "Bearer ghp_test123"

    @respx.mock
    @pytest.mark.asyncio
    @patch("oncoteam.github_client.GITHUB_TOKEN", "ghp_test123")
    async def test_no_labels(self):
        respx.post("https://api.github.com/repos/peter-fusek/oncoteam/issues").mock(
            return_value=httpx.Response(
                201,
                json={"number": 1, "html_url": "https://github.com/peter-fusek/oncoteam/issues/1"},
            )
        )

        result = await create_issue(
            repo="peter-fusek/oncoteam",
            title="No labels",
            body="Body",
        )

        assert result["number"] == 1

    @respx.mock
    @pytest.mark.asyncio
    @patch("oncoteam.github_client.GITHUB_TOKEN", "ghp_test123")
    async def test_api_error_raises(self):
        respx.post("https://api.github.com/repos/peter-fusek/oncoteam/issues").mock(
            return_value=httpx.Response(403, json={"message": "Forbidden"})
        )

        with pytest.raises(httpx.HTTPStatusError):
            await create_issue(
                repo="peter-fusek/oncoteam",
                title="Should fail",
                body="Body",
            )
