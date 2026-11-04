"""Bound incoming bodies and prevent caching of private API responses."""

from anyio import fail_after
from contextlib import contextmanager
from contextvars import ContextVar
import logging
import json
from math import isfinite
from pathlib import Path
from threading import Lock
import time
from uuid import uuid4
from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import JSONResponse
from starlette.middleware.httpsredirect import HTTPSRedirectMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.types import ASGIApp, Message, Receive, Scope, Send
from starlette.concurrency import run_in_threadpool


MAX_JSON_BYTES = 64 * 1024
MAX_BODY_BYTES = 1024 * 1024
BODY_TIMEOUT_SECONDS = 15
timing_logger = logging.getLogger("uvicorn.error.request_timing")
TIMED_ROUTES = {prefix + path for prefix in ("", "/api", "/api/v1")
                for path in ("/me", "/me/startup", "/children", "/conversations", "/coach", "/speech/transcribe")}
COACH_ROUTES = {prefix + "/coach" for prefix in ("", "/api", "/api/v1")}
TIMING_STAGES = (
    "token_verification", "account_security", "consent", "coaching_documents", "caregiver_safety",
    "profile_lookup", "conversation_context", "input_safety", "context_safety",
    "conversation_start", "retrieval", "evidence_selection",
    "generation", "generation_first_token", "first_answer", "response_safety", "interaction_save",
)
_request_timings = ContextVar("request_stage_timings", default=None)


class RequestStageTimings:
    """Bounded fixed-name metrics shared only with this request's worker tasks."""

    def __init__(self):
        self._seconds = {}
        self._lock = Lock()

    def record(self, stage: str, seconds: float, *, first=False) -> None:
        if stage not in TIMING_STAGES or not isfinite(seconds) or seconds < 0:
            return
        with self._lock:
            if not first or stage not in self._seconds:
                self._seconds[stage] = self._seconds.get(stage, 0) + seconds

    def header(self) -> str:
        with self._lock:
            return ", ".join(f"{stage};dur={self._seconds[stage] * 1000:.1f}"
                             for stage in TIMING_STAGES if stage in self._seconds)

    def snapshot(self) -> dict[str, float]:
        with self._lock:
            return {stage: round(seconds * 1000, 1) for stage, seconds in self._seconds.items()}


def record_request_stage(stage: str, seconds: float, *, first=False) -> None:
    timings = _request_timings.get()
    if timings is not None:
        timings.record(stage, seconds, first=first)


def request_timing_snapshot() -> dict[str, float]:
    timings = _request_timings.get()
    return timings.snapshot() if timings is not None else {}


@contextmanager
def timed_request_stage(request, stage: str):
    started = time.perf_counter()
    try:
        yield
    finally:
        seconds = time.perf_counter() - started
        record_request_stage(stage, seconds)
        request_id = getattr(request.state, "performance_request_id", None)
        if request_id:
            timing_logger.info("request_stage request=%s stage=%s seconds=%.3f",
                               request_id, stage, seconds)


def configure_http_security(app, *, production: bool, allowed_hosts: list[str],
                            development_timing_directory: Path | None = None) -> None:
    if production:
        app.add_middleware(HTTPSRedirectMiddleware)
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)
    # Apply response protections to host rejections and redirects too.
    app.add_middleware(HTTPSecurityMiddleware,
                       timing_directory=None if production else development_timing_directory)


class HTTPSecurityMiddleware:
    def __init__(self, app: ASGIApp, *, timing_directory: Path | None = None):
        self.app = app
        self._timing_directory = timing_directory

    def _capture_next(self, record: dict, server_port: int | None) -> None:
        # Explicit, development-only one-shot capture. Atomic flag removal lets
        # only one completed request claim it; replace a single bounded record.
        flag = self._timing_directory / "capture-next-coach-timing"
        try:
            target = json.loads(flag.read_text(encoding="utf-8-sig"))
            # A synthetic TestClient or a workflow server on another port must
            # not consume the capture armed for the user's running backend.
            if (type(target.get("server_port")) is not int
                    or target["server_port"] != server_port):
                return
            flag.unlink()
        except FileNotFoundError:
            return
        output = self._timing_directory / "local-coach-timing.json"
        temporary = output.with_suffix(".tmp")
        temporary.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        temporary.replace(output)

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        started = time.perf_counter()
        # Mounts may copy the ASGI scope; share the state mapping with the static
        # host so only its validated public assets can opt into caching.
        scope.setdefault("state", {})
        timed = scope.get("path") in TIMED_ROUTES
        timings = RequestStageTimings() if timed else None
        capture_record = None
        streaming_response = False
        if timed:
            state = scope.setdefault("state", {})
            state["performance_started"] = started
            state["performance_request_id"] = uuid4().hex[:12]

        async def secure_send(message: Message):
            nonlocal capture_record, streaming_response
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                streaming_response = headers.get("Content-Type", "").split(";", 1)[0].lower() == "text/event-stream"
                if timed:
                    seconds = time.perf_counter() - started
                    request_id = scope["state"]["performance_request_id"]
                    headers["Server-Timing"] = f"app;dur={seconds * 1000:.1f}"
                    stages = timings.header()
                    if stages:
                        headers["Server-Timing"] += ", " + stages
                    headers["X-Request-ID"] = request_id
                    # The path is from a fixed set; queries, identities and text are excluded.
                    timing_logger.info("request_timing request=%s route=%s status=%d seconds=%.3f",
                                       request_id, scope["path"], message["status"], seconds)
                    if scope["path"] in COACH_ROUTES and self._timing_directory is not None:
                        capture_record = {"request_id": request_id, "route": scope["path"],
                                          "status": message["status"], "total_ms": round(seconds * 1000, 1),
                                          "stages_ms": timings.snapshot()}
                headers["Cache-Control"] = (
                    "public, max-age=31536000, immutable"
                    if scope.get("state", {}).get("immutable_frontend_asset") else "no-store"
                )
                headers["X-Content-Type-Options"] = "nosniff"
                headers["X-Frame-Options"] = "DENY"
                # Firebase browser-key restrictions need the public page's origin,
                # while private API responses must not disclose their URL paths.
                public_document = (
                    (scope.get("path") in {"/", "/index.html"}
                     or scope.get("state", {}).get("public_frontend_document"))
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

        # AnyIO propagates this context to worker threads. Each HTTP request has
        # its own collector; cancellation/errors cannot leave it on a later one.
        token = _request_timings.set(timings)
        try:
            await self.app(scope, bounded_receive, secure_send)
        finally:
            _request_timings.reset(token)
        if capture_record is not None:
            # Headers measure TTFB for SSE. Finalize the metadata only after
            # the response body has finished, including generation and saving.
            capture_record["total_ms"] = round((time.perf_counter() - started) * 1000, 1)
            capture_record["stages_ms"] = timings.snapshot()
            if streaming_response:
                outcome = scope["state"].get("coaching_stream_outcome")
                capture_record["stream_outcome"] = outcome if outcome in {"completed", "failed", "cancelled"} else "unknown"
            try:
                if (self._timing_directory / "capture-next-coach-timing").is_file():
                    # The response has been sent; filesystem IO stays off the
                    # event loop and outside the measured response interval.
                    server = scope.get("server")
                    await run_in_threadpool(self._capture_next, capture_record, server[1] if server else None)
            except Exception as exc:
                timing_logger.warning("timing_capture_failed error_type=%s", type(exc).__name__)
