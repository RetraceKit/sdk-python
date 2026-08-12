"""URL routes for Retrace Kit Django example."""

from __future__ import annotations

from django.http import Http404, HttpRequest, HttpResponse, JsonResponse
from django.urls import path


def health(_request: HttpRequest) -> JsonResponse:
    return JsonResponse({"status": "ok"})


def boom(_request: HttpRequest) -> HttpResponse:
    raise ValueError("unhandled server error")


def missing(_request: HttpRequest) -> HttpResponse:
    raise Http404("not found")


urlpatterns = [
    path("health", health),
    path("boom", boom),
    path("missing", missing),
]
