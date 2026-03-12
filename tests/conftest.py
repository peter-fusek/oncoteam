"""Shared test fixtures."""

from unittest.mock import AsyncMock, patch

import pytest

_TEST_ALLOWED_ORIGINS = [
    "https://oncoteam-dashboard.onrender.com",
    "https://oncoteam-dashboard-test.onrender.com",
]


@pytest.fixture(autouse=True)
def _mock_activity_logging():
    """Prevent activity logging from making real HTTP calls during tests."""
    with patch("oncoteam.activity_logger._write_tool_log", new_callable=AsyncMock):
        yield


@pytest.fixture(autouse=True)
def _set_cors_and_origins():
    """Set a fake dashboard request and allowed origins for tests."""
    from starlette.datastructures import Headers

    import oncoteam.dashboard_api as mod

    class FakeCorsRequest:
        headers = Headers({"origin": "https://oncoteam-dashboard.onrender.com"})

    mod._CURRENT_REQUEST = FakeCorsRequest()
    with patch("oncoteam.dashboard_api.DASHBOARD_ALLOWED_ORIGINS", _TEST_ALLOWED_ORIGINS):
        yield
    mod._CURRENT_REQUEST = None
