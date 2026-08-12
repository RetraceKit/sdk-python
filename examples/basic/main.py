"""Basic Retrace Kit usage: init and manual exception capture."""

from __future__ import annotations

import os

from retrace_kit import capture_exception, init


def main() -> None:
    init(
        api_key=os.environ.get("RETRACEKIT_API_KEY", "your-project-api-key"),
        release=os.environ.get("RETRACEKIT_RELEASE"),
        environment=os.environ.get("RETRACEKIT_ENVIRONMENT", "development"),
    )

    try:
        raise RuntimeError("demo error from basic example")
    except RuntimeError as exc:
        capture_exception(exc, context={"url": "https://example.com/basic-demo"})

    print("Captured demo exception. Check your Retrace Kit dashboard.")


if __name__ == "__main__":
    main()
