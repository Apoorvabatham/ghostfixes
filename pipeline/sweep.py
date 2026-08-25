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

A 200 with an unusable payload is invisible to SurfaceGuard — the F1
near-miss (2026-08-25): a flat read of a nested payload made every ticket
look dateless and Stage B dropped the lot with all checks green. The
batch-health guard closes that hole: over each contiguous batch of Stage-B
decisions it watches two structural signals (unparseable filing dates;
keep-rate among non-pad candidates) and halts with MassDropDegraded when
either says the reads broke, rather than letting a parse failure masquerade
as data.
"""

import httpx

from .hashing import record_for
from .journal import FAILED

TERMINAL_PHASE1 = ("scrape_done", "api_dropped")


class SurfaceDegraded(RuntimeError):
    pass


class MassDropDegraded(RuntimeError):
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


class BatchHealthGuard:
    """Stage-B mass-drop guard: halts when a contiguous batch of decisions
    is structurally wrong rather than substantively informative.

    Two independent signals over each completed batch; either alone halts:

    - Unparseable filing timestamps. A payload-shape change presents as
      ~100% unparseable (the F1 near-miss measured exactly that); genuinely
      dateless tickets are rare portal junk, measured baseline 0/32 on the
      live endpoint. Halt when unparseable/decided >= UNPARSEABLE_MAX_FRAC.
      Pad-day drops count toward this signal too — deliberately: global
      read breakage must fire even inside an all-pad segment. Their usual
      silence here is an empirical fact (pad-day API dates parse), not a
      declared exclusion.
    - Keep-rate among decided candidates whose CSV date is NOT a declared
      pad day. Legitimate in-window drops are bounded by the publisher's
      ±12 h export artifact crossing a window edge (~1% of records); whole
      -corpus membership inversion presents near 0%. Halt when
      kept_non_pad/non_pad < KEEP_FLOOR_MIN_FRAC. Pad-day candidates are
      excluded from this denominator by adapter declaration
      (`selection.csv_date_is_pad`), so an all-pad batch — like the first
      142 IDs of this corpus — cannot fire it.

    When either signal halts, the raised MassDropDegraded carries
    `suspect_ticket_ids`: every ticket dropped since the last clean batch.
    Those drops happened under reads now known to be suspect, so the runner
    requeues them (journal FAILED — retryable) before propagating; resume
    re-decides them instead of shipping a silently shrunken corpus.

    Counters cover decisions made within one run only; a resumed run starts
    a new contiguous series. A batch evaluates when it reaches batch_size;
    a partial trailing batch evaluates only on natural exhaustion of the
    manifest, never on a crash or a `limit` stop — matching real crash
    semantics, where the counters die with the process.
    """

    BATCH_SIZE = 100
    UNPARSEABLE_MAX_FRAC = 0.20
    KEEP_FLOOR_MIN_FRAC = 0.70

    def __init__(self, selection, batch_size=BATCH_SIZE):
        self.selection = selection
        self.batch_size = batch_size
        self._reset()

    def _reset(self):
        self.decided = 0
        self.unparseable = 0
        self.non_pad = 0
        self.kept_non_pad = 0
        self.drop_ids = []

    def _is_pad(self, csv_date_raw):
        return self.selection.csv_date_is_pad(csv_date_raw)

    def record_keep(self, csv_date_raw):
        self.decided += 1
        if not self._is_pad(csv_date_raw):
            self.non_pad += 1
            self.kept_non_pad += 1

    def record_drop(self, ticket_id, csv_date_raw, parsed):
        """`parsed` is None exactly when the API filing timestamp was absent
        or unparseable — the structural signature."""
        self.decided += 1
        self.drop_ids.append(str(ticket_id))
        if parsed is None:
            self.unparseable += 1
        elif not self._is_pad(csv_date_raw):
            self.non_pad += 1

    def evaluate_batch(self):
        if self.decided >= self.batch_size:
            self._raise_if_unhealthy()

    def finalize(self):
        if self.decided > 0:
            self._raise_if_unhealthy()

    def _raise_if_unhealthy(self):
        unparseable_frac = self.unparseable / self.decided
        suspects = list(self.drop_ids)
        if unparseable_frac >= self.UNPARSEABLE_MAX_FRAC:
            exc = MassDropDegraded(
                f"batch health: {self.unparseable}/{self.decided} Stage-B "
                "decisions had no parseable API filing timestamp "
                f"({unparseable_frac:.0%} >= "
                f"{self.UNPARSEABLE_MAX_FRAC:.0%}) — reads are broken, not "
                "the data; halting")
            exc.suspect_ticket_ids = suspects
            raise exc
        if self.non_pad:
            keep_frac = self.kept_non_pad / self.non_pad
            if keep_frac < self.KEEP_FLOOR_MIN_FRAC:
                exc = MassDropDegraded(
                    f"batch health: {self.kept_non_pad}/{self.non_pad} kept "
                    f"among non-pad candidates ({keep_frac:.0%} < "
                    f"{self.KEEP_FLOOR_MIN_FRAC:.0%}) with "
                    f"{self.unparseable}/{self.decided} unparseable — mass "
                    "drop indicates structural read failure; halting")
                exc.suspect_ticket_ids = suspects
                raise exc
        self._reset()


class SweepRunner:
    def __init__(self, adapter, client, journal, hashlog, manifest,
                 guard=None, health=None):
        self.adapter = adapter
        self.client = client
        self.journal = journal
        self.hashlog = hashlog
        self.manifest = manifest
        self.guard = guard or SurfaceGuard()
        self.health = health or BatchHealthGuard(adapter.selection)
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
        exhausted = True
        for rec in self.manifest:
            if limit is not None and stats["candidates"] >= limit:
                # Crash-shaped stop: no trailing-batch evaluation. Edge case
                # accepted: if `limit` exactly consumes the remaining
                # non-terminal candidates the tail batch goes unevaluated —
                # its decisions are already terminal and a later full run
                # has nothing left to sample.
                exhausted = False
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
            except MassDropDegraded as exc:
                # The batch's drops happened under reads now known to be
                # suspect. Requeue them (FAILED is reachable from any state
                # and retryable) so resume re-decides them instead of
                # shipping a silently shrunken corpus; then halt loudly.
                for suspect_id in getattr(exc, "suspect_ticket_ids", ()):
                    self.journal.append(suspect_id, FAILED,
                                        stage="mass_drop_requeue")
                raise
            except (httpx.HTTPError, ValueError, KeyError) as exc:
                self.journal.append(tid, FAILED, stage="exception",
                                    error=type(exc).__name__)
                self.guard.record_failure(f"{tid}: {type(exc).__name__}")
                stats["failed"] += 1
                continue
            stats[outcome] = stats.get(outcome, 0) + 1
        if exhausted:
            # Natural end of manifest: the trailing partial batch is a real
            # sample and gets evaluated. A `limit` stop or a raised halt
            # skips this — a killed run's counters die with the process.
            self.health.finalize()
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
        csv_date = self._csv_date(tid)
        if not member:
            self.health.record_drop(tid, csv_date, parsed)
            self.journal.append(tid, "api_dropped",
                                api_date_raw=detail.filed_at_raw)
            self.health.evaluate_batch()
            return "api_dropped"
        self.health.record_keep(csv_date)
        self.journal.append(
            tid, "api_kept", api_date=parsed,
            csv_date_raw=csv_date,
            ward=detail.ward, category=detail.category,
            sub_category=detail.sub_category,
            citizen_status=detail.citizen_status,
            staff_status=detail.staff_status,
            image_urls=list(detail.image_urls))
        self.health.evaluate_batch()
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
