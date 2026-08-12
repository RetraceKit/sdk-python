"""Tests for user context management."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from retrace_kit.user import get_user, sanitize_user, set_user


class TestSanitizeUser:
    @pytest.mark.parametrize(
        ("user", "expected"),
        [
            ({"id": "user-1"}, {"id": "user-1"}),
            ({"id": "  user-2  "}, {"id": "user-2"}),
            (None, None),
            ({}, None),
            ({"id": ""}, None),
            ({"id": "   "}, None),
            ({"id": 123}, None),
            ("not-a-dict", None),
        ],
    )
    def test_sanitize_user(self, user: object, expected: object) -> None:
        assert sanitize_user(user) == expected


class TestSetUser:
    def test_accepts_dict_form(self) -> None:
        set_user({"id": "dict-user"})
        assert get_user() == {"id": "dict-user"}

    def test_accepts_keyword_id(self) -> None:
        set_user(id="keyword-user")
        assert get_user() == {"id": "keyword-user"}

    def test_accepts_string_form(self) -> None:
        set_user("string-user")
        assert get_user() == {"id": "string-user"}

    @pytest.mark.parametrize(
        "bad_input",
        [
            {"id": ""},
            {"id": 42},
            {"name": "no-id"},
        ],
    )
    def test_bad_input_is_no_op(self, bad_input: object) -> None:
        set_user({"id": "keep-me"})
        set_user(bad_input)  # type: ignore[arg-type]
        assert get_user() == {"id": "keep-me"}

    def test_never_raises_on_bad_input(self) -> None:
        set_user(object())  # type: ignore[arg-type]

    def test_pings_session_when_capture_enabled(self) -> None:
        with patch("retrace_kit.config.is_capture_enabled", return_value=True):
            with patch("retrace_kit.config.ping_session") as mock_ping:
                set_user({"id": "ping-user"})
        mock_ping.assert_called_once()
