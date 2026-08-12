"""Configured server URL storage for later capture use."""

from __future__ import annotations

_configured_server_url: str | None = None


def set_configured_server_url(url: str | None) -> None:
    """Store the configured server URL from init."""
    global _configured_server_url
    _configured_server_url = url


def get_configured_server_url() -> str | None:
    """Return the configured server URL, if any."""
    return _configured_server_url
