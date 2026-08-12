"""Breadcrumb collection."""

from __future__ import annotations

import math
from datetime import datetime, timezone

from retrace_kit.types import Breadcrumb, BreadcrumbType

MAX_BREADCRUMBS = 24

_queue: list[Breadcrumb] = []

_BREADCRUMB_TYPES: frozenset[BreadcrumbType] = frozenset({"request", "route", "common"})


def add_breadcrumb(
    *,
    type: BreadcrumbType,
    name: str,
    value: str,
    status: int | None = None,
    duration: int | None = None,
) -> None:
    """Append a breadcrumb to the FIFO queue (max 24). Never throws."""
    try:
        if type not in _BREADCRUMB_TYPES:
            return

        breadcrumb_value = value if isinstance(value, str) else ""
        breadcrumb_name = name if isinstance(name, str) else ""
        breadcrumb_status = (
            status
            if isinstance(status, int | float)
            and math.isfinite(status)
            else None
        )
        breadcrumb_duration = (
            round(duration)
            if isinstance(duration, int | float) and math.isfinite(duration)
            else None
        )

        crumb: Breadcrumb = {
            "type": type,
            "value": breadcrumb_value,
            "name": breadcrumb_name,
            "capturedAt": datetime.now(timezone.utc)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z"),
        }
        if breadcrumb_status is not None:
            crumb["status"] = int(breadcrumb_status)
        if breadcrumb_duration is not None:
            crumb["duration"] = int(breadcrumb_duration)

        _queue.append(crumb)
        if len(_queue) > MAX_BREADCRUMBS:
            _queue.pop(0)
    except Exception:
        # Never throw into host application code.
        pass


def get_breadcrumbs_snapshot() -> list[Breadcrumb]:
    """Return a shallow copy of the current breadcrumb queue."""
    return list(_queue)


def _reset_for_testing() -> None:
    """Reset module state (tests only)."""
    _queue.clear()
