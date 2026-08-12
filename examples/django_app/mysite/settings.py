"""Minimal Django settings for Retrace Kit example."""

from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "example-secret-key")
DEBUG = True
ALLOWED_HOSTS: list[str] = ["*"]

INSTALLED_APPS: list[str] = []

MIDDLEWARE = [
    "django.middleware.common.CommonMiddleware",
    "retrace_kit.integrations.django.RetraceKitMiddleware",
]

ROOT_URLCONF = "mysite.urls"

TEMPLATES: list[dict[str, object]] = []

WSGI_APPLICATION = "mysite.wsgi.application"

DATABASES: dict[str, dict[str, object]] = {}

USE_TZ = True
