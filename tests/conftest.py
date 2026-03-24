"""Shared test fixtures."""

from unittest.mock import AsyncMock, patch

import pytest

_TEST_ALLOWED_ORIGINS = [
    "https://dashboard.oncoteam.cloud",
    "https://valiant-reprieve-production.up.railway.app",
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
        headers = Headers({"origin": "https://dashboard.oncoteam.cloud"})

    mod._CURRENT_REQUEST = FakeCorsRequest()
    with patch("oncoteam.dashboard_api.DASHBOARD_ALLOWED_ORIGINS", _TEST_ALLOWED_ORIGINS):
        yield
    mod._CURRENT_REQUEST = None


@pytest.fixture(autouse=True)
def _clear_rate_limiters():
    """Reset rate limiter deques between tests to avoid cross-test pollution."""
    import oncoteam.dashboard_api as mod

    mod._rate_timestamps.clear()
    mod._expensive_timestamps.clear()
    yield
    mod._rate_timestamps.clear()
    mod._expensive_timestamps.clear()


@pytest.fixture(autouse=True)
def _mock_circuit_breaker_closed():
    """Default circuit breaker to closed so api_labs/api_documents don't fast-fail."""
    with patch(
        "oncoteam.dashboard_api.oncofiles_client.get_circuit_breaker_status",
        return_value={"state": "closed", "failure_count": 0, "cooldown_remaining": 0},
    ):
        yield
