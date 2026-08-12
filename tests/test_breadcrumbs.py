"""Tests for breadcrumb collection."""

from __future__ import annotations

from datetime import datetime, timezone

from retrace_kit.breadcrumbs import (
    MAX_BREADCRUMBS,
    add_breadcrumb,
    get_breadcrumbs_snapshot,
)


class TestAddBreadcrumb:
    def test_accepts_valid_breadcrumb_types(self) -> None:
        for crumb_type in ("request", "route", "common"):
            add_breadcrumb(type=crumb_type, value="v", name="n")

        snapshot = get_breadcrumbs_snapshot()
        assert len(snapshot) == 3
        assert [crumb["type"] for crumb in snapshot] == ["request", "route", "common"]

    def test_ignores_invalid_breadcrumb_types(self) -> None:
        add_breadcrumb(type="request", value="ok", name="ok")  # type: ignore[arg-type]
        add_breadcrumb(type="invalid", value="skip", name="skip")  # type: ignore[arg-type]
        add_breadcrumb(type="", value="skip", name="skip")  # type: ignore[arg-type]

        assert len(get_breadcrumbs_snapshot()) == 1

    def test_coerces_non_string_value_and_name_to_empty_strings(self) -> None:
        add_breadcrumb(type="common", value=42, name=None)  # type: ignore[arg-type]

        crumb = get_breadcrumbs_snapshot()[0]
        assert crumb["value"] == ""
        assert crumb["name"] == ""

    def test_includes_finite_status_and_rounds_duration(self) -> None:
        add_breadcrumb(
            type="request",
            value="/api",
            name="GET",
            status=404,
            duration=12.6,
        )

        crumb = get_breadcrumbs_snapshot()[0]
        assert crumb["status"] == 404
        assert crumb["duration"] == 13

    def test_omits_non_finite_status_and_duration(self) -> None:
        add_breadcrumb(
            type="request",
            value="/api",
            name="GET",
            status=float("nan"),
            duration=float("inf"),
        )

        crumb = get_breadcrumbs_snapshot()[0]
        assert "status" not in crumb
        assert "duration" not in crumb

    def test_sets_captured_at_as_iso8601_timestamp(self) -> None:
        add_breadcrumb(type="common", value="v", name="n")

        captured_at = get_breadcrumbs_snapshot()[0]["capturedAt"]
        assert captured_at[:4].isdigit()
        assert "T" in captured_at
        assert datetime.fromisoformat(captured_at.replace("Z", "+00:00")).tzinfo is not None

    def test_enforces_fifo_max_of_24_breadcrumbs(self) -> None:
        for index in range(25):
            add_breadcrumb(type="common", value=f"v{index}", name=f"n{index}")

        snapshot = get_breadcrumbs_snapshot()
        assert len(snapshot) == MAX_BREADCRUMBS
        assert snapshot[0]["name"] == "n1"
        assert snapshot[-1]["name"] == "n24"

    def test_never_raises_on_invalid_input(self) -> None:
        add_breadcrumb(type="bad", value="x", name="y")  # type: ignore[arg-type]


class TestGetBreadcrumbsSnapshot:
    def test_returns_shallow_copy(self) -> None:
        add_breadcrumb(type="common", value="v", name="n")

        snapshot = get_breadcrumbs_snapshot()
        snapshot.append(
            {
                "type": "common",
                "value": "extra",
                "name": "extra",
                "capturedAt": datetime.now(timezone.utc).isoformat(),
            }
        )

        assert len(get_breadcrumbs_snapshot()) == 1
