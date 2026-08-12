"""Retrace Kit Python SDK."""

from retrace_kit.breadcrumbs import add_breadcrumb
from retrace_kit.capture import capture_exception
from retrace_kit.config import init
from retrace_kit.handlers import install_asyncio_handler
from retrace_kit.tags import set_tag
from retrace_kit.types import (
    Breadcrumb,
    BreadcrumbType,
    IngestErrorEventPayload,
    IngestSessionPayload,
    RetraceKitConfig,
    RetraceKitUser,
)
from retrace_kit.user import set_user
from retrace_kit.version import __version__

__all__ = [
    "Breadcrumb",
    "BreadcrumbType",
    "IngestErrorEventPayload",
    "IngestSessionPayload",
    "RetraceKitConfig",
    "RetraceKitUser",
    "__version__",
    "add_breadcrumb",
    "capture_exception",
    "init",
    "install_asyncio_handler",
    "set_tag",
    "set_user",
]
