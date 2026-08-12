"""HTTP transport for sending events to Retrace Kit."""

from __future__ import annotations

import json
import logging
import threading
from collections.abc import Callable
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from retrace_kit.types import IngestErrorEventPayload, IngestSessionPayload
from retrace_kit.user import sanitize_user
from retrace_kit.version import __version__

logger = logging.getLogger("retrace_kit")

SDK_INTERNAL_HEADER = "X-RT-SDK-Internal"


def derive_sessions_endpoint(error_events_endpoint: str) -> str:
    """Derive the sessions ingest URL from the error-events endpoint."""
    if "/error-events" in error_events_endpoint:
        return error_events_endpoint.replace("/error-events", "/sessions")

    trimmed = error_events_endpoint.rstrip("/")
    last_slash = trimmed.rfind("/")
    if last_slash >= 0:
        return f"{trimmed[:last_slash]}/sessions"

    return f"{trimmed}/sessions"


def _build_headers(*, api_key: str) -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
        "X-RT-SDK-Version": __version__,
        SDK_INTERNAL_HEADER: "1",
    }


def _strip_sdk_version(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if key != "sdkVersion"}


def _with_sanitized_user(payload: dict[str, Any]) -> dict[str, Any]:
    if "user" not in payload:
        return payload

    user = sanitize_user(payload["user"])
    if user is None:
        return {key: value for key, value in payload.items() if key != "user"}

    return {**payload, "user": user}


def _post_json(*, url: str, api_key: str, body: dict[str, Any], event_label: str) -> None:
    try:
        data = json.dumps(body).encode("utf-8")
        request = Request(url, data=data, headers=_build_headers(api_key=api_key), method="POST")
        with urlopen(request, timeout=10) as response:
            if response.status >= 400:
                logger.warning(
                    "[retrace-kit sdk] failed to send %s: HTTP %s",
                    event_label,
                    response.status,
                )
    except HTTPError as err:
        logger.warning(
            "[retrace-kit sdk] failed to send %s: HTTP %s",
            event_label,
            err.code,
        )
    except (URLError, OSError, ValueError, TypeError) as err:
        logger.error("[retrace-kit sdk] failed to send %s: %s", event_label, err)


def _send_in_background(*, target: Callable[[], None]) -> None:
    thread = threading.Thread(target=target, daemon=True)
    thread.start()


def send_error_event(
    payload: IngestErrorEventPayload,
    *,
    api_key: str,
    endpoint: str,
) -> None:
    """POST error payload to the configured endpoint. Never raises."""
    body = _with_sanitized_user(_strip_sdk_version(dict(payload)))

    def _send() -> None:
        _post_json(url=endpoint, api_key=api_key, body=body, event_label="error event")

    try:
        _send_in_background(target=_send)
    except Exception as err:
        logger.error("[retrace-kit sdk] failed to send error event: %s", err)


def send_session_ping(
    payload: IngestSessionPayload,
    *,
    api_key: str,
    endpoint: str,
) -> None:
    """POST session payload to the sessions endpoint. Never raises."""
    body = _with_sanitized_user(dict(payload))

    def _send() -> None:
        _post_json(url=endpoint, api_key=api_key, body=body, event_label="session ping")

    try:
        _send_in_background(target=_send)
    except Exception as err:
        logger.error("[retrace-kit sdk] failed to send session ping: %s", err)
