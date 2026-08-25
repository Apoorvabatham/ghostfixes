"""Phase 1 sweep driver: selection -> fetch -> hash -> journal.

Resume reads disk only: the journal carries ticket-level state (including
the image-URL list captured at api_kept, so a restart needs no re-fetch to
know what to scrape), and HashLog replays its own records so per-image work
is exact-once across restarts. Failed images are retried on the next run —
they are never hashed, so nothing partial is trusted.

Fail loudly per scope-lock §9.6: detail-endpoint failures (auth wall,
5xx) and transport errors trip SurfaceGuard, which halts the run with
SurfaceDegraded instead of logging stale silence; an access restriction is
recorded as what it is, never routed around. Image-object non-200s are
per-object facts (§10: recorded, no retry storm), not degradation signals.
"""

import httpx

from .hashing import record_for
from .journal import FAILED

TERMINAL_PHASE1 = ("scrape_done", "api_dropped")


class SurfaceDegraded(RuntimeError):
    pass


class SurfaceGuard:
    """Halts after `limit` consecutive surface-level failures."""

    def __init__(self, limit=5):
        self.limit = limit
        self.streak = 0

    def record_success(self):
        self.streak = 0

    def record_failure(self, context):
        self.streak += 1
        if self.streak >= self.limit:
            raise SurfaceDegraded(
                f"{self.streak} consecutive surface failures "
                f"(last: {context}) — degraded; halting per scope-lock §9.6")


class SweepRunner:
    def __init__(self, adapter, client, journal, hashlog, manifest,
                 guard=None):
        self.adapter = adapter
        self.client = client
        self.journal = journal
        self.hashlog = hashlog
        self.manifest = manifest
        self.guard = guard or SurfaceGuard()
        # Exact-once image work across restarts.
        self._hashed = hashlog.existing_pairs()
        self._csv_dates = {rec["ticket_id"]: rec.get("csv_date_raw")
                           for rec in manifest}
        self.image_totals = {"images_hashed": 0, "images_failed_object": 0}

    def run(self, limit=None):
        stats = {
            "candidates": 0, "api_kept": 0, "api_dropped": 0,
            "scrape_done": 0, "failed": 0,
            "images_hashed": 0, "images_failed_object": 0,
            "already_done": 0,
        }
        for rec in self.manifest:
            if limit is not None and stats["candidates"] >= limit:
                break
            tid = rec["ticket_id"]
            state = self.journal.state_of(tid)
            if state in TERMINAL_PHASE1:
                stats["already_done"] += 1
                continue
            stats["candidates"] += 1
            try:
                outcome = self._process(tid)
            except SurfaceDegraded:
                raise
            except (httpx.HTTPError, ValueError, KeyError) as exc:
                self.journal.append(tid, FAILED, stage="exception",
                                    error=type(exc).__name__)
                self.guard.record_failure(f"{tid}: {type(exc).__name__}")
                stats["failed"] += 1
                continue
            stats[outcome] = stats.get(outcome, 0) + 1
        stats.update(self.image_totals)
        return stats

    def _process(self, tid):
        state = self.journal.state_of(tid)
        if state is None or state == FAILED:
            self.journal.append(tid, "candidate")
            state = "candidate"
        if state == "candidate":
            return self._detail_stage(tid)
        if state == "api_kept":
            self._scrape_stage(tid)
            return "scrape_done"
        raise ValueError(f"unexpected journal state {state!r} for {tid}")

    def _detail_stage(self, tid):
        resp = self.client.fetch_detail(self.adapter, tid)
        if resp.status_code != 200:
            # An access restriction or outage on the metadata surface IS a
            # degraded surface (§9.6): count it, never route around it.
            # Record the restriction first, THEN let the guard decide
            # whether it halts: a halt must not lose the last failure.
            self.journal.append(tid, FAILED, stage="detail",
                                http_status=resp.status_code)
            self.guard.record_failure(f"detail {tid} HTTP {resp.status_code}")
            return "failed"
        self.guard.record_success()
        detail = self.adapter.parse_detail(resp.json())
        member, parsed = self.adapter.selection.is_stage_b_member(
            detail.filed_at_raw)
        if not member:
            self.journal.append(tid, "api_dropped",
                                api_date_raw=detail.filed_at_raw)
            return "api_dropped"
        self.journal.append(
            tid, "api_kept", api_date=parsed,
            csv_date_raw=self._csv_date(tid),
            ward=detail.ward, category=detail.category,
            sub_category=detail.sub_category,
            citizen_status=detail.citizen_status,
            staff_status=detail.staff_status,
            image_urls=list(detail.image_urls))
        self._scrape_stage(tid)
        return "scrape_done"

    def _csv_date(self, tid):
        return self._csv_dates.get(str(tid))

    def _scrape_stage(self, tid):
        rec = self.journal.state_map()[str(tid)]
        urls = rec.get("image_urls") or []
        failed_objects = 0
        for url in urls:
            if (str(tid), url) in self._hashed:
                continue
            resp = self.client.fetch_image(self.adapter, url)
            # Per-object non-200s are recorded facts (§10), not surface
            # degradation: no guard involvement, no retry storm.
            if resp is None or resp.status_code != 200:
                failed_objects += 1
                continue
            content = resp.content
            if not content:
                failed_objects += 1
                continue
            # A 200 whose bytes will not decode or hash is an object-level
            # fact like a 403 (§10): counted, never trusted, not a halt.
            try:
                record = record_for(tid, url, content)
            except (OSError, ValueError):
                failed_objects += 1
                continue
            self.hashlog.append(record)
            self._hashed.add((str(tid), url))
        hashed = sum(1 for u in urls if (str(tid), u) in self._hashed)
        self.image_totals["images_hashed"] += hashed
        self.image_totals["images_failed_object"] += failed_objects
        self.journal.append(tid, "scrape_done", images_hashed=hashed,
                            images_failed_object=failed_objects)
