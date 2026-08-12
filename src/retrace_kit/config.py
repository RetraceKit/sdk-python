"""SDK configuration and initialization."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

from retrace_kit.handlers import (
    install_asyncio_handler,
    install_handlers,
    uninstall_handlers,
)
from retrace_kit.server_url import set_configured_server_url
from retrace_kit.tags import set_tag
from retrace_kit.transport import derive_sessions_endpoint, send_session_ping
from retrace_kit.types import IngestSessionPayload
from retrace_kit.user import get_user

logger = logging.getLogger("retrace_kit")

DEFAULT_ENDPOINT = "https://api.retracekit.cloud/api/error-events"


@dataclass(frozen=True)
class InternalConfig:
    """Internal SDK configuration state."""

    api_key: str
    endpoint: str
    release: str | None = None
    environment: str | None = None
    server_url: str | None = None
    enabled: bool = True


_current_config: InternalConfig | None = None
_warned_about_missing_api_key = False
_session_id: str | None = None


def _ensure_session_id() -> None:
    global _session_id
    if _session_id:
        return
    _session_id = str(uuid.uuid4())


def _normalize_endpoint(endpoint: str | None) -> str:
    if endpoint and endpoint.strip():
        return endpoint.strip()
    return DEFAULT_ENDPOINT


def init(
    *,
    api_key: str,
    endpoint: str | None = None,
    release: str | None = None,
    environment: str | None = None,
    server_url: str | None = None,
    enabled: bool = True,
) -> None:
    """Initialize SDK configuration and global error handlers."""
    global _current_config, _warned_about_missing_api_key

    try:
        _ensure_session_id()
        set_tag("runtime", "python")

        normalized_server_url = (
            server_url.strip()
            if isinstance(server_url, str) and server_url.strip()
            else None
        )
        set_configured_server_url(normalized_server_url)

        normalized_endpoint = _normalize_endpoint(endpoint)
        trimmed_api_key = api_key.strip() if isinstance(api_key, str) else ""

        uninstall_handlers()

        if not trimmed_api_key:
            if not _warned_about_missing_api_key:
                _warned_about_missing_api_key = True
                logger.warning(
                    "[retrace-kit sdk] init({ apiKey }) requires a non-blank apiKey; "
                    "event sending will be disabled.",
                )

            _current_config = InternalConfig(
                api_key="",
                endpoint=normalized_endpoint,
                release=release,
                environment=environment,
                server_url=normalized_server_url,
                enabled=False,
            )
            return

        _current_config = InternalConfig(
            api_key=trimmed_api_key,
            endpoint=normalized_endpoint,
            release=release,
            environment=environment,
            server_url=normalized_server_url,
            enabled=enabled,
        )

        if enabled:
            install_handlers()
            try:
                install_asyncio_handler()
            except Exception:
                pass
            ping_session()
    except Exception:
        # Never throw into host application code.
        pass


def get_current_config() -> InternalConfig | None:
    """Return the current SDK configuration."""
    return _current_config


def is_capture_enabled() -> bool:
    """Return whether event capture and sending are enabled."""
    return bool(_current_config and _current_config.enabled and _current_config.api_key)


def get_session_id() -> str | None:
    """Return the current session ID."""
    return _session_id


def ping_session() -> None:
    """Send a session ping when capture is enabled. Never throws."""
    try:
        if not is_capture_enabled():
            return

        cfg = get_current_config()
        sid = get_session_id()
        if cfg is None or sid is None:
            return

        user = get_user()
        payload: IngestSessionPayload = {"sessionId": sid}
        if user is not None:
            payload["user"] = user
        if cfg.release:
            payload["release"] = cfg.release
        if cfg.environment:
            payload["environment"] = cfg.environment

        send_session_ping(
            payload,
            api_key=cfg.api_key,
            endpoint=derive_sessions_endpoint(cfg.endpoint),
        )
    except Exception:
        # Never throw into host application code.
        pass


def _reset_for_testing() -> None:
    """Reset module state (tests only)."""
    global _current_config, _warned_about_missing_api_key, _session_id
    _current_config = None
    _warned_about_missing_api_key = False
    _session_id = None
