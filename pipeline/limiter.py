"""Global request limiter — invariant 5, hard: starts ≤1 per 3 s across ALL hosts.

Phase 2 archiving may overlap long server-side capture waits (scope-lock
Amendment A): starts stay rate-gated while up to `max_in_flight` requests run
concurrently. Clock and sleep are injectable so tests need no network, no time.
"""

import threading
from contextlib import contextmanager
from time import monotonic, sleep as _sleep

MIN_INTERVAL_S = 3.0
MAX_IN_FLIGHT_ARCHIVE = 4


class GlobalLimiter:
    def __init__(self, min_interval=MIN_INTERVAL_S, max_in_flight=1,
                 clock=monotonic, sleep=_sleep):
        self._min_interval = float(min_interval)
        self._clock = clock
        self._sleep = sleep
        self._lock = threading.Lock()
        self._inflight = threading.Semaphore(max_in_flight)
        self._last_start = None

    def _rate_gate(self):
        with self._lock:
            while True:
                if self._last_start is None:
                    break
                remaining = self._min_interval - (self._clock() - self._last_start)
                if remaining <= 0:
                    break
                self._sleep(remaining)
            self._last_start = self._clock()

    @contextmanager
    def request(self):
        """Context manager bounding one HTTP request's full lifetime."""
        self._rate_gate()
        self._inflight.acquire()
        try:
            yield self
        finally:
            self._inflight.release()
