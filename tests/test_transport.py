"""Tests for HTTP transport."""

from __future__ import annotations

import json
import logging
import threading
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from retrace_kit.transport import (
    derive_sessions_endpoint,
    send_error_event,
    send_session_ping,
)
from retrace_kit.version import __version__


@pytest.fixture
def sync_background_threads(monkeypatch: pytest.MonkeyPatch) -> None:
    """Run background transport threads synchronously in tests."""

    def immediate_start(self: threading.Thread) -> None:
        self._target(*self._args, **self._kwargs)  # type: ignore[misc]

    monkeypatch.setattr(threading.Thread, "start", immediate_start)


class TestDeriveSessionsEndpoint:
    def test_replaces_error_events_with_sessions(self) -> None:
        assert (
            derive_sessions_endpoint("https://api.example.com/api/error-events")
            == "https://api.example.com/api/sessions"
        )

    def test_replaces_error_events_with_trailing_slash(self) -> None:
        assert (
            derive_sessions_endpoint("https://api.example.com/api/error-events/")
            == "https://api.example.com/api/sessions/"
        )

    def test_replaces_error_events_in_relative_endpoints(self) -> None:
        assert derive_sessions_endpoint("/api/error-events") == "/api/sessions"

    def test_derives_from_parent_path_when_error_events_absent(self) -> None:
        assert (
            derive_sessions_endpoint("https://api.example.com/api/events")
            == "https://api.example.com/api/sessions"
        )

    def test_strips_trailing_slash_before_parent_path(self) -> None:
        assert (
            derive_sessions_endpoint("https://api.example.com/api/")
            == "https://api.example.com/sessions"
        )

    def test_handles_endpoints_without_trailing_slash(self) -> None:
        assert (
            derive_sessions_endpoint("https://api.example.com/api")
            == "https://api.example.com/sessions"
        )

    def test_appends_sessions_when_no_slash_present(self) -> None:
        assert derive_sessions_endpoint("api.example.com") == "api.example.com/sessions"

    def test_uses_last_slash_when_only_protocol_contains_slash(self) -> None:
        assert derive_sessions_endpoint("https://api.example.com") == "https://sessions"

    def test_handles_deeply_nested_paths(self) -> None:
        assert (
            derive_sessions_endpoint("https://api.example.com/v1/ingest/error-events")
            == "https://api.example.com/v1/ingest/sessions"
        )


class TestSendErrorEvent:
    @pytest.fixture
    def captured_request(self) -> dict[str, Any]:
        return {}

    @pytest.fixture
    def mock_urlopen(
        self,
        captured_request: dict[str, Any],
    ) -> MagicMock:
        def _urlopen(request: Any, *args: Any, **kwargs: Any) -> MagicMock:
            captured_request["url"] = request.full_url
            captured_request["headers"] = dict(request.header_items())
            captured_request["body"] = request.data.decode("utf-8")
            response = MagicMock()
            response.status = 200
            response.__enter__ = MagicMock(return_value=response)
            response.__exit__ = MagicMock(return_value=False)
            return response

        with patch("retrace_kit.transport.urlopen", side_effect=_urlopen) as mock:
            yield mock

    def test_posts_with_correct_headers_and_strips_sdk_version(
        self,
        sync_background_threads: None,
        mock_urlopen: MagicMock,
        captured_request: dict[str, Any],
    ) -> None:
        send_error_event(
            {
                "message": "something broke",
                "stacktrace": "Error: something broke\n    at app.py:1:1",
                "sdkVersion": "should-be-stripped",
            },
            api_key="test-api-key",
            endpoint="https://api.example.com/api/error-events",
        )

        mock_urlopen.assert_called_once()
        assert captured_request["url"] == "https://api.example.com/api/error-events"
        assert captured_request["headers"]["Content-type"] == "application/json"
        assert captured_request["headers"]["Authorization"] == "Bearer test-api-key"
        assert captured_request["headers"]["X-rt-sdk-version"] == __version__
        assert captured_request["headers"]["X-rt-sdk-internal"] == "1"

        body = json.loads(captured_request["body"])
        assert "sdkVersion" not in body
        assert body["message"] == "something broke"
        assert body["stacktrace"] == "Error: something broke\n    at app.py:1:1"

    def test_strips_extra_user_fields_before_sending(
        self,
        sync_background_threads: None,
        mock_urlopen: MagicMock,
        captured_request: dict[str, Any],
    ) -> None:
        send_error_event(
            {
                "message": "err",
                "stacktrace": "trace",
                "user": {"id": "user-1", "name": "Jane Doe", "email": "jane@example.com"},  # type: ignore[typeddict-item]
            },
            api_key="test-api-key",
            endpoint="https://api.example.com/api/error-events",
        )

        body = json.loads(captured_request["body"])
        assert body["user"] == {"id": "user-1"}

    def test_warns_on_http_errors(
        self,
        sync_background_threads: None,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        from urllib.error import HTTPError

        http_error = HTTPError(
            url="https://api.example.com/api/error-events",
            code=500,
            msg="Error",
            hdrs=None,
            fp=None,
        )

        with patch("retrace_kit.transport.urlopen", side_effect=http_error):
            with caplog.at_level(logging.WARNING, logger="retrace_kit"):
                send_error_event(
                    {"message": "err", "stacktrace": "trace"},
                    api_key="test-api-key",
                    endpoint="https://api.example.com/api/error-events",
                )

        assert "[retrace-kit sdk] failed to send error event: HTTP 500" in caplog.text

    def test_logs_exceptions_and_never_raises(
        self,
        sync_background_threads: None,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        network_error = OSError("network down")

        with patch("retrace_kit.transport.urlopen", side_effect=network_error):
            with caplog.at_level(logging.ERROR, logger="retrace_kit"):
                send_error_event(
                    {"message": "err", "stacktrace": "trace"},
                    api_key="test-api-key",
                    endpoint="https://api.example.com/api/error-events",
                )

        assert "[retrace-kit sdk] failed to send error event: network down" in caplog.text


class TestSendSessionPing:
    @pytest.fixture
    def captured_request(self) -> dict[str, Any]:
        return {}

    @pytest.fixture
    def mock_urlopen(
        self,
        captured_request: dict[str, Any],
    ) -> MagicMock:
        def _urlopen(request: Any, *args: Any, **kwargs: Any) -> MagicMock:
            captured_request["url"] = request.full_url
            captured_request["headers"] = dict(request.header_items())
            captured_request["body"] = request.data.decode("utf-8")
            response = MagicMock()
            response.status = 200
            response.__enter__ = MagicMock(return_value=response)
            response.__exit__ = MagicMock(return_value=False)
            return response

        with patch("retrace_kit.transport.urlopen", side_effect=_urlopen) as mock:
            yield mock

    def test_posts_with_correct_headers_and_body(
        self,
        sync_background_threads: None,
        mock_urlopen: MagicMock,
        captured_request: dict[str, Any],
    ) -> None:
        payload = {
            "sessionId": "sess-123",
            "release": "1.0.0",
            "environment": "test",
        }

        send_session_ping(
            payload,
            api_key="session-key",
            endpoint="https://api.example.com/api/sessions",
        )

        mock_urlopen.assert_called_once()
        assert captured_request["url"] == "https://api.example.com/api/sessions"
        assert captured_request["headers"]["Content-type"] == "application/json"
        assert captured_request["headers"]["Authorization"] == "Bearer session-key"
        assert captured_request["headers"]["X-rt-sdk-version"] == __version__
        assert captured_request["headers"]["X-rt-sdk-internal"] == "1"
        assert json.loads(captured_request["body"]) == payload

    def test_strips_extra_user_fields_before_sending(
        self,
        sync_background_threads: None,
        mock_urlopen: MagicMock,
        captured_request: dict[str, Any],
    ) -> None:
        send_session_ping(
            {
                "sessionId": "sess-123",
                "user": {"id": "user-1", "name": "Jane Doe", "email": "jane@example.com"},  # type: ignore[typeddict-item]
            },
            api_key="session-key",
            endpoint="https://api.example.com/api/sessions",
        )

        body = json.loads(captured_request["body"])
        assert body["user"] == {"id": "user-1"}

    def test_warns_on_http_errors(
        self,
        sync_background_threads: None,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        from urllib.error import HTTPError

        http_error = HTTPError(
            url="https://api.example.com/api/sessions",
            code=403,
            msg="Forbidden",
            hdrs=None,
            fp=None,
        )

        with patch("retrace_kit.transport.urlopen", side_effect=http_error):
            with caplog.at_level(logging.WARNING, logger="retrace_kit"):
                send_session_ping(
                    {"sessionId": "sess-123"},
                    api_key="session-key",
                    endpoint="https://api.example.com/api/sessions",
                )

        assert "[retrace-kit sdk] failed to send session ping: HTTP 403" in caplog.text

    def test_logs_exceptions_and_never_raises(
        self,
        sync_background_threads: None,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        network_error = OSError("connection reset")

        with patch("retrace_kit.transport.urlopen", side_effect=network_error):
            with caplog.at_level(logging.ERROR, logger="retrace_kit"):
                send_session_ping(
                    {"sessionId": "sess-123"},
                    api_key="session-key",
                    endpoint="https://api.example.com/api/sessions",
                )

        assert "[retrace-kit sdk] failed to send session ping: connection reset" in caplog.text
