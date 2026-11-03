"""Serve the built web interface and API from the same container origin."""

from pathlib import Path
import re

from fastapi import APIRouter, FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.gzip import GZipMiddleware


class FrontendStaticFiles(StaticFiles):
    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        # Only successful, content-versioned build assets can outlive a release.
        # HTML and the unversioned recording worklet must still be fetched fresh.
        if response.status_code in {200, 304} and re.fullmatch(
            r"assets/[\w.-]+-[\w-]{8,}\.(?:js|css)", path.replace("\\", "/"), flags=re.ASCII,
        ):
            scope.setdefault("state", {})["immutable_frontend_asset"] = True
        return response


def mount_frontend(app: FastAPI, router: APIRouter, directory: Path) -> None:
    if not (directory / "index.html").is_file():
        raise RuntimeError("SERVE_FRONTEND requires the built frontend/dist/index.html.")
    # Reuse the protected routes; API requests must precede the public static mount.
    app.include_router(router, prefix="/api")
    # Compress public files only; private API bodies keep their existing policy.
    app.mount("/", GZipMiddleware(FrontendStaticFiles(directory=directory, html=True),
                                 minimum_size=1000, compresslevel=6), name="frontend")
