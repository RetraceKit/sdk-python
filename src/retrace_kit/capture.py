"""Exception capture and reporting."""

from __future__ import annotations

import sys
import threading
import time
import traceback
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any, cast

from retrace_kit.breadcrumbs import get_breadcrumbs_snapshot
from retrace_kit.config import InternalConfig, get_current_config, get_session_id
from retrace_kit.dedup import DedupCache, compute_dedup_key
from retrace_kit.server_url import get_configured_server_url
from retrace_kit.tags import get_tags_snapshot
from retrace_kit.transport import send_error_event
from retrace_kit.types import IngestErrorEventPayload
from retrace_kit.user import get_user

_dedup_cache = DedupCache()
_capture_guard = threading.local()


def _utc_now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def _get_default_user_agent() -> str:
    major, minor, micro = sys.version_info[:3]
    return f"Python/{major}.{minor}.{micro}"


def _get_default_url() -> str | None:
    try:
        return get_configured_server_url()
    except Exception:
        return None


def _extract_message(error: object) -> str:
    if isinstance(error, BaseException):
        message = str(error)
        if message:
            return message
    if isinstance(error, str) and error:
        return error
    if error is not None:
        try:
            value = str(error)
            if value:
                return value
        except Exception:
            pass
    return "Unknown error"


def _extract_stacktrace(error: object) -> str:
    if isinstance(error, BaseException) and error.__traceback__ is not None:
        return "".join(
            traceback.format_exception(type(error), error, error.__traceback__)
        ).rstrip()
    return "No stacktrace available"


def _extract_name(error: object) -> str | None:
    if isinstance(error, BaseException):
        name = type(error).__name__
        if isinstance(name, str) and name.strip():
            return name
    return None


def build_payload_from_error(
    error: object,
    config: InternalConfig,
    context: Mapping[str, Any] | None = None,
) -> IngestErrorEventPayload:
    """Build a backend-aligned payload from an error and current SDK state."""
    user = get_user()
    breadcrumbs = get_breadcrumbs_snapshot()
    tags = get_tags_snapshot()
    session_id = get_session_id()
    name = _extract_name(error)

    payload: IngestErrorEventPayload = {
        "timestamp": _utc_now_iso(),
        "message": _extract_message(error),
        "stacktrace": _extract_stacktrace(error),
    }

    if name:
        payload["name"] = name

    url = config.server_url if config.server_url else _get_default_url()
    if url:
        payload["url"] = url

    if config.release:
        payload["release"] = config.release
    if config.environment:
        payload["environment"] = config.environment

    payload["userAgent"] = _get_default_user_agent()

    if user is not None:
        payload["user"] = user
    if breadcrumbs:
        payload["breadcrumbs"] = breadcrumbs
    if tags:
        payload["tags"] = tags
    if session_id:
        payload["sessionId"] = session_id

    if context is None:
        return payload

    merged = cast(IngestErrorEventPayload, {**payload, **dict(context)})
    if "sessionId" not in context and session_id:
        merged["sessionId"] = session_id
    return merged


def _is_capturing() -> bool:
    return bool(getattr(_capture_guard, "active", False))


def _set_capturing(active: bool) -> None:
    _capture_guard.active = active


def capture_exception(
    error: object,
    context: Mapping[str, Any] | None = None,
) -> None:
    """Capture and report an exception. Never throws."""
    if _is_capturing():
        return

    _set_capturing(True)
    try:
        cfg = get_current_config()
        if cfg is None or not cfg.enabled or not cfg.api_key:
            return

        dedup_key: str | None = None
        allow_send = True

        try:
            dedup_key = compute_dedup_key(
                _extract_name(error),
                _extract_message(error),
                _extract_stacktrace(error),
            )
            allow_send = _dedup_cache.should_send(dedup_key, int(time.time() * 1000))
        except Exception:
            # Fail-open when dedup logic throws.
            pass

        if not allow_send:
            return

        payload = build_payload_from_error(error, cfg, context)
        send_error_event(payload, api_key=cfg.api_key, endpoint=cfg.endpoint)

        if dedup_key is not None:
            try:
                _dedup_cache.record_send(dedup_key, int(time.time() * 1000))
            except Exception:
                # Ignore cache write failures.
                pass
    except Exception:
        # Never throw into host application code.
        pass
    finally:
        _set_capturing(False)


def _reset_for_testing() -> None:
    """Reset module state (tests only)."""
    _set_capturing(False)
    _dedup_cache.clear()
