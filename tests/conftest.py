"""Shared test fixtures."""

from unittest.mock import AsyncMock, patch

import pytest


@pytest.fixture(autouse=True)
def _mock_activity_logging():
    """Prevent activity logging from making real HTTP calls during tests."""
    with patch("oncoteam.activity_logger._write_tool_log", new_callable=AsyncMock):
        yield


@pytest.fixture(autouse=True)
def _set_cors_request():
    """Set a fake dashboard request for CORS origin resolution in tests."""
    from starlette.datastructures import Headers

    import oncoteam.dashboard_api as mod

    class FakeCorsRequest:
        headers = Headers({"origin": "https://oncoteam-dashboard.onrender.com"})

    mod._CURRENT_REQUEST = FakeCorsRequest()
    yield
    mod._CURRENT_REQUEST = None
