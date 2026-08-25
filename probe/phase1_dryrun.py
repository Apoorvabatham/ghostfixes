"""Bounded Phase 1 dry run — end-to-end over a small mechanical subset.

Subset rule, stated BEFORE running (scope-lock requirement): the FIRST N
entries of the Stage A manifest in ascending numeric ticket-ID order.
N=50 by default; nothing here is hand-picked after looking at tickets.

Everything lands in probe/out/dryrun/ (gitignored). The full manifest is
written there too — the committed data/manifest comes only with the real
sweep. Checks enforced at the end:
  - every journal record's keys sit inside the allowed universe;
  - every hash record's keys sit inside the allowed universe;
  - no Indian mobile-number or email pattern appears in ANY output file
    (digit-run guarded so epoch milliseconds cannot false-positive);
  - measured per-ticket request count is reported against the 4.5 figure.
"""

import argparse
import csv
import io
import json
import os
import re
import sys
import time

from adapters.bengaluru import ADAPTER
from pipeline.fetcher import PortalClient
from pipeline.hashing import HashLog
from pipeline.journal import SweepJournal
from pipeline.manifest import build_candidates, load_manifest
from pipeline.sweep import SweepRunner

USER_AGENT = ("GhostFixes/0.1-phase1-dryrun "
              "(+https://github.com/Apoorvabatham/ghostfixes; "
              "contact: apba00001@uni-saarland.de)")


def rows_from_bytes(data, label):
    """csv.DictReader over in-memory bytes. PII-bearing columns exist on
    these rows; only adapter.parse_csv_row may read fields, and nothing is
    ever written to disk from here."""
    text = io.TextIOWrapper(io.BytesIO(data), encoding="utf-8")
    return label, csv.DictReader(text)


def build_full_manifest(client, outdir):
    path = os.path.join(outdir, "manifest.jsonl")
    if os.path.exists(path):
        return load_manifest(path)
    sources = []
    for label, url in sorted(ADAPTER.csv_sources().items()):
        resp = client.get_bytes(url)
        if resp.status_code != 200:
            raise RuntimeError(f"CSV {label} HTTP {resp.status_code} — "
                               "fail loudly per scope-lock §9.6")
        sources.append(rows_from_bytes(resp.content, label))
        del resp
    candidates, duplicates = build_candidates(ADAPTER, sources)
    with open(path, "w", encoding="utf-8") as fh:
        for rec in candidates:
            fh.write(json.dumps(rec, ensure_ascii=False,
                                sort_keys=True) + "\n")
    print(f"manifest: {len(candidates)} candidates "
          f"({duplicates} duplicate IDs skipped) -> {path}")
    return candidates


JOURNAL_ALLOWED = {"ticket_id", "ts_utc", "state", "api_date",
                   "api_date_raw", "csv_date_raw", "ward", "category",
                   "sub_category", "citizen_status", "staff_status",
                   "image_urls", "images_hashed", "images_failed_object",
                   "stage", "http_status", "error"}
HASH_ALLOWED = {"ticket_id", "ts_utc", "url", "image_sha256", "phash",
                "brightness_mean", "brightness_stddev", "width", "height",
                "format"}
PHONE_RE = re.compile(r"(?<![0-9])[6-9][0-9]{9}(?![0-9])")
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def check_outputs(outdir):
    problems = []
    for name, allowed in (("journal.jsonl", JOURNAL_ALLOWED),
                          ("hashes.jsonl", HASH_ALLOWED)):
        path = os.path.join(outdir, name)
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as fh:
            for lineno, line in enumerate(fh, 1):
                rec = json.loads(line)
                extra = set(rec) - allowed
                if extra:
                    problems.append(f"{name}:{lineno}: extra keys {extra}")
    for name in os.listdir(outdir):
        path = os.path.join(outdir, name)
        if not os.path.isfile(path):
            continue
        text = open(path, encoding="utf-8", errors="strict").read()
        for lineno, line in enumerate(text.splitlines(), 1):
            if PHONE_RE.search(line):
                problems.append(f"{name}:{lineno}: phone-like digit run")
            if EMAIL_RE.search(line):
                problems.append(f"{name}:{lineno}: email-like string")
    return problems


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--data-dir", default="probe/out/dryrun")
    args = parser.parse_args(argv)

    outdir = args.data_dir
    os.makedirs(outdir, exist_ok=True)
    client = PortalClient(USER_AGENT)
    started = time.monotonic()

    candidates = build_full_manifest(client, outdir)
    csv_requests = client.requests_made
    subset = candidates[:args.limit]
    print(f"subset rule: first {len(subset)} of {len(candidates)} "
          "candidates, ascending numeric ID order")

    jpath = os.path.join(outdir, "journal.jsonl")
    hpath = os.path.join(outdir, "hashes.jsonl")
    with SweepJournal(jpath) as journal, HashLog(hpath) as hashlog:
        runner = SweepRunner(ADAPTER, client, journal, hashlog, subset)
        stats = runner.run()
        elapsed = time.monotonic() - started

    summary = {
        "subset": len(subset), "elapsed_s": round(elapsed, 1),
        "requests_total": client.requests_made,
        "csv_requests": csv_requests,
        "per_ticket_requests": round(
            client.requests_made / max(len(subset), 1), 2),
        "stats": stats,
    }
    path = os.path.join(outdir, "summary.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2, sort_keys=True)
    print(json.dumps(summary, indent=2, sort_keys=True))

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
