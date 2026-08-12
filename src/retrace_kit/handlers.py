"""Global exception and signal handlers."""

from __future__ import annotations

import asyncio
import sys
import threading
from collections.abc import Callable
from types import TracebackType
from typing import Any, cast

ExcHook = Callable[
    [type[BaseException], BaseException | None, TracebackType | None],
    Any,
]
ThreadExcHook = Callable[[threading.ExceptHookArgs], Any]
AsyncioExcHandler = Callable[[asyncio.AbstractEventLoop, dict[str, Any]], Any]

_previous_sys_excepthook: ExcHook | None = None
_installed_sys_excepthook: ExcHook | None = None

_previous_threading_excepthook: ThreadExcHook | None = None
_installed_threading_excepthook: ThreadExcHook | None = None

_asyncio_loop_handlers: dict[
    asyncio.AbstractEventLoop,
    tuple[AsyncioExcHandler, AsyncioExcHandler | None],
] = {}


def _capture_exception(error: object) -> None:
    from retrace_kit.capture import capture_exception

    capture_exception(error)


def _capture_from_exc_info(
    exc_type: type[BaseException] | None,
    exc_value: BaseException | None,
    exc_tb: TracebackType | None,
) -> None:
    if exc_type is None:
        return

    if exc_value is None:
        exc_value = exc_type()

    if not isinstance(exc_value, BaseException):
        _capture_exception(exc_value)
        return

    if exc_tb is not None and exc_value.__traceback__ is not exc_tb:
        exc_value = exc_value.with_traceback(exc_tb)

    _capture_exception(exc_value)


def _make_sys_excepthook(previous: ExcHook | None) -> ExcHook:
    def hook(
        exc_type: type[BaseException],
        exc_value: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        try:
            _capture_from_exc_info(exc_type, exc_value, exc_tb)
        except Exception:
            pass

        if previous is not None and previous is not hook:
            try:
                previous(exc_type, exc_value, exc_tb)
            except Exception:
                pass

    return hook


def _make_threading_excepthook(previous: ThreadExcHook | None) -> ThreadExcHook:
    def hook(args: threading.ExceptHookArgs) -> None:
        try:
            _capture_from_exc_info(args.exc_type, args.exc_value, args.exc_traceback)
        except Exception:
            pass

        if previous is not None and previous is not hook:
            try:
                previous(args)
            except Exception:
                pass

    return hook


def _make_asyncio_handler(previous: AsyncioExcHandler | None) -> AsyncioExcHandler:
    def handler(loop: asyncio.AbstractEventLoop, context: dict[str, Any]) -> None:
        try:
            exception = context.get("exception")
            if exception is not None:
                _capture_exception(exception)
        except Exception:
            pass

        if previous is not None and previous is not handler:
            try:
                previous(loop, context)
            except Exception:
                pass
        else:
            try:
                loop.default_exception_handler(context)
            except Exception:
                pass

    return handler


def install_handlers() -> None:
    """Install global exception handlers. Never throws."""
    global _previous_sys_excepthook, _installed_sys_excepthook
    global _previous_threading_excepthook, _installed_threading_excepthook

    try:
        current_sys = cast(ExcHook, sys.excepthook)
        if _installed_sys_excepthook is not current_sys:
            _previous_sys_excepthook = current_sys
            _installed_sys_excepthook = _make_sys_excepthook(_previous_sys_excepthook)
            sys.excepthook = _installed_sys_excepthook

        if hasattr(threading, "excepthook"):
            current_thread = cast(ThreadExcHook, threading.excepthook)
            if _installed_threading_excepthook is not current_thread:
                _previous_threading_excepthook = current_thread
                _installed_threading_excepthook = _make_threading_excepthook(
                    _previous_threading_excepthook,
                )
                threading.excepthook = _installed_threading_excepthook
    except Exception:
        pass


def uninstall_handlers() -> None:
    """Remove global exception handlers and restore previous hooks."""
    global _previous_sys_excepthook, _installed_sys_excepthook
    global _previous_threading_excepthook, _installed_threading_excepthook

    try:
        if _installed_sys_excepthook is not None and sys.excepthook is _installed_sys_excepthook:
            sys.excepthook = _previous_sys_excepthook or sys.__excepthook__
        _previous_sys_excepthook = None
        _installed_sys_excepthook = None

        if hasattr(threading, "excepthook"):
            if (
                _installed_threading_excepthook is not None
                and threading.excepthook is _installed_threading_excepthook
                and _previous_threading_excepthook is not None
            ):
                threading.excepthook = _previous_threading_excepthook
            _previous_threading_excepthook = None
            _installed_threading_excepthook = None

        for loop, (our_handler, previous) in list(_asyncio_loop_handlers.items()):
            try:
                if loop.get_exception_handler() is our_handler:
                    loop.set_exception_handler(previous)
            except Exception:
                pass
        _asyncio_loop_handlers.clear()
    except Exception:
        pass


def install_asyncio_handler(loop: asyncio.AbstractEventLoop | None = None) -> None:
    """Install an asyncio loop exception handler. Never throws."""
    try:
        target_loop = loop
        if target_loop is None:
            try:
                target_loop = asyncio.get_running_loop()
            except RuntimeError:
                return

        if target_loop in _asyncio_loop_handlers:
            return

        previous = cast(AsyncioExcHandler | None, target_loop.get_exception_handler())
        our_handler = _make_asyncio_handler(previous)
        _asyncio_loop_handlers[target_loop] = (our_handler, previous)
        target_loop.set_exception_handler(our_handler)
    except Exception:
        pass


def _reset_for_testing() -> None:
    """Reset module state (tests only)."""
    uninstall_handlers()
