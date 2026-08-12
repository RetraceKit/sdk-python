"""Tests for error deduplication."""

from __future__ import annotations

from retrace_kit.dedup import (
    DEDUP_WINDOW_MS,
    DedupCache,
    compute_dedup_key,
    extract_last_frame_name,
)

PYTHON_STACK = """Traceback (most recent call last):
  File "/app/main.py", line 10, in <module>
    main()
  File "/app/main.py", line 5, in helper
    raise ValueError("boom")
ValueError: boom"""

PYTHON_NESTED_STACK = """Traceback (most recent call last):
  File "/app/index.py", line 10, in outer
    inner()
  File "/app/index.py", line 5, in inner
    raise RuntimeError("fail")
RuntimeError: fail"""


class TestExtractLastFrameName:
    def test_returns_last_python_frame_function_name(self) -> None:
        assert extract_last_frame_name(PYTHON_STACK) == "helper"

    def test_returns_module_frame_name(self) -> None:
        stack = """Traceback (most recent call last):
  File "/app/run.py", line 1, in <module>
    raise SystemExit(1)
SystemExit: 1"""
        assert extract_last_frame_name(stack) == "<module>"

    def test_returns_unknown_for_empty_stacktrace(self) -> None:
        assert extract_last_frame_name("") == "unknown"
        assert extract_last_frame_name("   ") == "unknown"

    def test_returns_unknown_when_stack_has_no_frame_lines(self) -> None:
        assert extract_last_frame_name("No stacktrace available") == "unknown"
        assert extract_last_frame_name("ValueError: boom") == "unknown"

    def test_skips_non_frame_lines_and_uses_last_frame(self) -> None:
        assert extract_last_frame_name(PYTHON_NESTED_STACK) == "inner"


class TestComputeDedupKey:
    def test_produces_stable_key_for_same_fields(self) -> None:
        first = compute_dedup_key("ValueError", "boom", PYTHON_STACK)
        second = compute_dedup_key("ValueError", "boom", PYTHON_STACK)
        assert first == second
        assert len(first) > 0

    def test_normalizes_none_name_to_empty_string(self) -> None:
        with_name = compute_dedup_key("ValueError", "boom", PYTHON_STACK)
        without_name = compute_dedup_key(None, "boom", PYTHON_STACK)
        assert with_name != without_name

    def test_differentiates_keys_by_message(self) -> None:
        first = compute_dedup_key("ValueError", "first", PYTHON_STACK)
        second = compute_dedup_key("ValueError", "second", PYTHON_STACK)
        assert first != second

    def test_differentiates_keys_by_error_name(self) -> None:
        first = compute_dedup_key("ValueError", "boom", PYTHON_STACK)
        second = compute_dedup_key("RuntimeError", "boom", PYTHON_STACK)
        assert first != second

    def test_differentiates_keys_by_last_stack_frame(self) -> None:
        first_stack = """Traceback (most recent call last):
  File "app.py", line 1, in alpha
    raise ValueError("boom")
ValueError: boom"""
        second_stack = """Traceback (most recent call last):
  File "app.py", line 2, in beta
    raise ValueError("boom")
ValueError: boom"""
        first = compute_dedup_key("ValueError", "boom", first_stack)
        second = compute_dedup_key("ValueError", "boom", second_stack)
        assert first != second

    def test_uses_unknown_frame_fallback_in_key_when_stack_is_empty(self) -> None:
        key = compute_dedup_key("ValueError", "boom", "")
        assert key.endswith("\x1finner") is False
        assert key.endswith("\x1funknown")

    def test_includes_python_last_frame_name_in_dedup_key(self) -> None:
        key = compute_dedup_key("ValueError", "boom", PYTHON_STACK)
        assert key.endswith("\x1fhelper")


class TestDedupCache:
    def test_exports_30_second_dedup_window(self) -> None:
        assert DEDUP_WINDOW_MS == 30_000

    def test_allows_first_send_for_unseen_key(self) -> None:
        cache = DedupCache()
        now = 1_000_000
        assert cache.should_send("key-a", now) is True

    def test_suppresses_duplicate_sends_within_window(self) -> None:
        cache = DedupCache()
        first_send_at = 1_000_000
        cache.record_send("key-a", first_send_at)

        assert cache.should_send("key-a", first_send_at + 1) is False
        assert cache.should_send("key-a", first_send_at + DEDUP_WINDOW_MS - 1) is False

    def test_does_not_extend_window_on_repeat_record(self) -> None:
        cache = DedupCache()
        first_send_at = 1_000_000
        cache.record_send("key-a", first_send_at)
        cache.record_send("key-a", first_send_at + 5_000)

        assert cache.should_send("key-a", first_send_at + 10_000) is False
        assert cache.should_send("key-a", first_send_at + DEDUP_WINDOW_MS - 1) is False

    def test_allows_send_after_window_expires(self) -> None:
        cache = DedupCache()
        first_send_at = 1_000_000
        cache.record_send("key-a", first_send_at)

        assert cache.should_send("key-a", first_send_at + DEDUP_WINDOW_MS) is True
        assert cache.should_send("key-a", first_send_at + DEDUP_WINDOW_MS + 1) is True

    def test_starts_new_window_after_expiry_when_recording_again(self) -> None:
        cache = DedupCache()
        first_send_at = 1_000_000
        second_send_at = first_send_at + DEDUP_WINDOW_MS

        cache.record_send("key-a", first_send_at)
        assert cache.should_send("key-a", second_send_at) is True

        cache.record_send("key-a", second_send_at)
        assert cache.should_send("key-a", second_send_at + 1) is False
        assert cache.should_send("key-a", second_send_at + DEDUP_WINDOW_MS - 1) is False
        assert cache.should_send("key-a", second_send_at + DEDUP_WINDOW_MS) is True

    def test_tracks_keys_independently(self) -> None:
        cache = DedupCache()
        now = 1_000_000
        cache.record_send("key-a", now)

        assert cache.should_send("key-a", now + 1) is False
        assert cache.should_send("key-b", now + 1) is True

    def test_allows_one_send_per_window_over_five_minutes(self) -> None:
        cache = DedupCache()
        key = "key-a"
        five_minutes_ms = 5 * 60 * 1_000
        sends = 0

        for elapsed_ms in range(0, five_minutes_ms + 1, 100):
            if cache.should_send(key, elapsed_ms):
                cache.record_send(key, elapsed_ms)
                sends += 1

        assert sends == 11
