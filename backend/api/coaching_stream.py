"""Bounded SSE transport for a single authenticated coaching operation."""
import asyncio
from concurrent.futures import TimeoutError as FutureTimeout
import json
from threading import Event
import time

from fastapi import HTTPException
from starlette.responses import StreamingResponse

from backend.core.http_security import record_request_stage, request_timing_snapshot


class StreamCancelled(RuntimeError):
    pass


class CoachingStream:
    def __init__(self, request):
        self.loop = asyncio.get_running_loop()
        self.queue = asyncio.Queue(maxsize=16)
        self.cancelled = Event()
        self.state = request.state
        self.state.coaching_stream_outcome = "started"
        self.started = getattr(request.state, "performance_started", time.perf_counter())
        self.first_answer = False

    def _first(self, event):
        if event in {"delta", "ready"} and not self.first_answer:
            self.first_answer = True
            record_request_stage("first_answer", time.perf_counter() - self.started)

    async def send(self, event, data):
        if self.cancelled.is_set():
            raise StreamCancelled()
        self._first(event)
        await self.queue.put((event, data))

    def send_from_worker(self, event, data):
        if self.cancelled.is_set():
            raise StreamCancelled()
        self._first(event)
        future = asyncio.run_coroutine_threadsafe(self.queue.put((event, data)), self.loop)
        while True:
            try:
                future.result(timeout=0.25)
                return
            except FutureTimeout:
                if self.cancelled.is_set():
                    future.cancel()
                    raise StreamCancelled() from None

    def response(self, operation):
        async def produce():
            try:
                response = await operation(self)
                self.state.coaching_stream_outcome = "completed"
                await self.send("done", {"response": response.model_dump(mode="json"),
                                         "timings_ms": request_timing_snapshot()})
            except HTTPException as exc:
                self.state.coaching_stream_outcome = "failed"
                await self.send("error", {"status": exc.status_code, "detail": exc.detail})
            except StreamCancelled:
                return
            except Exception:
                self.state.coaching_stream_outcome = "failed"
                await self.send("error", {"status": 502, "detail": "Something went wrong. Please try again."})

        async def events():
            task = asyncio.create_task(produce())
            try:
                yield 'event: status\ndata: {"phase":"preparing"}\n\n'
                while True:
                    try:
                        event, data = await asyncio.wait_for(self.queue.get(), timeout=10)
                    except TimeoutError:
                        yield ": keep-alive\n\n"
                        continue
                    yield f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, allow_nan=False)}\n\n"
                    if event in {"done", "error"}:
                        break
            finally:
                self.cancelled.set()
                if self.state.coaching_stream_outcome == "started":
                    self.state.coaching_stream_outcome = "cancelled"
                if not task.done():
                    task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, StreamCancelled):
                    pass

        return StreamingResponse(events(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})
