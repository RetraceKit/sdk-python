"""Tests for SDK configuration."""

from __future__ import annotations

import logging
import re
import uuid
from unittest.mock import patch

import pytest

from retrace_kit.config import (
    DEFAULT_ENDPOINT,
    get_current_config,
    get_session_id,
    init,
    is_capture_enabled,
    ping_session,
)
from retrace_kit.tags import get_tags_snapshot


class TestInit:
    def test_init_with_api_key_sets_config_and_runtime_tag(self) -> None:
        with patch("retrace_kit.config.send_session_ping") as mock_send:
            with patch("retrace_kit.config.install_handlers") as mock_install:
                init(
                    api_key="  test-key  ",
                    release="1.2.3",
                    environment="staging",
                )

        cfg = get_current_config()
        assert cfg is not None
        assert cfg.api_key == "test-key"
        assert cfg.endpoint == DEFAULT_ENDPOINT
        assert cfg.release == "1.2.3"
        assert cfg.environment == "staging"
        assert cfg.enabled is True
        assert is_capture_enabled() is True
        assert get_tags_snapshot() == {"runtime": "python"}
        mock_send.assert_called_once()
        mock_install.assert_called_once()

    def test_init_without_api_key_warns_once_and_disables_capture(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        with patch("retrace_kit.config.send_session_ping") as mock_send:
            with patch("retrace_kit.config.uninstall_handlers") as mock_uninstall:
                with caplog.at_level(logging.WARNING, logger="retrace_kit"):
                    init(api_key="")
                    init(api_key="")

        warning_messages = [
            record.message
            for record in caplog.records
            if record.levelno == logging.WARNING
        ]
        assert len(warning_messages) == 1
        assert (
            "[retrace-kit sdk] init({ apiKey }) requires a non-blank apiKey; "
            "event sending will be disabled."
        ) in warning_messages[0]

        cfg = get_current_config()
        assert cfg is not None
        assert cfg.api_key == ""
        assert cfg.endpoint == DEFAULT_ENDPOINT
        assert cfg.enabled is False
        assert is_capture_enabled() is False
        mock_send.assert_not_called()
        assert mock_uninstall.call_count == 2

    def test_init_with_enabled_false_skips_session_ping(self) -> None:
        with patch("retrace_kit.config.send_session_ping") as mock_send:
            with patch("retrace_kit.config.install_handlers") as mock_install:
                init(api_key="key", enabled=False)

        cfg = get_current_config()
        assert cfg is not None
        assert cfg.enabled is False
        assert is_capture_enabled() is False
        mock_send.assert_not_called()
        mock_install.assert_not_called()

    def test_init_uses_custom_endpoint(self) -> None:
        custom_endpoint = "https://custom.example.com/api/error-events"

        with patch("retrace_kit.config.send_session_ping") as mock_send:
            init(api_key="key", endpoint=custom_endpoint)

        cfg = get_current_config()
        assert cfg is not None
        assert cfg.endpoint == custom_endpoint
        mock_send.assert_called_once()

    def test_init_stores_server_url(self) -> None:
        from retrace_kit.server_url import get_configured_server_url

        init(api_key="key", server_url="  https://api.example.com/users  ")

        cfg = get_current_config()
        assert cfg is not None
        assert cfg.server_url == "https://api.example.com/users"
        assert get_configured_server_url() == "https://api.example.com/users"


class TestSessionId:
    def test_init_creates_session_id(self) -> None:
        with patch("retrace_kit.config.send_session_ping"):
            init(api_key="key")

        sid = get_session_id()
        assert sid is not None
        uuid.UUID(sid)

    def test_session_id_is_reused_on_reinit(self) -> None:
        with patch("retrace_kit.config.send_session_ping"):
            init(api_key="first-key")
            first_sid = get_session_id()
            init(api_key="second-key")

        assert get_session_id() == first_sid


class TestPingSession:
    def test_ping_session_sends_payload_when_capture_enabled(self) -> None:
        with patch("retrace_kit.config.send_session_ping") as mock_send:
            init(
                api_key="key",
                release="2.0.0",
                environment="prod",
            )
            mock_send.reset_mock()

            ping_session()

        mock_send.assert_called_once()
        args, kwargs = mock_send.call_args
        sent_payload = args[0]
        assert sent_payload["sessionId"] == get_session_id()
        assert sent_payload["release"] == "2.0.0"
        assert sent_payload["environment"] == "prod"
        assert kwargs["api_key"] == "key"
        assert kwargs["endpoint"] == DEFAULT_ENDPOINT.replace("/error-events", "/sessions")

    def test_ping_session_noops_when_capture_disabled(self) -> None:
        with patch("retrace_kit.config.send_session_ping") as mock_send:
            init(api_key="")
            mock_send.reset_mock()

            ping_session()

        mock_send.assert_not_called()

    def test_ping_session_noops_when_enabled_false(self) -> None:
        with patch("retrace_kit.config.send_session_ping") as mock_send:
            init(api_key="key", enabled=False)
            mock_send.reset_mock()

            ping_session()

        mock_send.assert_not_called()

    def test_ping_session_never_raises_when_transport_fails(self) -> None:
        with patch(
            "retrace_kit.config.send_session_ping",
            side_effect=RuntimeError("transport failed"),
        ):
            init(api_key="key")

        ping_session()

    def test_session_id_matches_uuid_format(self) -> None:
        with patch("retrace_kit.config.send_session_ping"):
            init(api_key="key")

        sid = get_session_id()
        assert sid is not None
        assert re.fullmatch(
            r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
            sid,
            flags=re.IGNORECASE,
        )
