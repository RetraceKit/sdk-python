"""Shared type definitions matching the JavaScript SDK."""

from __future__ import annotations

from typing import Literal, TypedDict

BreadcrumbType = Literal["request", "route", "common"]


class RetraceKitUser(TypedDict):
    """User context attached to error events."""

    id: str


class _RetraceKitConfigRequired(TypedDict):
    apiKey: str


class RetraceKitConfig(_RetraceKitConfigRequired, total=False):
    """SDK initialization options."""

    endpoint: str
    release: str
    environment: str
    enabled: bool
    serverUrl: str


class _BreadcrumbRequired(TypedDict):
    type: BreadcrumbType
    value: str
    name: str
    capturedAt: str


class Breadcrumb(_BreadcrumbRequired, total=False):
    """A single breadcrumb captured before an error."""

    status: int
    duration: int


class _IngestErrorEventPayloadRequired(TypedDict):
    message: str
    stacktrace: str


class IngestErrorEventPayload(_IngestErrorEventPayloadRequired, total=False):
    """Payload sent to the Retrace Kit error ingest endpoint."""

    timestamp: str
    name: str
    url: str
    release: str
    environment: str
    userAgent: str
    user: RetraceKitUser
    breadcrumbs: list[Breadcrumb]
    tags: dict[str, str]
    sessionId: str


class _IngestSessionPayloadRequired(TypedDict):
    sessionId: str


class IngestSessionPayload(_IngestSessionPayloadRequired, total=False):
    """Payload sent when registering or updating a session."""

    user: RetraceKitUser
    release: str
    environment: str
    timestamp: str
