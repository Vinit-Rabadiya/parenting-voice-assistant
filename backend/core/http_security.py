"""Bound incoming bodies and prevent caching of private API responses."""

from anyio import fail_after
from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import JSONResponse
from starlette.middleware.httpsredirect import HTTPSRedirectMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.types import ASGIApp, Message, Receive, Scope, Send


MAX_JSON_BYTES = 64 * 1024
MAX_BODY_BYTES = 1024 * 1024
BODY_TIMEOUT_SECONDS = 15


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

        async def secure_send(message: Message):
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["Cache-Control"] = "no-store"
                headers["X-Content-Type-Options"] = "nosniff"
                headers["X-Frame-Options"] = "DENY"
                headers["Referrer-Policy"] = "no-referrer"
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
