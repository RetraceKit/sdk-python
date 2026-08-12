"""Django management script for Retrace Kit example."""

from __future__ import annotations

import os
import sys


def main() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "mysite.settings")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Django is required. Install with: pip install retrace-kit[django]",
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
