"""WSGI entrypoint for Retrace Kit Django example."""

from __future__ import annotations

import os

from django.core.wsgi import get_wsgi_application

from retrace_kit import init

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "mysite.settings")

init(
    api_key=os.environ.get("RETRACEKIT_API_KEY", "your-project-api-key"),
    release=os.environ.get("RETRACEKIT_RELEASE"),
    environment=os.environ.get("RETRACEKIT_ENVIRONMENT", "development"),
)

application = get_wsgi_application()
