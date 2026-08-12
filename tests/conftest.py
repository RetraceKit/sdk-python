"""Pytest configuration for retrace-kit tests."""

from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


@pytest.fixture(autouse=True)
def reset_sdk_state() -> Iterator[None]:
    """Reset module-level SDK state between tests."""
    from retrace_kit import (
        breadcrumbs,
        capture,
        config,
        handlers,
        server_url,
        tags,
        user,
    )

    handlers._reset_for_testing()
    config._reset_for_testing()
    user._reset_for_testing()
    tags._reset_for_testing()
    breadcrumbs._reset_for_testing()
    capture._reset_for_testing()
    server_url.set_configured_server_url(None)
    yield
    handlers._reset_for_testing()
    config._reset_for_testing()
    user._reset_for_testing()
    tags._reset_for_testing()
    breadcrumbs._reset_for_testing()
    capture._reset_for_testing()
    server_url.set_configured_server_url(None)
