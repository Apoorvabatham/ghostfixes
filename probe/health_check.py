"""Resume-gate health check — scope-lock Amendment F (corrected 2026-08-26).

While the detail endpoint is globally unresponsive (stage0-report
Addendum 4), bounded batches resume only after a detail call answers.
This check spends at most TWO requests per run — the portal root, then
exactly ONE detail call against the FIRST PENDING ticket id in manifest
order (mechanical, never hand-picked) — and is meant to run at most once
every 30–60 minutes. A root 200 proves nothing about the detail surface
(measured: the root served 1.7 s responses throughout the outage); UP
requires detail HTTP 200.

One JSON line per run lands in probe/out/health.jsonl (gitignored); every
request also lands in probe/out/timings.jsonl like all other driver
traffic. Exit codes: 0 = up, nothing pending, or sweep already running;
1 = still down.

If the sweep lock is held, a batch is running by definition and this
check spends nothing. The flock here also makes a check and a batch
mutually exclusive, so health traffic can never interleave with sweep
traffic outside the limiter's own gate.
"""

import fcntl
import json
import os
import sys

from adapters.bengaluru import ADAPTER
from pipeline.journal import utc_now_iso
from pipeline.manifest import load_manifest

from phase1_local import (DATA_DIR, LOCK_PATH, TIMINGS_PATH, USER_AGENT,
                          TimedPortalClient)

ROOT_URL = "https://sahaaya2.bbmp.gov.in/"
HEALTH_PATH = os.path.join("probe", "out", "health.jsonl")
TERMINAL_PHASE1 = ("scrape_done", "api_dropped")


class HealthClient(TimedPortalClient):
    """TimedPortalClient plus a properly gated root fetch. get_bytes would
    tag the root as kind 'csv'; the root is not bulk data."""

    def fetch_root(self):
        def _gated_get(url):
            with self._limiter.request():
                self.requests_made += 1
                return self.client_for(True).get(url)
        return self._tagged("root", _gated_get, ROOT_URL)


def first_pending_id():
    """First non-terminal ticket in manifest order, from disk only."""
    manifest = load_manifest(os.path.join(DATA_DIR, "manifest.jsonl"))
    states = {}
    jpath = os.path.join(DATA_DIR, "journal.jsonl")
    if os.path.exists(jpath):
        with open(jpath, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    rec = json.loads(line)
                    states[rec["ticket_id"]] = rec["state"]
    for rec in manifest:
        tid = str(rec["ticket_id"])
        if states.get(tid) not in TERMINAL_PHASE1:
            return tid
    return None


def main():
    os.makedirs(os.path.dirname(HEALTH_PATH), exist_ok=True)
    rec = {"ts_utc": utc_now_iso()}
    code = 1

    os.makedirs(os.path.dirname(os.path.abspath(LOCK_PATH)), exist_ok=True)
    lock_fd = os.open(LOCK_PATH, os.O_CREAT | os.O_RDWR, 0o644)
    try:
        held = False
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            held = True
        except OSError:
            rec["verdict"] = "skipped_sweep_running"
            code = 0
        if held:
            tid = first_pending_id()
            rec["ticket_id"] = tid
            if tid is None:
                rec["verdict"] = "sweep_complete"
                code = 0
            else:
                client = HealthClient(USER_AGENT, TIMINGS_PATH)
                try:
                    try:
                        root = client.fetch_root()
                        rec["root_status"] = root.status_code
                    except Exception as exc:
                        rec["root_error"] = type(exc).__name__
                    try:
                        detail = client.fetch_detail(ADAPTER, tid)
                        rec["detail_status"] = detail.status_code
                    except Exception as exc:
                        rec["detail_error"] = type(exc).__name__
                finally:
                    client.close()
                rec["verdict"] = ("up" if rec.get("detail_status") == 200
                                  else "down")
                code = 0 if rec["verdict"] == "up" else 1
    finally:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
        except OSError:
            pass
        os.close(lock_fd)

    line = json.dumps(rec, sort_keys=True)
    with open(HEALTH_PATH, "a", encoding="utf-8") as fh:
        fh.write(line + "\n")
    print(line, flush=True)
    return code


if __name__ == "__main__":
    sys.exit(main())
