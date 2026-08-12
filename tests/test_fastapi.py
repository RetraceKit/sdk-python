"""Tests for FastAPI integration."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from retrace_kit.config import init
from retrace_kit.integrations.fastapi import setup_fastapi


@pytest.fixture
def fastapi_app() -> FastAPI:
    with patch("retrace_kit.transport.urlopen") as mock_urlopen:
        mock_response = mock_urlopen.return_value.__enter__.return_value
        mock_response.status = 200
        init(api_key="test-key", enabled=True)

    app = FastAPI()
    setup_fastapi(app)

    @app.get("/error")
    def error_route() -> None:
        raise ValueError("boom")

    @app.get("/not-found")
    def not_found_route() -> None:
        raise HTTPException(status_code=404, detail="missing")

    @app.get("/server-error")
    def server_error_route() -> None:
        raise HTTPException(status_code=500, detail="fail")

    @app.get("/ok")
    def ok_route() -> dict[str, str]:
        return {"status": "ok"}

    return app


class TestSetupFastAPI:
    def test_import_error_when_fastapi_missing(self) -> None:
        import builtins

        real_import = builtins.__import__

        def fake_import(
            name: str,
            globals: object | None = None,
            locals: object | None = None,
            fromlist: object = (),
            level: int = 0,
        ) -> object:
            if name == "fastapi" or name.startswith("fastapi."):
                raise ImportError("No module named 'fastapi'")
            if name == "starlette" or name.startswith("starlette."):
                raise ImportError("No module named 'starlette'")
            return real_import(name, globals, locals, fromlist, level)

        with patch("builtins.__import__", side_effect=fake_import):
            with pytest.raises(ImportError, match="retrace-kit\\[fastapi\\]"):
                setup_fastapi(FastAPI())

    def test_unhandled_exception_sends_one_event(self, fastapi_app: FastAPI) -> None:
        with patch("retrace_kit.capture.send_error_event") as mock_send:
            client = TestClient(fastapi_app, raise_server_exceptions=False)
            response = client.get("/error")

        assert response.status_code == 500
        mock_send.assert_called_once()
        payload = mock_send.call_args[0][0]
        assert payload["name"] == "ValueError"
        assert payload["message"] == "boom"
        assert payload["url"] == "http://testserver/error"
        assert payload["breadcrumbs"]
        assert payload["breadcrumbs"][-1]["type"] == "route"
        assert payload["breadcrumbs"][-1]["name"] == "GET"
        assert payload["breadcrumbs"][-1]["value"] == "/error"

    def test_http_404_does_not_send_event(self, fastapi_app: FastAPI) -> None:
        with patch("retrace_kit.capture.send_error_event") as mock_send:
            client = TestClient(fastapi_app, raise_server_exceptions=False)
            response = client.get("/not-found")

        assert response.status_code == 404
        mock_send.assert_not_called()

    def test_http_500_sends_event(self, fastapi_app: FastAPI) -> None:
        with patch("retrace_kit.capture.send_error_event") as mock_send:
            client = TestClient(fastapi_app, raise_server_exceptions=False)
            response = client.get("/server-error")

        assert response.status_code == 500
        mock_send.assert_called_once()
        payload = mock_send.call_args[0][0]
        assert payload["name"] == "HTTPException"
        assert payload["url"] == "http://testserver/server-error"

    def test_delegates_to_previous_exception_handler(self) -> None:
        with patch("retrace_kit.transport.urlopen") as mock_urlopen:
            mock_response = mock_urlopen.return_value.__enter__.return_value
            mock_response.status = 200
            init(api_key="test-key", enabled=True)

        app = FastAPI()

        from starlette.responses import JSONResponse

        async def custom_exception_handler_response(
            request: object,
            exc: Exception,
        ) -> JSONResponse:
            return JSONResponse(status_code=418, content={"detail": "custom"})

        app.add_exception_handler(Exception, custom_exception_handler_response)
        setup_fastapi(app)

        @app.get("/error")
        def error_route() -> None:
            raise ValueError("boom")

        with patch("retrace_kit.capture.send_error_event") as mock_send:
            client = TestClient(app, raise_server_exceptions=False)
            response = client.get("/error")

        assert response.status_code == 418
        assert response.json() == {"detail": "custom"}
        mock_send.assert_called_once()

    def test_installs_asyncio_handler_on_startup(self) -> None:
        with patch("retrace_kit.transport.urlopen") as mock_urlopen:
            mock_response = mock_urlopen.return_value.__enter__.return_value
            mock_response.status = 200
            init(api_key="test-key", enabled=True)

        app = FastAPI()
        with patch("retrace_kit.integrations.fastapi.install_asyncio_handler") as mock_install:
            setup_fastapi(app)
            with TestClient(app):
                pass

        mock_install.assert_called_once()
