"""FastAPI integration for Retrace Kit."""

from __future__ import annotations

from typing import Any, cast

from retrace_kit.breadcrumbs import add_breadcrumb
from retrace_kit.capture import capture_exception
from retrace_kit.config import is_capture_enabled
from retrace_kit.handlers import install_asyncio_handler


def _capture_route_error(request: Any, exc: BaseException) -> None:
    if not is_capture_enabled():
        return
    try:
        add_breadcrumb(
            type="route",
            name=request.method,
            value=request.url.path,
        )
        capture_exception(exc, context={"url": str(request.url)})
    except Exception:
        # Never throw into host application code.
        pass


def setup_fastapi(app: Any) -> None:
    """Register Retrace Kit exception handlers on a FastAPI app."""
    try:
        from fastapi.exception_handlers import http_exception_handler
        from starlette.exceptions import HTTPException as StarletteHTTPException
        from starlette.requests import Request
        from starlette.responses import JSONResponse, Response
        from starlette.websockets import WebSocketDisconnect
    except ImportError as exc:
        raise ImportError(
            "FastAPI integration requires fastapi. "
            "Install with: pip install retrace-kit[fastapi]",
        ) from exc

    previous_http_handler = app.exception_handlers.get(StarletteHTTPException)
    previous_exception_handler = app.exception_handlers.get(Exception)

    async def _default_exception_handler(
        request: Request,
        exc: Exception,
    ) -> Response:
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal Server Error"},
        )

    async def retrace_http_exception_handler(
        request: Request,
        exc: StarletteHTTPException,
    ) -> Response:
        if exc.status_code >= 500:
            _capture_route_error(request, exc)

        if previous_http_handler is not None:
            return cast(Response, await previous_http_handler(request, exc))
        return await http_exception_handler(request, exc)

    async def retrace_exception_handler(
        request: Request,
        exc: Exception,
    ) -> Response:
        if isinstance(exc, WebSocketDisconnect):
            if previous_exception_handler is not None:
                return cast(Response, await previous_exception_handler(request, exc))
            raise exc

        if isinstance(exc, StarletteHTTPException):
            if exc.status_code >= 500:
                _capture_route_error(request, exc)
            if previous_http_handler is not None:
                return cast(Response, await previous_http_handler(request, exc))
            return await http_exception_handler(request, exc)

        _capture_route_error(request, exc)

        if previous_exception_handler is not None:
            return cast(Response, await previous_exception_handler(request, exc))
        return await _default_exception_handler(request, exc)

    async def _install_asyncio_handler_on_startup() -> None:
        install_asyncio_handler()

    app.on_event("startup")(_install_asyncio_handler_on_startup)
    app.add_exception_handler(StarletteHTTPException, retrace_http_exception_handler)
    app.add_exception_handler(Exception, retrace_exception_handler)
