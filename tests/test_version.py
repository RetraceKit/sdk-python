"""Tests for package version."""

from retrace_kit import __version__


def test_version_is_string() -> None:
    assert isinstance(__version__, str)
    assert __version__


def test_version_format() -> None:
    parts = __version__.split(".")
    assert len(parts) >= 2
    assert all(part.isdigit() for part in parts)
