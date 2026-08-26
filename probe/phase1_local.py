"""Bounded LOCAL Phase 1 batches — the Amendment F execution driver.

Amendment F (2026-08-26, docs/stage1-scope-lock.md): all Phase 1 sweeping
runs locally against the residential vantage — sustained access from CI
runners is measured dead (docs/stage0-report.md Addendum 3: three batches
halted on httpx.ReadTimeout streaks) — in bounded batches with a checkpoint
commit between batches. This driver is that runner; probe/phase1_dryrun.py
stays the dry-run tool and is untouched.

Differences from the dry-run driver:

  - operates directly on data/ (committed manifest/journal/hashes); the
    manifest is loaded from disk, so no CSV refetch ever happens;
  - wraps PortalClient to append one timing line per HTTP request to
    probe/out/timings.jsonl (gitignored scratch): wall-clock start UTC,
    monotonic start (ms resolution), wire seconds, kind (csv|detail|
    image), status or error class, byte count. The measured window is the
    request's lifetime INSIDE the limiter gate — limiter sleep is
    excluded; start-to-start spacing computed from the monotonic stamps
    evidences the 3 s floor at millisecond accuracy (wall-clock seconds
    alone cannot: NTP steps and truncation fake violations);
  - kind is tagged at the PortalClient call site, not guessed from the
    URL: the adapter decides what a URL is (citizen photos live on hosts
    whose paths carry no /GrievanceImages/ marker);
  - one process holds the sweep at a time: an flock on
    probe/out/phase1_local.lock refuses a second invocation loudly
    instead of double-spending the rate budget against data/;
  - one of --max-requests/--limit is REQUIRED: Amendment F batches are
    bounded by design; omitting both would silently convert a bounded
    batch into an unbounded multi-day run;
  - the subset is always the full Stage A manifest; bounds come from
    --max-requests (crash-shaped budget stop, the Amendment F batch
    boundary) and --limit (same crash-shaped semantics).

Known limits, stated rather than buried:

  - redirects are NOT followed (pipeline/fetcher.py policy): a 3xx
    surfaces as a non-200 fact for its request, never chased silently;
  - run-level stats["images_hashed"] includes hashes replayed from
    earlier processes for any ticket whose scrape straddled two runs
    (per-ticket journal facts and committed hashes stay exact; only this
    convenience total can over-count after a mid-scrape kill).

Halt behaviour is pipeline-owned and unchanged: SurfaceGuard raises on 5
consecutive surface failures, BatchHealthGuard on structurally impossible
Stage-B batches; both crash this process loudly with the journal fsynced to
the last decided ticket. Resume is exact-once (SweepJournal replay +
HashLog pair replay). After every run: the dry-run driver's invariant
checks run over data/ (key universes + phone/email pattern scan).
"""

import argparse
import contextvars
import fcntl
import json
import math
import os
import sys
import time
from urllib.parse import urlsplit

from phase1_dryrun import check_outputs
from pipeline.hashing import HashLog
from pipeline.journal import SweepJournal, utc_now_iso
from pipeline.manifest import load_manifest
from pipeline.fetcher import PortalClient
from pipeline.sweep import SweepRunner

from adapters.bengaluru import ADAPTER

DATA_DIR = "data"
TIMINGS_PATH = os.path.join("probe", "out", "timings.jsonl")
LOCK_PATH = os.path.join("probe", "out", "phase1_local.lock")

IMAGE_MARKER = "/GrievanceImages/"

USER_AGENT = ("GhostFixes/0.1-phase1-local "
              "(+https://github.com/Apoorvabatham/ghostfixes; "
              "contact: apba00001@uni-saarland.de)")

# Kind tagging: set around each PortalClient call so the timing wrapper
# records what the ADAPTER says a request is, not what its URL looks like.
_expected_kind = contextvars.ContextVar("phase1_local_request_kind",
                                        default=None)


class TimedPortalClient(PortalClient):
    """PortalClient that appends one timing line per HTTP request.

    Wraps each cached httpx.Client's .get exactly once per trust level.
    Transport errors are recorded by exception class name and re-raised:
    a timed-out request must look exactly like one to SurfaceGuard.
    """

    def __init__(self, user_agent, timings_path, **kwargs):
        # kwargs pass through to PortalClient (limiter/timeout/transport)
        # so tests can inject a MockTransport and a fast-forward limiter;
        # production passes nothing and gets the real 3 s gate.
        super().__init__(user_agent, **kwargs)
        self._timings_path = timings_path
        self.timings = []
        self._wrapped = set()
        os.makedirs(os.path.dirname(os.path.abspath(timings_path)),
                    exist_ok=True)
        self._fh = open(timings_path, "a", encoding="utf-8")

    def _tagged(self, kind, fn, *args):
        """Run one PortalClient request method with its kind declared."""
        token = _expected_kind.set(kind)
        try:
            return fn(*args)
        finally:
            _expected_kind.reset(token)

    def get_bytes(self, url):
        return self._tagged("csv", super().get_bytes, url)

    def fetch_detail(self, adapter, ticket_id):
        return self._tagged("detail", super().fetch_detail, adapter,
                            ticket_id)

    def fetch_image(self, adapter, url):
        return self._tagged("image", super().fetch_image, adapter, url)

    def client_for(self, verify_tls):
        client = super().client_for(verify_tls)
        key = bool(verify_tls)
        if key not in self._wrapped:
            original_get = client.get

            def timed_get(url, **kwargs):
                started = time.monotonic()
                split = urlsplit(url)
                rec = {
                    "ts_utc": utc_now_iso(),
                    "mono_s": round(started, 4),
                    "kind": _expected_kind.get() or (
                        "image" if IMAGE_MARKER in split.path else "detail"),
                    "host": split.netloc,
                }
                try:
                    resp = original_get(url, **kwargs)
                except Exception as exc:
                    rec["error"] = type(exc).__name__
                    rec["elapsed_s"] = round(time.monotonic() - started, 3)
                    self._record(rec)
                    raise
                rec["status"] = resp.status_code
                rec["elapsed_s"] = round(time.monotonic() - started, 3)
                rec["bytes"] = len(resp.content)
                self._record(rec)
                return resp

            client.get = timed_get
            self._wrapped.add(key)
        return client

    def _record(self, rec):
        self.timings.append(rec)
        self._fh.write(json.dumps(rec, sort_keys=True) + "\n")
        self._fh.flush()

    def close(self):
        super().close()
        self._fh.close()


def percentile(values, q):
    """Nearest-rank percentile; None when empty."""
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil(q / 100 * len(ordered)))
    return ordered[min(rank - 1, len(ordered) - 1)]


def describe_latencies(records):
    times = [r.get("elapsed_s") for r in records if "elapsed_s" in r]
    return {
        "n": len(times),
        "p50_s": percentile(times, 50),
        "p95_s": percentile(times, 95),
        "max_s": percentile(times, 100),
    }


def _pending_ids(manifest, journal):
    terminal = ("scrape_done", "api_dropped")
    return [rec["ticket_id"] for rec in manifest
            if journal.state_of(rec["ticket_id"]) not in terminal]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-requests", type=int, default=None,
                        help="stop crash-shaped once this many requests "
                             "have been made (the Amendment F batch "
                             "boundary); resume continues from disk")
    parser.add_argument("--limit", type=int, default=None,
                        help="cap candidates processed this run "
                             "(crash-shaped, like --max-requests)")
    parser.add_argument("--data-dir", default=DATA_DIR)
    parser.add_argument("--timings-out", default=TIMINGS_PATH)
    parser.add_argument("--progress-every", type=int, default=25)
    args = parser.parse_args(argv)
    if args.max_requests is None and args.limit is None:
        parser.error("one of --max-requests/--limit is required: "
                     "Amendment F batches are bounded by design; an "
                     "unbounded run would silently become multi-day")

    # One process sweeps at a time (pre-probe review): two concurrent runs
    # against data/ would double-spend the rate budget on the same pending
    # prefix and interleave journal records validated against stale state.
    os.makedirs(os.path.dirname(os.path.abspath(LOCK_PATH)), exist_ok=True)
    lock_fd = os.open(LOCK_PATH, os.O_CREAT | os.O_RDWR, 0o644)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        os.close(lock_fd)
        print(f"another phase1_local run holds the sweep lock ({LOCK_PATH}) "
              "— refusing to double-spend the rate budget against data/",
              file=sys.stderr)
        return 3

    outdir = args.data_dir
    manifest = load_manifest(os.path.join(outdir, "manifest.jsonl"))
    jpath = os.path.join(outdir, "journal.jsonl")
    hpath = os.path.join(outdir, "hashes.jsonl")

    client = TimedPortalClient(USER_AGENT, args.timings_out)
    started_monotonic = time.monotonic()
    started_utc = utc_now_iso()

    def show_progress(snapshot):
        recent = client.timings[-60:]
        lat = describe_latencies(recent)
        errors = sum(1 for r in client.timings if "error" in r)
        print(f"progress: {snapshot['candidates']} candidates, "
              f"{snapshot['requests_made']} requests, "
              f"kept={snapshot['api_kept']} dropped={snapshot['api_dropped']} "
              f"at={snapshot['at_ticket']} | last{lat['n']}: "
              f"p50={lat['p50_s']}s p95={lat['p95_s']}s "
              f"max={lat['max_s']}s errors={errors}", flush=True)

    try:
        with SweepJournal(jpath) as journal, HashLog(hpath) as hashlog:
            pending = _pending_ids(manifest, journal)
            print(f"manifest: {len(manifest)} candidates; "
                  f"pending before this run: {len(pending)}"
                  + (f"; first={pending[0]}" if pending else ""),
                  flush=True)
            runner = SweepRunner(ADAPTER, client, journal, hashlog, manifest)
            stats = runner.run(limit=args.limit,
                               request_budget=args.max_requests,
                               progress_every=args.progress_every,
                               on_progress=show_progress)
    finally:
        client.close()
        os.close(lock_fd)   # closing the fd releases the flock

    elapsed = time.monotonic() - started_monotonic
    starts = [r["mono_s"] for r in client.timings]
    gaps = [round(b - a, 3) for a, b in zip(starts, starts[1:])]

    summary = {
        "started_utc": started_utc,
        "elapsed_s": round(elapsed, 1),
        "requests_total": len(client.timings),
        "min_start_gap_s": min(gaps) if gaps else None,
        "by_kind": {},
        "errors": {},
        "statuses": {},
        "overall_latency": describe_latencies(client.timings),
        "stats": stats,
    }
    for rec in client.timings:
        kind = rec["kind"]
        summary["by_kind"].setdefault(kind, {"n": 0, "errors": 0})
        entry = summary["by_kind"][kind]
        entry["n"] += 1
        if "error" in rec:
            entry["errors"] += 1
            summary["errors"][rec["error"]] = \
                summary["errors"].get(rec["error"], 0) + 1
        else:
            key = f"{kind}/{rec['status']}"
            summary["statuses"][key] = summary["statuses"].get(key, 0) + 1
    for kind, entry in summary["by_kind"].items():
        subset = [r for r in client.timings if r["kind"] == kind]
        entry["latency"] = describe_latencies(subset)

    summary_path = os.path.join(
        os.path.dirname(os.path.abspath(args.timings_out)),
        f"local_{started_utc.replace('-', '').replace(':', '')}.json")
    with open(summary_path, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2, sort_keys=True)
    print(json.dumps(summary, indent=2, sort_keys=True), flush=True)

    problems = check_outputs(outdir)
    if problems:
        print("INVARIANT CHECK FAILURES:", file=sys.stderr)
        for problem in problems[:20]:
            print(" ", problem, file=sys.stderr)
        return 2
    print("invariant checks: clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
