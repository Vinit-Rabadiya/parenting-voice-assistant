"""Bound concurrent processing and short bursts without daily usage quotas."""

from collections import OrderedDict
from contextlib import contextmanager
import hmac
from secrets import token_bytes
from threading import Lock
import time


class AdmissionRejected(RuntimeError):
    pass


class RequestAdmission:
    def __init__(self, *, enforce_rate=True, max_active=4, max_per_user=2,
                 burst=8, refill_seconds=3, capacity=1024, clock=time.monotonic):
        self.enforce_rate = enforce_rate
        self.max_active, self.max_per_user = max_active, max_per_user
        self.burst, self.refill_seconds, self.capacity = burst, refill_seconds, capacity
        self.clock = clock
        self._secret = token_bytes(32)
        self._buckets = OrderedDict()
        self._active = {}
        self._workers = {}
        self._speech_active = 0
        self._lock = Lock()
        self._closed = False

    def _key(self, uid):
        return hmac.digest(self._secret, uid.encode(), "sha256")

    def _consume(self, key, category):
        if not self.enforce_rate:
            return
        now = self.clock()
        burst, refill_seconds = (32, 1) if category == "reads" else (self.burst, self.refill_seconds)
        bucket_key = (key, category)
        tokens, recorded = self._buckets.get(bucket_key, (burst, now))
        tokens = min(burst, tokens + max(0, now - recorded) / refill_seconds)
        if tokens < 1:
            raise AdmissionRejected("Please wait a few seconds before trying again.")
        self._buckets[bucket_key] = (tokens - 1, now)
        self._buckets.move_to_end(bucket_key)
        while len(self._buckets) > self.capacity:
            self._buckets.popitem(last=False)

    def check_write(self, uid):
        self._check(uid, "writes")

    def check_read(self, uid):
        self._check(uid, "reads")

    def _check(self, uid, category):
        with self._lock:
            if self._closed:
                raise AdmissionRejected("The service is restarting. Please try again shortly.")
            self._consume(self._key(uid), category)

    @contextmanager
    def processing(self, uid):
        key = self._key(uid)
        with self._lock:
            if (self._closed or sum(self._active.values()) >= self.max_active
                    or self._active.get(key, 0) >= self.max_per_user
                    or sum(self._workers.values()) >= self.max_active
                    or self._workers.get(key, 0) >= self.max_per_user):
                raise AdmissionRejected("The service is busy. Please try again shortly.")
            self._consume(key, "processing")
            self._active[key] = self._active.get(key, 0) + 1
        try:
            yield
        finally:
            with self._lock:
                count = self._active.get(key, 0) - 1
                if count > 0:
                    self._active[key] = count
                else:
                    self._active.pop(key, None)

    @contextmanager
    def worker(self, uid, *, speech=False):
        # A disconnected HTTP request cannot cancel a blocking provider/model
        # call. Keep its actual capacity reserved until the worker exits.
        key = self._key(uid)
        with self._lock:
            if (self._closed or sum(self._workers.values()) >= self.max_active
                    or self._workers.get(key, 0) >= self.max_per_user
                    or speech and self._speech_active >= 1):
                raise AdmissionRejected("The service is busy. Please try again shortly.")
            self._workers[key] = self._workers.get(key, 0) + 1
            self._speech_active += int(speech)
        try:
            yield
        finally:
            with self._lock:
                count = self._workers.get(key, 0) - 1
                if count > 0:
                    self._workers[key] = count
                else:
                    self._workers.pop(key, None)
                self._speech_active -= int(speech)

    def close(self):
        with self._lock:
            self._closed = True
            self._buckets.clear()
