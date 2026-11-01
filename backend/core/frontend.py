"""Serve the built web interface and API from the same container origin."""

from pathlib import Path

from fastapi import APIRouter, FastAPI
from fastapi.staticfiles import StaticFiles


def mount_frontend(app: FastAPI, router: APIRouter, directory: Path) -> None:
    if not (directory / "index.html").is_file():
        raise RuntimeError("SERVE_FRONTEND requires the built frontend/dist/index.html.")
    # Reuse the protected routes; API requests must precede the public static mount.
    app.include_router(router, prefix="/api")
    app.mount("/", StaticFiles(directory=directory, html=True), name="frontend")
