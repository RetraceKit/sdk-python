"""Deduplication of repeated error events."""

from __future__ import annotations

import re

DEDUP_WINDOW_MS = 30_000

_DEDUP_KEY_DELIMITER = "\x1f"
_EMPTY_STACK_FALLBACK = "unknown"


def _is_frame_line(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith(('File "', "File '"))


def _parse_frame_function_name(line: str) -> str | None:
    match = re.search(r" in (\S+)\s*$", line.strip())
    if not match:
        return None

    function_name = match.group(1).strip()
    return function_name or None


def extract_last_frame_name(stacktrace: str) -> str:
    """Extract the function name from the last stack frame line, or a fallback."""
    if not stacktrace.strip():
        return _EMPTY_STACK_FALLBACK

    lines = stacktrace.split("\n")
    for index in range(len(lines) - 1, -1, -1):
        line = lines[index]
        if not _is_frame_line(line):
            continue

        function_name = _parse_frame_function_name(line)
        if function_name:
            return function_name

    return _EMPTY_STACK_FALLBACK


def compute_dedup_key(
    name: str | None,
    message: str,
    stacktrace: str,
) -> str:
    """Build a dedup key from raw error name, message, and stacktrace."""
    frame_name = extract_last_frame_name(stacktrace)
    normalized_name = name if name is not None else ""
    return f"{normalized_name}{_DEDUP_KEY_DELIMITER}{message}{_DEDUP_KEY_DELIMITER}{frame_name}"


class DedupCache:
    """In-memory cache that suppresses duplicate sends within a fixed window."""

    def __init__(self) -> None:
        self._entries: dict[str, int] = {}

    def should_send(self, key: str, now: int) -> bool:
        first_sent_at = self._entries.get(key)
        if first_sent_at is None:
            return True
        return now - first_sent_at >= DEDUP_WINDOW_MS

    def record_send(self, key: str, now: int) -> None:
        first_sent_at = self._entries.get(key)
        if first_sent_at is None or now - first_sent_at >= DEDUP_WINDOW_MS:
            self._entries[key] = now

    def clear(self) -> None:
        """Reset cache state (tests only)."""
        self._entries.clear()
