"""Django integration for Retrace Kit."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from retrace_kit.breadcrumbs import add_breadcrumb
from retrace_kit.capture import capture_exception
from retrace_kit.config import is_capture_enabled


class RetraceKitMiddleware:
    """Django middleware that captures unhandled server exceptions."""

    def __init__(self, get_response: Callable[..., Any]) -> None:
        self.get_response = get_response

    def __call__(self, request: Any) -> Any:
        return self.get_response(request)

    def process_exception(self, request: Any, exception: BaseException) -> None:
        """Capture unhandled exceptions; return None so Django continues handling."""
        try:
            from django.core.exceptions import PermissionDenied  # type: ignore[import-untyped]
            from django.http import Http404  # type: ignore[import-untyped]
        except ImportError:
            return

        if isinstance(exception, (Http404, PermissionDenied)):
            return

        if not is_capture_enabled():
            return

        try:
            add_breadcrumb(
                type="route",
                name=request.method,
                value=request.path,
            )
            capture_exception(
                exception,
                context={"url": request.build_absolute_uri()},
            )
        except Exception:
            # Never throw into host application code.
            pass

        return
