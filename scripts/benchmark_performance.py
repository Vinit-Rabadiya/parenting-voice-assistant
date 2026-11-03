"""Offline request-path benchmark. Never initializes Firebase or calls a provider.

Run with: python -m scripts.benchmark_performance --output artifacts/performance/baseline.json
The injected IO delay is a controlled experiment, not a production latency estimate.
"""

import argparse
from collections import Counter
from datetime import datetime, timezone
import gzip
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import platform
import re
import socket
import statistics
from threading import Thread
import time
import tracemalloc
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from google.auth.credentials import AnonymousCredentials
from google.auth.transport.requests import AuthorizedSession

from backend.api.dependencies import (
    get_caregiver_data_service, get_coaching_service, get_retrieval_service,
    get_usage_control_service,
)
from backend.api.v1.router import api_router
from backend.core.http_security import configure_http_security
from backend.core.frontend import mount_frontend
from backend.core.privacy import CONSENT_VERSION
from backend.core.security import get_account_security_service
from backend.services.coaching import CoachingResult
from backend.services.account_security import AccountSecurityService
from backend.services.feedback_summary import FeedbackSummaryService
from backend.services.usage import UsageDecision


class BenchmarkData:
    def __init__(self, delay):
        self.delay = delay
        self.calls = Counter()
        self.conversations = {}

    def io(self, stage):
        self.calls[stage] += 1
        time.sleep(self.delay)

    def list_children(self, uid):
        self.io("profiles")
        return [{"id": "benchmark-child", "name": "Example", "date_of_birth": "2026-05-03",
                 "age_months": 6, "completed_months": 6, "age_days": 184,
                 "age_label": "6 months", "in_scope": True, "baseline_milestones": []}]

    def get_child(self, uid, child_id):
        return self.list_children(uid)[0]

    def get_consent(self, uid):
        self.io("consent")
        return {"consent_version": CONSENT_VERSION, "consent_at": datetime.now(timezone.utc),
                "caregiver_authority": True}

    def create_conversation(self, uid, child_id, *, conversation_id=None):
        self.get_child(uid, child_id)
        self.io("conversation_create")
        now = datetime.now(timezone.utc)
        item = {"id": conversation_id or str(uuid4()), "child_id": child_id,
                "title": "New conversation", "created_at": now, "updated_at": now,
                "messages": []}
        self.conversations[item["id"]] = item
        return item

    def get_conversation(self, uid, conversation_id, *args, **kwargs):
        # Firestore reads the parent, then the bounded messages query.
        self.io("conversation_parent")
        self.io("conversation_messages")
        return self.conversations.get(conversation_id)

    def save_conversation_turn(self, uid, conversation_id, *args):
        self.io("transaction_save")
        return str(uuid4())


def summary(samples):
    ordered = sorted(samples)
    def percentile(fraction):
        return round(ordered[min(len(ordered) - 1, int((len(ordered) - 1) * fraction))], 3)
    return {"samples": len(samples), "mean_ms": round(statistics.mean(samples), 3),
            "p50_ms": round(statistics.median(samples), 3),
            "p95_ms": percentile(.95), "p99_ms": percentile(.99)}


def benchmark_security_transport(samples):
    """Actual loopback TCP connections, with anonymous credentials and no TLS."""
    connections = []

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def setup(self):
            super().setup()
            self.connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            connections.append(1)

        def do_POST(self):
            self.rfile.read(int(self.headers["Content-Length"]))
            body = b'{"users":[{"localId":"benchmark-user","emailVerified":true}]}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            self.wfile.flush()

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}/lookup"

    class LoopbackSession(AuthorizedSession):
        def post(self, ignored_provider_url, **kwargs):
            return super().post(url, **kwargs)

    app = SimpleNamespace(project_id="benchmark", credential=SimpleNamespace(
        get_credential=lambda: AnonymousCredentials()))
    results = {}
    try:
        with patch("backend.services.account_security.AuthorizedSession", LoopbackSession):
            for name, idle in (("legacy_per_call_session", 0), ("pooled_session", 8)):
                service = AccountSecurityService(app, max_idle_sessions=idle)
                connections.clear()
                timings = []
                try:
                    for _ in range(samples):
                        started = time.perf_counter()
                        service.read("benchmark-user")
                        timings.append((time.perf_counter() - started) * 1000)
                    results[name] = {**summary(timings), "tcp_connections": len(connections),
                                     "provider_lookups": samples}
                finally:
                    service.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    return {"environment": "loopback HTTP; no TLS, live identity or provider", "scenarios": results}


def benchmark_feedback(samples, delay):
    """100 synthetic accounts, controlled RPC delay, real aggregate/privacy logic."""
    calls = Counter()
    accepted_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    feedback_at = datetime(2026, 1, 2, tzinfo=timezone.utc)
    consent = {"consent_version": CONSENT_VERSION, "consent_at": accepted_at,
               "caregiver_authority": True}

    def io(stage):
        calls[stage] += 1
        time.sleep(delay)

    def account(uid):
        reference = SimpleNamespace(path=f"users/{uid}")
        snapshot = SimpleNamespace(reference=reference, exists=True, to_dict=lambda: consent)
        def get(**kwargs):
            io("consent_get_rpc")
            return snapshot
        reference.get, reference.snapshot = get, snapshot
        return reference

    def get_all(references, **kwargs):
        io("consent_batch_rpc")
        return (reference.snapshot for reference in reversed(references))

    rows = [SimpleNamespace(reference=SimpleNamespace(path=f"users/account{i}/conversations/chat/messages/answer"),
            to_dict=lambda: {"role": "assistant", "feedback": {"rating": 4, "recorded_at": feedback_at}})
            for i in range(100)]

    def collection_group(group):
        query = SimpleNamespace()
        query.select = lambda fields: query
        query.limit = lambda count: query
        def stream(**kwargs):
            io("scan_rpc")
            return iter(rows if group == "messages" else [])
        query.stream = stream
        return query

    client = SimpleNamespace(collection_group=collection_group,
                             collection=lambda name: SimpleNamespace(document=account), get_all=get_all)
    timings = []
    for _ in range(samples):
        started = time.perf_counter()
        assert FeedbackSummaryService(client).read().ratings[3].count == 100
        timings.append((time.perf_counter() - started) * 1000)
    return {"environment": {"accounts": 100, "injected_rpc_delay_ms": delay * 1000,
                            "network": "synthetic storage; no live database"},
            **summary(timings), "calls_per_sample": {key: count / samples for key, count in calls.items()}}


def benchmark_static_transfer():
    directory = Path("frontend/dist")
    if not (directory / "index.html").is_file():
        return {"available": False, "reason": "Build the frontend first."}
    app = FastAPI()
    configure_http_security(app, production=False, allowed_hosts=[])
    mount_frontend(app, api_router, directory)
    initial = re.findall(r'(?:src|href)="(/assets/[^" ]+)"', (directory / "index.html").read_text())
    assets = []
    with TestClient(app) as client:
        for file in sorted((directory / "assets").glob("*")):
            if file.suffix not in {".js", ".css"}:
                continue
            path = "/assets/" + file.name
            with client.stream("GET", path, headers={"Accept-Encoding": "gzip"}) as response:
                wire_bytes = sum(len(chunk) for chunk in response.iter_raw())
                assets.append({"path": path, "initial": path in initial, "identity_bytes": file.stat().st_size,
                               "gzip_wire_bytes": wire_bytes, "cache_control": response.headers["Cache-Control"],
                               "content_encoding": response.headers.get("Content-Encoding")})
        return {"available": True, "assets": assets, "html_cache_control": client.get("/").headers["Cache-Control"],
                "worklet_cache_control": client.get("/audio/capture.worklet.js").headers["Cache-Control"]}


def run(samples, delay):
    data = BenchmarkData(delay)
    app = FastAPI()
    app.state.firebase = object()
    configure_http_security(app, production=False, allowed_hosts=[])
    app.include_router(api_router)

    def verify(*args, **kwargs):
        assert kwargs["check_revoked"] is True
        data.io("token_revocation")
        return {"uid": "benchmark-user", "email_verified": True, "firebase": {}}

    def security(uid):
        data.io("account_security")
        return {"mfa_enabled": False, "mfa_required": False}

    def consume(*args):
        data.io("quota")
        return UsageDecision(True)

    def generate(*args, **kwargs):
        data.io("generation")
        return CoachingResult("Talk gently to your baby.", [], answer_basis="general_information")

    app.dependency_overrides.update({
        get_caregiver_data_service: lambda: data,
        get_account_security_service: lambda: SimpleNamespace(read=security),
        get_usage_control_service: lambda: SimpleNamespace(consume=consume),
        get_coaching_service: lambda: SimpleNamespace(generate=generate),
        get_retrieval_service: lambda: SimpleNamespace(retrieve=lambda *a, **kw: []),
    })
    results = {}
    with patch("backend.core.security.auth.verify_id_token", side_effect=verify), TestClient(app) as client:
        def request(method, path, **kwargs):
            data.calls["http_requests"] += 1
            response = client.request(method, path, headers={"Authorization": "Bearer benchmark"}, **kwargs)
            if not response.is_success:
                raise RuntimeError(f"Benchmark fixture failed: {path} ({response.status_code})")
            return response.json()

        def startup_legacy():
            request("GET", "/me")
            request("GET", "/privacy/consent")
            request("GET", "/children")

        def startup_combined():
            request("GET", "/me/startup")

        def first_turn(combined):
            cid = str(uuid4()) if combined else request("POST", "/conversations", json={"child_id": "benchmark-child"})["id"]
            request("POST", "/coach", json={"child_id": "benchmark-child", "conversation_id": cid,
                    "start_conversation": combined, "question": "How can I talk with my baby?"})

        for name, action in (("startup_legacy", startup_legacy), ("startup_combined", startup_combined),
                             ("first_turn_legacy", lambda: first_turn(False)),
                             ("first_turn_combined", lambda: first_turn(True))):
            action()  # exclude imports, thread startup and first route initialization
            data.calls.clear()
            timings = []
            cpu_started = time.process_time()
            for _ in range(samples):
                started = time.perf_counter()
                action()
                timings.append((time.perf_counter() - started) * 1000)
                data.conversations.clear()
            cpu_ms = (time.process_time() - cpu_started) * 1000 / samples
            results[name] = {**summary(timings), "cpu_ms_per_sample": round(cpu_ms, 3), "calls_per_sample": {
                key: count / samples for key, count in sorted(data.calls.items())}}
            # Separate allocation sample: tracing overhead cannot distort timings.
            tracemalloc.start()
            try:
                action()
                results[name]["python_peak_allocated_bytes_one_sample"] = tracemalloc.get_traced_memory()[1]
            finally:
                tracemalloc.stop()
                data.conversations.clear()
    assets = []
    for file in sorted(Path("frontend/dist/assets").glob("*")):
        if file.suffix in {".js", ".css"}:
            content = file.read_bytes()
            assets.append({"name": file.name, "bytes": len(content), "gzip_bytes": len(gzip.compress(content, mtime=0))})
    return {"environment": {"python": platform.python_version(), "platform": platform.system(),
            "injected_io_delay_ms": delay * 1000, "network": "in-process TestClient; no live services",
            "percentiles": "P50 median; P95/P99 lower empirical order statistic"},
            "scenarios": results, "built_assets": assets,
            "security_transport": benchmark_security_transport(samples),
            "static_host": benchmark_static_transfer()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=100)
    parser.add_argument("--io-delay-ms", type=float, default=5)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--feedback-only", action="store_true")
    args = parser.parse_args()
    if args.samples < 2 or args.io_delay_ms < 0:
        parser.error("Use at least two samples and a non-negative IO delay.")
    result = (benchmark_feedback(args.samples, args.io_delay_ms / 1000) if args.feedback_only
              else run(args.samples, args.io_delay_ms / 1000))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
