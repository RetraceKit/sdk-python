"""Minimal FastAPI app with Retrace Kit integration."""

from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException

from retrace_kit import init
from retrace_kit.integrations.fastapi import setup_fastapi

init(
    api_key=os.environ.get("RETRACEKIT_API_KEY", "your-project-api-key"),
    release=os.environ.get("RETRACEKIT_RELEASE"),
    environment=os.environ.get("RETRACEKIT_ENVIRONMENT", "development"),
)

app = FastAPI(title="Retrace Kit FastAPI Example")
setup_fastapi(app)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/boom")
def boom() -> None:
    raise ValueError("unhandled server error")


@app.get("/missing")
def missing() -> None:
    raise HTTPException(status_code=404, detail="not found")
