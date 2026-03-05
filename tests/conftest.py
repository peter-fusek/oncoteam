"""Shared test fixtures."""

from unittest.mock import AsyncMock, patch

import pytest


@pytest.fixture(autouse=True)
def _mock_activity_logging():
    """Prevent activity logging from making real HTTP calls during tests."""
    with patch("oncoteam.activity_logger._write_tool_log", new_callable=AsyncMock):
        yield
