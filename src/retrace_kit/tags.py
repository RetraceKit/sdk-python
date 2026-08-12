"""Tag management."""

from __future__ import annotations

_tags: dict[str, str] = {}


def set_tag(name: str, value: str) -> None:
    """Set a global tag for subsequent error events. Never throws."""
    try:
        key = name.strip() if isinstance(name, str) else ""
        if not key:
            return

        tag_value = value if isinstance(value, str) else str(value if value is not None else "")
        _tags[key] = tag_value
    except Exception:
        # Never throw into host application code.
        pass


def get_tags_snapshot() -> dict[str, str]:
    """Return a snapshot of current tags."""
    return dict(_tags)


def _reset_for_testing() -> None:
    """Reset module state (tests only)."""
    _tags.clear()
