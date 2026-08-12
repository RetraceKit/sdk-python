"""User context management."""

from __future__ import annotations

from retrace_kit.types import RetraceKitUser

_current_user: RetraceKitUser | None = None


def sanitize_user(user: object) -> RetraceKitUser | None:
    """Normalize user input to a valid RetraceKitUser or None."""
    try:
        if user is None or not isinstance(user, dict):
            return None

        raw_id = user.get("id")
        if not isinstance(raw_id, str):
            return None

        user_id = raw_id.strip()
        if not user_id:
            return None

        return {"id": user_id}
    except Exception:
        return None


def set_user(
    user: RetraceKitUser | str | None = None,
    *,
    id: str | None = None,
) -> None:
    """Set the current user for subsequent error events. Never throws."""
    try:
        normalized: RetraceKitUser | None = None

        if isinstance(user, dict):
            normalized = sanitize_user(user)
        elif isinstance(user, str):
            normalized = sanitize_user({"id": user})
        elif id is not None:
            normalized = sanitize_user({"id": id})
        else:
            return

        if normalized is None:
            return

        global _current_user
        _current_user = normalized

        from retrace_kit.config import is_capture_enabled, ping_session

        if is_capture_enabled():
            ping_session()
    except Exception:
        # Never throw into host application code.
        pass


def get_user() -> RetraceKitUser | None:
    """Return the current user, if set."""
    return _current_user


def _reset_for_testing() -> None:
    """Reset module state (tests only)."""
    global _current_user
    _current_user = None
