"""Append-only sweep journal — the checkpoint/resume spine.

Every ticket sits in exactly one recorded state after any interrupted run;
resume loads the journal and continues at the first incomplete ticket in
manifest order. Nothing is ever skipped silently (CLAUDE.md Stage 2: fail
loudly). Records carry only fields from the scope-lock §7 allowed universe.
"""

import json
import os
import sys
from datetime import datetime, timezone

# Forward order; a ticket's effective state is its last recorded event.
STATE_RANK = {
    "candidate": 0,
    "api_kept": 1,
    "api_dropped": 1,
    "scrape_done": 2,
    "archive_queued": 3,
    "archive_done": 4,
}
TERMINAL_STATES = ("archive_done", "api_dropped")
FAILED = "failed"


def utc_now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class TransitionError(ValueError):
    pass


def _assert_forward(prior_state, new_state):
    """Forward-only transitions, except: failures are recordable from anywhere,
    and retrying after a failure may go anywhere."""
    if prior_state is None or prior_state == FAILED or new_state == FAILED:
        return
    if prior_state in TERMINAL_STATES:
        raise TransitionError(
            f"{prior_state} is terminal; refusing {new_state}")
    if STATE_RANK[new_state] <= STATE_RANK[prior_state]:
        raise TransitionError(
            f"non-forward transition {prior_state} -> {new_state}")


class SweepJournal:
    def __init__(self, path):
        self.path = path
        self._fh = open(path, "a", encoding="utf-8")
        self._warned_no_fsync = False
        # Authoritative in-process view, seeded by replaying any existing
        # journal so appends from earlier runs constrain this one.
        self._cache = {}
        self._replay_into(self._cache)

    def _replay_into(self, target):
        if not os.path.exists(self.path):
            return
        with open(self.path, encoding="utf-8") as fh:
            for lineno, line in enumerate(fh, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError as exc:
                    # A torn final line after a hard kill is damage we
                    # surface, not skip: fail loudly.
                    raise ValueError(f"{self.path}:{lineno}: unparsable journal "
                                     "line — unparsable; fail loudly, do not skip") from exc
                target[rec["ticket_id"]] = rec

    def append(self, ticket_id, state, **detail):
        tid = str(ticket_id)
        prior = self._cache.get(tid)
        _assert_forward(prior["state"] if prior else None, state)
        rec = {"ticket_id": tid, "ts_utc": utc_now_iso(), "state": state}
        rec.update(detail)
        line = json.dumps(rec, ensure_ascii=False, sort_keys=True)
        self._fh.write(line + "\n")
        self._fh.flush()
        try:
            os.fsync(self._fh.fileno())
        except OSError:
            # Some filesystems refuse fsync; flush still gives crash-ordering
            # within the process. Warned once — never silently ignored.
            if not self._warned_no_fsync:
                print("journal: fsync unavailable on this filesystem; "
                      "relying on flush()", file=sys.stderr)
                self._warned_no_fsync = True
        self._cache[tid] = rec
        return rec

    def state_map(self):
        """Copy of ticket_id -> last record."""
        return dict(self._cache)

    def state_of(self, ticket_id):
        prior = self._cache.get(str(ticket_id))
        return prior["state"] if prior else None

    def counts(self):
        tally = {}
        for rec in self._cache.values():
            tally[rec["state"]] = tally.get(rec["state"], 0) + 1
        return tally

    def close(self):
        self._fh.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        # Closing on the exception path too: a long sweep must never leak
        # the handle when a ticket blows up mid-run.
        self.close()
        return False
