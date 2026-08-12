# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-08-12

### Added

- Core SDK with `init`, `capture_exception`, breadcrumbs, user context, and tags
- Automatic capture via global handlers for uncaught exceptions, threading errors, and asyncio loop exceptions
- Event deduplication and background transport to the Retrace Kit ingest API
- Session ping on initialization
- FastAPI integration (`setup_fastapi`) for automatic 5xx and unhandled exception reporting with route breadcrumbs
- Django integration (`RetraceKitMiddleware`) for automatic view exception reporting (ignores `Http404` and `PermissionDenied`)
- Typed public API with strict mypy coverage
- Example apps for basic usage, FastAPI, and Django
- Development tooling: pytest, ruff, and mypy

[0.1.0]: https://github.com/RetraceKit/sdk-python/releases/tag/v0.1.0
