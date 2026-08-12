"""Tests for Django integration."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import django
import pytest
from django.conf import settings
from django.http import Http404, HttpRequest, HttpResponse, JsonResponse
from django.test import Client, RequestFactory
from django.urls import path

from retrace_kit.config import init
from retrace_kit.integrations.django import RetraceKitMiddleware


def _configure_django() -> None:
    if settings.configured:
        return

    root = Path(__file__).resolve().parent
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    settings.configure(
        DEBUG=True,
        SECRET_KEY="test-secret-key",
        ROOT_URLCONF=__name__,
        MIDDLEWARE=[
            "django.middleware.common.CommonMiddleware",
            "retrace_kit.integrations.django.RetraceKitMiddleware",
        ],
        ALLOWED_HOSTS=["testserver"],
        USE_TZ=True,
    )
    django.setup()


def health(_request: HttpRequest) -> JsonResponse:
    return JsonResponse({"status": "ok"})


def boom(_request: HttpRequest) -> HttpResponse:
    raise ValueError("boom")


def missing(_request: HttpRequest) -> HttpResponse:
    raise Http404("missing")


urlpatterns = [
    path("health", health),
    path("boom", boom),
    path("missing", missing),
]


@pytest.fixture(scope="module", autouse=True)
def django_setup() -> None:
    _configure_django()


@pytest.fixture
def middleware() -> RetraceKitMiddleware:
    return RetraceKitMiddleware(get_response=lambda request: HttpResponse("ok"))


class TestRetraceKitMiddleware:
    def test_view_exception_sends_event(self) -> None:
        with (
            patch("retrace_kit.transport.urlopen") as mock_urlopen,
            patch("retrace_kit.capture.send_error_event") as mock_send,
        ):
            mock_response = mock_urlopen.return_value.__enter__.return_value
            mock_response.status = 200
            init(api_key="test-key", enabled=True)
            response = Client(raise_request_exception=False).get("/boom")

        assert response.status_code == 500
        mock_send.assert_called_once()
        payload = mock_send.call_args[0][0]
        assert payload["name"] == "ValueError"
        assert payload["message"] == "boom"
        assert payload["url"] == "http://testserver/boom"
        assert payload["breadcrumbs"][-1]["type"] == "route"
        assert payload["breadcrumbs"][-1]["name"] == "GET"
        assert payload["breadcrumbs"][-1]["value"] == "/boom"

    def test_success_response_does_not_send_event(self) -> None:
        with (
            patch("retrace_kit.transport.urlopen") as mock_urlopen,
            patch("retrace_kit.capture.send_error_event") as mock_send,
        ):
            mock_response = mock_urlopen.return_value.__enter__.return_value
            mock_response.status = 200
            init(api_key="test-key", enabled=True)
            response = Client().get("/health")

        assert response.status_code == 200
        mock_send.assert_not_called()

    def test_http404_does_not_send_event(self) -> None:
        with (
            patch("retrace_kit.transport.urlopen") as mock_urlopen,
            patch("retrace_kit.capture.send_error_event") as mock_send,
        ):
            mock_response = mock_urlopen.return_value.__enter__.return_value
            mock_response.status = 200
            init(api_key="test-key", enabled=True)
            response = Client().get("/missing")

        assert response.status_code == 404
        mock_send.assert_not_called()

    def test_process_exception_skips_client_errors(
        self,
        middleware: RetraceKitMiddleware,
    ) -> None:
        with (
            patch("retrace_kit.transport.urlopen") as mock_urlopen,
            patch("retrace_kit.capture.send_error_event") as mock_send,
        ):
            mock_response = mock_urlopen.return_value.__enter__.return_value
            mock_response.status = 200
            init(api_key="test-key", enabled=True)
            request = RequestFactory().get("/missing")
            result = middleware.process_exception(request, Http404("missing"))

        assert result is None
        mock_send.assert_not_called()
