"""Bounded Phase 1 dry run — end-to-end over a small mechanical subset.

Two subset rules, both stated BEFORE running and both purely positional —
nothing here is hand-picked after looking at tickets:

  --sample first (default): the FIRST N entries of the Stage A manifest in
  ascending numeric ticket-ID order. Recorded dry-run rule. On this corpus
  it lands inside the December-31 padding day, so it exercises selection,
  Stage-B drops and crash-resume but structurally cannot reach the kept
  path.

  --sample stride: Amendment C (2026-08-25, docs/stage1-scope-lock.md) —
  indices k*(len//N), a systematic content-blind spread across the whole
  padded window. Explicitly a MECHANISM-VALIDATION sample: it exists to
  exercise image fetch, hashing and scrape-stage resume, and must never be
  cited as evidence about Q1 prevalence or any rate.

Everything lands in probe/out/dryrun/ (gitignored); the stride sample
writes to *{_stride}.jsonl siblings and never touches data/. The full
manifest is written there too — the committed data/manifest comes only
with the real sweep. Checks enforced at the end:
  - every journal/hash/manifest record's keys sit inside its allowed
    universe;
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
MANIFEST_ALLOWED = {"ticket_id", "source", "csv_date_raw", "category_exact",
                    "normalization_fired"}
# Hex-boundary-guarded: a match adjacent to [a-fA-F] is inside a hash or
# other hex string (sha256/pHash carry ~3% false trips per digest raw, which
# would fail most clean stride legs). Pure-digit fields still match.
PHONE_RE = re.compile(r"(?<![0-9a-fA-F])[6-9][0-9]{9}(?![0-9a-fA-F])")
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def stride_subset(candidates, n):
    """Amendment C mechanism-validation sample: indices k*(len//n).

    A function of list position alone — no category, ward or outcome ever
    influences membership. Not a statistical sample; see module docstring.
    """
    stride = max(1, len(candidates) // n)
    return [candidates[k * stride] for k in range(n)]


def check_outputs(outdir):
    problems = []
    plans = (("journal", JOURNAL_ALLOWED), ("hashes", HASH_ALLOWED),
             ("manifest", MANIFEST_ALLOWED))
    for prefix, allowed in plans:
        for name in sorted(os.listdir(outdir)):
            if not (name.startswith(prefix) and name.endswith(".jsonl")):
                continue
            path = os.path.join(outdir, name)
            with open(path, encoding="utf-8") as fh:
                for lineno, line in enumerate(fh, 1):
                    rec = json.loads(line)
                    extra = set(rec) - allowed
                    if extra:
                        problems.append(
                            f"{name}:{lineno}: extra keys {sorted(extra)}")
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
    parser.add_argument("--sample", choices=("first", "stride"),
                        default="first")
    parser.add_argument("--data-dir", default="probe/out/dryrun")
    args = parser.parse_args(argv)

    outdir = args.data_dir
    os.makedirs(outdir, exist_ok=True)
    client = PortalClient(USER_AGENT)
    started = time.monotonic()

    candidates = build_full_manifest(client, outdir)
    csv_requests = client.requests_made
    if args.sample == "stride":
        subset = stride_subset(candidates, args.limit)
        suffix = "_stride"
        print(f"subset rule: Amendment C stride sample — indices k*"
              f"{max(1, len(candidates) // args.limit)} over {len(candidates)} "
              f"candidates ({len(subset)} tickets); mechanism-validation "
              "sample, not statistical")
    else:
        subset = candidates[:args.limit]
        suffix = ""
        print(f"subset rule: first {len(subset)} of {len(candidates)} "
              "candidates, ascending numeric ID order")

    jpath = os.path.join(outdir, f"journal{suffix}.jsonl")
    hpath = os.path.join(outdir, f"hashes{suffix}.jsonl")
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
    path = os.path.join(outdir, f"summary{suffix}.json")
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
