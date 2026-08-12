"""Tests for global exception handlers."""

from __future__ import annotations

import asyncio
import sys
import threading
from types import SimpleNamespace, TracebackType
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from retrace_kit.config import init
from retrace_kit.handlers import (
    install_asyncio_handler,
    install_handlers,
    uninstall_handlers,
)


@pytest.fixture
def sync_background_threads(monkeypatch: pytest.MonkeyPatch) -> None:
    """Run background transport threads synchronously in tests."""

    def immediate_start(self: threading.Thread) -> None:
        self._target(*self._args, **self._kwargs)  # type: ignore[misc]

    monkeypatch.setattr(threading.Thread, "start", immediate_start)


def _make_exc_info(message: str = "uncaught") -> tuple[
    type[BaseException],
    BaseException,
    TracebackType | None,
]:
    try:
        raise ValueError(message)
    except ValueError:
        exc_type, exc_value, exc_tb = sys.exc_info()
        assert exc_type is not None
        assert exc_value is not None
        return exc_type, exc_value, exc_tb


class TestSysExcepthook:
    def test_calls_capture_exception(
        self,
        sync_background_threads: None,
    ) -> None:
        with patch("retrace_kit.capture.send_error_event") as mock_send:
            init(api_key="test-key")
            exc_type, exc_value, exc_tb = _make_exc_info("hook error")
            sys.excepthook(exc_type, exc_value, exc_tb)

        mock_send.assert_called_once()
        payload = mock_send.call_args[0][0]
        assert payload["name"] == "ValueError"
        assert payload["message"] == "hook error"
        assert "Traceback" in payload["stacktrace"]
        assert "hook error" in payload["stacktrace"]

    def test_chains_previous_excepthook(self) -> None:
        chained: list[tuple[Any, Any, Any]] = []

        def previous_hook(
            exc_type: type[BaseException],
            exc_value: BaseException | None,
            exc_tb: TracebackType | None,
        ) -> None:
            chained.append((exc_type, exc_value, exc_tb))

        sys.excepthook = previous_hook
        install_handlers()

        exc_type, exc_value, exc_tb = _make_exc_info("chain me")
        sys.excepthook(exc_type, exc_value, exc_tb)

        assert len(chained) == 1
        assert chained[0][0] is ValueError
        assert chained[0][1] is exc_value

    def test_uninstall_restores_previous_excepthook(self) -> None:
        def previous_hook(
            exc_type: type[BaseException],
            exc_value: BaseException | None,
            exc_tb: TracebackType | None,
        ) -> None:
            pass

        sys.excepthook = previous_hook
        install_handlers()
        assert sys.excepthook is not previous_hook

        uninstall_handlers()
        assert sys.excepthook is previous_hook


class TestThreadingExcepthook:
    def test_smoke_capture_and_chain(self, sync_background_threads: None) -> None:
        if not hasattr(threading, "excepthook"):
            pytest.skip("threading.excepthook unavailable")

        chained: list[threading.ExceptHookArgs] = []

        def previous_hook(args: threading.ExceptHookArgs) -> None:
            chained.append(args)

        threading.excepthook = previous_hook

        with patch("retrace_kit.config.send_session_ping"):
            with patch("retrace_kit.capture.send_error_event") as mock_send:
                init(api_key="test-key")
                exc_type, exc_value, exc_tb = _make_exc_info("thread hook")
                args = SimpleNamespace(
                    exc_type=exc_type,
                    exc_value=exc_value,
                    exc_traceback=exc_tb,
                    thread=threading.current_thread(),
                )
                threading.excepthook(args)  # type: ignore[arg-type]

        mock_send.assert_called_once()
        assert len(chained) == 1
        assert chained[0].exc_value is exc_value


class TestAsyncioHandler:
    def test_captures_loop_exception_and_chains_previous(
        self,
        sync_background_threads: None,
    ) -> None:
        loop = asyncio.new_event_loop()
        chained: list[dict[str, Any]] = []

        def previous_handler(
            _loop: asyncio.AbstractEventLoop,
            context: dict[str, Any],
        ) -> None:
            chained.append(context)

        loop.set_exception_handler(previous_handler)

        with patch("retrace_kit.capture.send_error_event") as mock_send:
            init(api_key="test-key")
            install_asyncio_handler(loop)

            error = RuntimeError("async failure")
            context = {"exception": error, "message": "Task exception was never retrieved"}
            handler = loop.get_exception_handler()
            assert handler is not None
            handler(loop, context)

        mock_send.assert_called_once()
        sent_payload = mock_send.call_args[0][0]
        assert sent_payload["name"] == "RuntimeError"
        assert sent_payload["message"] == "async failure"
        assert len(chained) == 1
        assert chained[0]["exception"] is error

        loop.close()

    def test_calls_default_handler_when_no_previous(
        self,
        sync_background_threads: None,
    ) -> None:
        loop = asyncio.new_event_loop()
        loop.set_exception_handler(None)

        with patch("retrace_kit.capture.send_error_event") as mock_send:
            init(api_key="test-key")
            install_asyncio_handler(loop)

            error = RuntimeError("async failure")
            context = {"exception": error, "message": "Task exception was never retrieved"}
            handler = loop.get_exception_handler()
            assert handler is not None

            with patch.object(loop, "default_exception_handler") as mock_default:
                handler(loop, context)

        mock_send.assert_called_once()
        mock_default.assert_called_once_with(context)

        loop.close()


class TestHandlersNeverRaise:
    def test_install_handlers_never_raises_when_assignment_fails(self) -> None:
        with patch(
            "retrace_kit.handlers.sys.excepthook",
            new_callable=MagicMock,
            side_effect=RuntimeError("blocked"),
        ):
            install_handlers()

    def test_uninstall_handlers_never_raises_when_restore_fails(self) -> None:
        install_handlers()
        with patch(
            "retrace_kit.handlers.sys.excepthook",
            new_callable=MagicMock,
            side_effect=RuntimeError("blocked"),
        ):
            uninstall_handlers()

    def test_hook_never_raises_when_capture_fails(self) -> None:
        install_handlers()
        with patch(
            "retrace_kit.handlers._capture_exception",
            side_effect=RuntimeError("capture failed"),
        ):
            exc_type, exc_value, exc_tb = _make_exc_info()
            sys.excepthook(exc_type, exc_value, exc_tb)

    def test_install_asyncio_handler_never_raises(self) -> None:
        loop = asyncio.new_event_loop()
        with patch.object(
            loop,
            "set_exception_handler",
            side_effect=RuntimeError("blocked"),
        ):
            install_asyncio_handler(loop)
        loop.close()
