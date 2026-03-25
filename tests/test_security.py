"""Tests for Sprint 54 security hardening: input validation, body size limits."""

from __future__ import annotations

import contextlib
import json
from unittest.mock import AsyncMock

import pytest

from oncoteam.dashboard_api import MAX_REQUEST_BODY_BYTES, _parse_json_body
from oncoteam.oncofiles_client import _validate_id

# ── _validate_id tests ──────────────────────────────────────────────


class TestValidateId:
    def test_valid_string(self):
        assert _validate_id("123") == "123"

    def test_valid_int(self):
        assert _validate_id(42) == "42"

    def test_strips_whitespace(self):
        assert _validate_id("  abc  ") == "abc"

    def test_empty_raises(self):
        with pytest.raises(ValueError, match="Invalid"):
            _validate_id("")

    def test_whitespace_only_raises(self):
        with pytest.raises(ValueError, match="Invalid"):
            _validate_id("   ")

    def test_too_long_raises(self):
        with pytest.raises(ValueError, match="Invalid"):
            _validate_id("x" * 201)

    def test_max_length_ok(self):
        result = _validate_id("x" * 200)
        assert len(result) == 200

    def test_custom_name_in_error(self):
        with pytest.raises(ValueError, match="file_id"):
            _validate_id("", "file_id")


# ── _parse_json_body tests ──────────────────────────────────────────


class TestParseJsonBody:
    @pytest.fixture
    def mock_request(self):
        """Create a mock request with configurable body."""
        request = AsyncMock()
        return request

    async def test_valid_json(self, mock_request):
        mock_request.body.return_value = json.dumps({"key": "value"}).encode()
        result = await _parse_json_body(mock_request)
        assert result == {"key": "value"}

    async def test_empty_json_object(self, mock_request):
        mock_request.body.return_value = b"{}"
        result = await _parse_json_body(mock_request)
        assert result == {}

    async def test_body_too_large_raises(self, mock_request):
        mock_request.body.return_value = b"x" * (MAX_REQUEST_BODY_BYTES + 1)
        with pytest.raises(ValueError, match="too large"):
            await _parse_json_body(mock_request)

    async def test_body_at_limit_ok(self, mock_request):
        data = {"data": "a" * (MAX_REQUEST_BODY_BYTES - 20)}
        mock_request.body.return_value = json.dumps(data).encode()[:MAX_REQUEST_BODY_BYTES]
        # Should not raise ValueError — at or under limit
        # (may raise JSONDecodeError if truncated, but not a size error)
        with contextlib.suppress(json.JSONDecodeError):
            await _parse_json_body(mock_request)

    async def test_invalid_json_raises(self, mock_request):
        mock_request.body.return_value = b"not json"
        with pytest.raises(json.JSONDecodeError):
            await _parse_json_body(mock_request)

    def test_max_body_size_is_1mb(self):
        assert MAX_REQUEST_BODY_BYTES == 1_000_000
