"""Bound incoming bodies and prevent caching of private API responses."""

from anyio import fail_after
from contextlib import contextmanager
import logging
import time
from uuid import uuid4
from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import JSONResponse
from starlette.middleware.httpsredirect import HTTPSRedirectMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.types import ASGIApp, Message, Receive, Scope, Send


MAX_JSON_BYTES = 64 * 1024
MAX_BODY_BYTES = 1024 * 1024
BODY_TIMEOUT_SECONDS = 15
timing_logger = logging.getLogger("uvicorn.error.request_timing")
TIMED_ROUTES = {prefix + path for prefix in ("", "/api", "/api/v1")
                for path in ("/me", "/me/startup", "/children", "/conversations", "/coach", "/speech/transcribe")}


@contextmanager
def timed_request_stage(request, stage: str):
    started = time.perf_counter()
    try:
        yield
    finally:
        request_id = getattr(request.state, "performance_request_id", None)
        if request_id:
            timing_logger.info("request_stage request=%s stage=%s seconds=%.3f",
                               request_id, stage, time.perf_counter() - started)


def configure_http_security(app, *, production: bool, allowed_hosts: list[str]) -> None:
    if production:
        app.add_middleware(HTTPSRedirectMiddleware)
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)
    # Apply response protections to host rejections and redirects too.
    app.add_middleware(HTTPSecurityMiddleware)


class HTTPSecurityMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        started = time.perf_counter()
        # Mounts may copy the ASGI scope; share the state mapping with the static
        # host so only its validated public assets can opt into caching.
        scope.setdefault("state", {})
        timed = scope.get("path") in TIMED_ROUTES
        if timed:
            state = scope.setdefault("state", {})
            state["performance_started"] = started
            state["performance_request_id"] = uuid4().hex[:12]

        async def secure_send(message: Message):
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                if timed:
                    seconds = time.perf_counter() - started
                    request_id = scope["state"]["performance_request_id"]
                    headers["Server-Timing"] = f"app;dur={seconds * 1000:.1f}"
                    headers["X-Request-ID"] = request_id
                    # The path is from a fixed set; queries, identities and text are excluded.
                    timing_logger.info("request_timing request=%s route=%s status=%d seconds=%.3f",
                                       request_id, scope["path"], message["status"], seconds)
                headers["Cache-Control"] = (
                    "public, max-age=31536000, immutable"
                    if scope.get("state", {}).get("immutable_frontend_asset") else "no-store"
                )
                headers["X-Content-Type-Options"] = "nosniff"
                headers["X-Frame-Options"] = "DENY"
                # Firebase browser-key restrictions need the public page's origin,
                # while private API responses must not disclose their URL paths.
                public_document = (
                    scope.get("path") in {"/", "/index.html"}
                    and message["status"] == 200
                    and headers.get("Content-Type", "").split(";", 1)[0].strip().lower() == "text/html"
                )
                headers["Referrer-Policy"] = "strict-origin" if public_document else "no-referrer"
                if scope.get("scheme") == "https":
                    headers["Strict-Transport-Security"] = "max-age=31536000"
            await send(message)

        async def reject(status: int, detail: str):
            await JSONResponse({"detail": detail}, status_code=status)(scope, receive, secure_send)

        headers = Headers(scope=scope)
        content_type = headers.get("content-type", "").split(";")[0].strip().lower()
        limit = MAX_JSON_BYTES if content_type == "application/json" else MAX_BODY_BYTES
        lengths = headers.getlist("content-length")
        if lengths:
            if (len(lengths) != 1 or len(lengths[0]) > 20
                    or not lengths[0].isascii() or not lengths[0].isdigit()):
                await reject(400, "Invalid Content-Length.")
                return
            if int(lengths[0]) > limit:
                await reject(413, "Request body is too large.")
                return

        # Count actual bytes as well: chunked bodies and incorrect length headers
        # must not bypass the limit. The timeout covers uploads, not generation.
        body = bytearray()
        try:
            with fail_after(BODY_TIMEOUT_SECONDS):
                while True:
                    message = await receive()
                    if message["type"] == "http.disconnect":
                        return
                    chunk = message.get("body", b"")
                    if len(body) + len(chunk) > limit:
                        await reject(413, "Request body is too large.")
                        return
                    body.extend(chunk)
                    if not message.get("more_body", False):
                        break
        except TimeoutError:
            await reject(408, "Request upload timed out.")
            return

        delivered = False

        async def bounded_receive():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        await self.app(scope, bounded_receive, secure_send)
