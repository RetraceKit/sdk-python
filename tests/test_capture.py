"""Tests for exception capture."""

from __future__ import annotations

import json
import sys
import threading
from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from retrace_kit.breadcrumbs import add_breadcrumb
from retrace_kit.capture import build_payload_from_error, capture_exception
from retrace_kit.config import InternalConfig, get_current_config, init
from retrace_kit.dedup import DEDUP_WINDOW_MS
from retrace_kit.server_url import set_configured_server_url
from retrace_kit.tags import set_tag
from retrace_kit.user import set_user


@pytest.fixture
def sync_background_threads(monkeypatch: pytest.MonkeyPatch) -> None:
    """Run background transport threads synchronously in tests."""

    def immediate_start(self: threading.Thread) -> None:
        self._target(*self._args, **self._kwargs)  # type: ignore[misc]

    monkeypatch.setattr(threading.Thread, "start", immediate_start)


@pytest.fixture
def enabled_config() -> InternalConfig:
    return InternalConfig(
        api_key="test-key",
        endpoint="https://api.example.com/api/error-events",
        release="1.0.0",
        environment="test",
        server_url="https://api.example.com/orders/42",
        enabled=True,
    )


def _make_error_with_traceback(
    exc_type: type[BaseException],
    message: str,
    filename: str,
    func_name: str,
    lineno: int,
) -> BaseException:
    try:
        code = compile("raise exc_type(message)", filename, "exec")
        namespace: dict[str, Any] = {"exc_type": exc_type, "message": message}
        exec(code, namespace)  # noqa: S102
    except BaseException as error:  # noqa: BLE001
        return error
    raise AssertionError("expected exception")


class TestBuildPayloadFromError:
    @patch("retrace_kit.capture._utc_now_iso", return_value="2026-07-09T12:00:00.000Z")
    def test_extracts_message_name_and_stacktrace(self, _mock_now: MagicMock) -> None:
        error = _make_error_with_traceback(ValueError, "type mismatch", "test.py", "check", 3)

        payload = build_payload_from_error(
            error,
            InternalConfig(api_key="k", endpoint="https://api.example.com/api/error-events"),
        )

        assert payload["message"] == "type mismatch"
        assert payload["name"] == "ValueError"
        assert "Traceback" in payload["stacktrace"]
        assert "type mismatch" in payload["stacktrace"]

    @patch("retrace_kit.capture._utc_now_iso", return_value="2026-07-09T12:00:00.000Z")
    def test_uses_string_errors_as_message(self, _mock_now: MagicMock) -> None:
        payload = build_payload_from_error(
            "network timeout",
            InternalConfig(api_key="k", endpoint="https://api.example.com/api/error-events"),
        )

        assert payload["message"] == "network timeout"
        assert "name" not in payload
        assert payload["stacktrace"] == "No stacktrace available"

    @patch("retrace_kit.capture._utc_now_iso", return_value="2026-07-09T12:00:00.000Z")
    @pytest.mark.parametrize(
        ("error", "expected_message"),
        [
            (None, "Unknown error"),
            (42, "42"),
            ({"code": "ERR"}, "{'code': 'ERR'}"),
        ],
    )
    def test_falls_back_for_non_exception_errors(
        self,
        _mock_now: MagicMock,
        error: object,
        expected_message: str,
    ) -> None:
        payload = build_payload_from_error(
            error,
            InternalConfig(api_key="k", endpoint="https://api.example.com/api/error-events"),
        )
        assert payload["message"] == expected_message

    @patch("retrace_kit.capture._utc_now_iso", return_value="2026-07-09T12:00:00.000Z")
    def test_includes_user_tags_breadcrumbs_and_session_id(self, _mock_now: MagicMock) -> None:
        init(api_key="test-key")
        set_user(id="user-1")
        set_tag("env", "staging")
        add_breadcrumb(type="common", value="clicked", name="button")

        error = ValueError("boom")
        payload = build_payload_from_error(error, get_current_config())  # type: ignore[arg-type]

        assert payload["user"] == {"id": "user-1"}
        assert payload["tags"]["env"] == "staging"
        assert payload["tags"]["runtime"] == "python"
        assert len(payload["breadcrumbs"]) == 1
        assert payload["sessionId"] is not None

    @patch("retrace_kit.capture._utc_now_iso", return_value="2026-07-09T12:00:00.000Z")
    def test_includes_user_agent_from_python_version(self, _mock_now: MagicMock) -> None:
        major, minor, micro = sys.version_info[:3]
        payload = build_payload_from_error(
            ValueError("boom"),
            InternalConfig(api_key="k", endpoint="https://api.example.com/api/error-events"),
        )
        assert payload["userAgent"] == f"Python/{major}.{minor}.{micro}"

    @patch("retrace_kit.capture._utc_now_iso", return_value="2026-07-09T12:00:00.000Z")
    def test_prefers_server_url_from_config(self, _mock_now: MagicMock) -> None:
        payload = build_payload_from_error(
            ValueError("boom"),
            InternalConfig(
                api_key="k",
                endpoint="https://api.example.com/api/error-events",
                server_url="https://api.example.com/orders/42",
            ),
        )
        assert payload["url"] == "https://api.example.com/orders/42"

    @patch("retrace_kit.capture._utc_now_iso", return_value="2026-07-09T12:00:00.000Z")
    def test_uses_configured_server_url_as_default(self, _mock_now: MagicMock) -> None:
        set_configured_server_url("https://configured.example.com/app")
        payload = build_payload_from_error(
            ValueError("boom"),
            InternalConfig(api_key="k", endpoint="https://api.example.com/api/error-events"),
        )
        assert payload["url"] == "https://configured.example.com/app"

    @patch("retrace_kit.capture._utc_now_iso", return_value="2026-07-09T12:00:00.000Z")
    def test_omits_empty_breadcrumbs_and_tags(self, _mock_now: MagicMock) -> None:
        payload = build_payload_from_error(
            ValueError("boom"),
            InternalConfig(api_key="k", endpoint="https://api.example.com/api/error-events"),
        )
        assert "breadcrumbs" not in payload
        assert "tags" not in payload

    @patch("retrace_kit.capture._utc_now_iso", return_value="2026-07-09T12:00:00.000Z")
    def test_merges_context_overrides(self, _mock_now: MagicMock) -> None:
        init(api_key="test-key")
        payload = build_payload_from_error(
            ValueError("original"),
            get_current_config(),  # type: ignore[arg-type]
            {"message": "overridden message", "environment": "override-env"},
        )
        assert payload["message"] == "overridden message"
        assert payload["environment"] == "override-env"
        assert payload["sessionId"] is not None


@pytest.fixture
def init_without_session_ping() -> None:
    with patch("retrace_kit.config.send_session_ping"):
        yield


class TestCaptureException:
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
            captured_request["body"] = request.data.decode("utf-8")
            response = MagicMock()
            response.status = 200
            response.__enter__ = MagicMock(return_value=response)
            response.__exit__ = MagicMock(return_value=False)
            return response

        with patch("retrace_kit.transport.urlopen", side_effect=_urlopen) as mock:
            yield mock

    def test_sends_when_capture_enabled(
        self,
        sync_background_threads: None,
        mock_urlopen: MagicMock,
        enabled_config: InternalConfig,
    ) -> None:
        with patch("retrace_kit.capture.get_current_config", return_value=enabled_config):
            error = ValueError("capture me")
            capture_exception(error)

        mock_urlopen.assert_called_once()

    def test_no_ops_when_api_key_missing(
        self,
        sync_background_threads: None,
        mock_urlopen: MagicMock,
        enabled_config: InternalConfig,
    ) -> None:
        disabled = InternalConfig(
            api_key="",
            endpoint=enabled_config.endpoint,
            enabled=True,
        )
        with patch("retrace_kit.capture.get_current_config", return_value=disabled):
            capture_exception(ValueError("ignored"))

        mock_urlopen.assert_not_called()

    def test_no_ops_when_capture_disabled(
        self,
        sync_background_threads: None,
        mock_urlopen: MagicMock,
        enabled_config: InternalConfig,
    ) -> None:
        disabled = InternalConfig(
            api_key=enabled_config.api_key,
            endpoint=enabled_config.endpoint,
            enabled=False,
        )
        with patch("retrace_kit.capture.get_current_config", return_value=disabled):
            capture_exception(ValueError("ignored"))

        mock_urlopen.assert_not_called()

    def test_no_ops_when_not_initialized(
        self,
        sync_background_threads: None,
        mock_urlopen: MagicMock,
    ) -> None:
        with patch("retrace_kit.capture.get_current_config", return_value=None):
            capture_exception(ValueError("ignored"))

        mock_urlopen.assert_not_called()

    def test_sends_payload_via_transport(
        self,
        sync_background_threads: None,
        mock_urlopen: MagicMock,
        init_without_session_ping: None,
    ) -> None:
        init(api_key="test-key", release="1.0.0", environment="test")
        set_user(id="u1")
        error = _make_error_with_traceback(RuntimeError, "capture me", "app.py", "handler", 7)
        capture_exception(error, {"message": "context override"})

        body = json.loads(mock_urlopen.call_args[0][0].data.decode("utf-8"))
        assert body["message"] == "context override"
        assert body["name"] == "RuntimeError"
        assert body["release"] == "1.0.0"
        assert body["environment"] == "test"
        assert body["user"] == {"id": "u1"}
        assert body["sessionId"] is not None
        assert body["userAgent"].startswith("Python/")

    def test_never_raises_when_config_lookup_fails(self) -> None:
        with patch("retrace_kit.capture.get_current_config", side_effect=RuntimeError("config failed")):
            capture_exception(ValueError("safe"))

    def test_never_raises_when_transport_fails(
        self,
        sync_background_threads: None,
        init_without_session_ping: None,
    ) -> None:
        init(api_key="test-key")
        with patch("retrace_kit.transport.urlopen", side_effect=OSError("network down")):
            capture_exception(ValueError("safe"))

    def test_suppresses_duplicate_errors_within_dedup_window(
        self,
        sync_background_threads: None,
        mock_urlopen: MagicMock,
        init_without_session_ping: None,
    ) -> None:
        init(api_key="test-key")
        error = _make_error_with_traceback(ValueError, "boom", "app.py", "handler", 1)

        capture_exception(error)
        capture_exception(error)

        mock_urlopen.assert_called_once()

    def test_allows_same_error_after_dedup_window(
        self,
        sync_background_threads: None,
        mock_urlopen: MagicMock,
        init_without_session_ping: None,
    ) -> None:
        init(api_key="test-key")
        error = _make_error_with_traceback(ValueError, "boom", "app.py", "handler", 1)
        start = datetime(2026, 7, 9, 12, 0, 0, tzinfo=timezone.utc)

        with patch("retrace_kit.capture.time.time") as mock_time:
            mock_time.return_value = start.timestamp()
            capture_exception(error)

            mock_time.return_value = start.timestamp() + (DEDUP_WINDOW_MS / 1000)
            capture_exception(error)

        assert mock_urlopen.call_count == 2

    def test_suppresses_reentrant_capture_calls(
        self,
        sync_background_threads: None,
        init_without_session_ping: None,
    ) -> None:
        init(api_key="test-key")
        send_calls = 0

        def nested_send(*args: Any, **kwargs: Any) -> None:
            nonlocal send_calls
            send_calls += 1
            capture_exception(ValueError("nested"))

        with patch("retrace_kit.capture.send_error_event", side_effect=nested_send):
            capture_exception(ValueError("outer"))

        assert send_calls == 1

    def test_concurrent_threads_do_not_drop_errors(
        self,
        init_without_session_ping: None,
    ) -> None:
        init(api_key="test-key")
        start_event = threading.Event()
        send_calls: list[str] = []
        lock = threading.Lock()

        def capture_in_thread(message: str) -> None:
            start_event.wait(timeout=5)
            capture_exception(ValueError(message))

        def record_send(payload: dict[str, object], **kwargs: object) -> None:
            with lock:
                send_calls.append(str(payload["message"]))

        with patch("retrace_kit.capture.send_error_event", side_effect=record_send) as mock_send:

            threads = [
                threading.Thread(target=capture_in_thread, args=(f"thread-{index}",))
                for index in range(2)
            ]
            for thread in threads:
                thread.start()
            start_event.set()
            for thread in threads:
                thread.join(timeout=5)

        assert sorted(send_calls) == ["thread-0", "thread-1"]
        assert mock_send.call_count == 2

    def test_deduplicates_regardless_of_context_overrides(
        self,
        sync_background_threads: None,
        mock_urlopen: MagicMock,
        init_without_session_ping: None,
    ) -> None:
        init(api_key="test-key")
        error = _make_error_with_traceback(ValueError, "boom", "app.py", "handler", 1)

        capture_exception(error, {"message": "override one"})
        capture_exception(error, {"message": "override two"})

        mock_urlopen.assert_called_once()
        body = json.loads(mock_urlopen.call_args[0][0].data.decode("utf-8"))
        assert body["message"] == "override one"
