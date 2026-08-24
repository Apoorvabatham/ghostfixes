# GhostFixes — Project Brief

## What we're building

An open-source, forkable tool that ingests publicly accessible municipal grievance
data from Indian civic portals, flags closed complaints where the resolution evidence
is anomalous, and publishes the results as a static site with links to archived copies
of the original records.

It is **not an accusation engine**. It surfaces oddities and lets readers judge. The
output is a register of "closed tickets where something about the proof doesn't add
up," with the underlying numbers shown.

The end state is a repo any civic group in any Indian city can fork and run for their
own municipality in an afternoon.

## Hard invariants — never violate these, at any stage, no matter what

These are not preferences. If a task seems to require breaking one, stop and ask.

1. **No PII is ever written to disk.** Names, phone numbers, email addresses, house
   numbers, complainant identifiers — parse them if the page contains them, discard
   them in memory, never persist, never log, never commit. Store only: ticket ID,
   ward, zone, category, dates, image hashes, derived metrics.
2. **No LLM in the runtime pipeline.** You are writing the code; no model call ever
   sees a scraped record. All detection is deterministic and reproducible.
3. **Never use the word "fraud," "fake," "corrupt," or any synonym** in code, output,
   UI copy, commit messages, or README. Every published statement must be a
   falsifiable fact about a file or a timeline — e.g. "resolution photo mean
   brightness 4.2/255" or "identical image hash appears on 7 tickets." Nothing that
   requires defending an opinion.
4. **Only unauthenticated, publicly browsable endpoints.** No login flows. No session
   replay. Never enumerate or guess ticket IDs. Never reuse an `app_id`/`api_key`
   found embedded in a public URL to call a backend directly. If bulk browsing isn't
   publicly offered, that's an answer — stop and say so, don't find a way around it.
5. **Rate limit: 1 request per 3 seconds, hard.** Honest `User-Agent` on every request
   identifying the project and a contact email.
6. **No image files are committed or published**, except pitch-black frames (which
   contain no PII by definition). Everything else is represented by hash + archived
   link only.

## Stage 0 — Feasibility probe · GATE: build nothing else until this clears

Write a single throwaway script (`probe/`) that answers these and prints a report.
Do not scaffold the project, do not create the pipeline, do not pick a framework.

1. **Is there a sanctioned API?** MCD 311 claims Open311 compliance. Probe standard
   paths (`/open311/v2/discovery.json`, `/georeport/v2/`, `/api/v2/`) on the vendor
   domain. A 200 on discovery changes the entire architecture — report it loudly.
2. **Is the data already published?** Check `data.opencity.in` for the existing BBMP
   ward-level grievance datasets (2020–2025). If the fields we need are already
   there, we don't scrape for metadata at all.
3. **Logged-out visibility.** Can a closed ticket's detail page and its resolution
   photo be viewed with no cookies and no login?
4. **Direct image fetch.** `curl` a resolution photo URL with no session. 403 without
   cookies = the CV layer and the proof-link plan both die; report immediately.
5. **Is it JSON behind the page?** Inspect network traffic. If a JSON endpoint
   populates the page, we target that and skip the browser entirely. If it's ASP.NET
   `__VIEWSTATE`, flag the difficulty.
6. **EXIF survival.** Pull ~10 resolution photos, run `exiftool`. If GPS and original
   timestamps survive, say so before writing anything else — it likely replaces the
   entire CV layer with a far stronger signal.
7. **Foreign IP.** Same request from local, from a GitHub Actions runner, and note the
   difference. If Actions IPs are blocked, the free-hosting plan is dead and we
   restructure.

Output a written summary. **Then stop.**

## Stage 1 — Scope lock

One city, one category. Choose based on Stage 0 results — whichever gives an API or
surviving EXIF wins.

**Do not pick streetlights.** Legitimate resolution photos are taken at night and will
destroy the brightness heuristic. Garbage and potholes are the target: daytime,
visually obvious, high volume.

## Stage 2 — Ingestion

- Prefer JSON/API endpoint over browser automation. Only reach for Playwright if
  Stage 0 proved there's no alternative.
- Submit every ticket URL to `archive.org` at scrape time. Link the archived snapshot,
  never the live page — the party we're auditing controls the live page and can delete
  it.
- Append a daily `data/hashes.jsonl`: ticket ID, capture timestamp, image SHA-256,
  pHash, brightness mean/stddev. Commit it. This is our public tamper-evident audit
  trail — it's the receipt if anyone later claims a flag was fabricated.
- **Fail loudly.** Silent scraper breakage producing stale data is worse than no data.

## Stage 3 — Detection ladder

Implement in this order. Order reflects signal strength and legal safety — the
weakest, most false-positive-prone check comes last on purpose.

1. **Re-complaint rate** — same category + same location re-filed within N days of
   being marked resolved. Pure metadata, no images, no PII, no false-positive tuning.
   This is the headline metric. Not FR%.
2. **EXIF mismatch** (only if Stage 0 showed EXIF survives) — resolution photo
   geotagged far from the complaint, or timestamped before the complaint was filed.
3. **Recycled image** — pHash in a BK-tree, Hamming distance ≤ 8. Do not compare hash
   strings for equality; recompression breaks exact matches, which is precisely the
   case we're hunting. Guard against uniform-image collisions (blank walls, plain
   tarmac).
4. **Obstructed lens** — gate on brightness mean AND stddev together. A covered lens
   has near-zero variance; a dark scene with a light source has high variance. Add
   Laplacian variance for the no-detail case.

Every flag record stores the raw numbers that produced it, so any claim can be checked.

## Stage 4 — Validation · GATE: publish nothing before this clears

Build a small local review UI. The maintainer hand-labels 300 flagged items. Compute
precision per check type.

Do not generate any public-facing number, chart, or ward ranking until that precision
figure has been reviewed. When we publish, the methodology and the false-positive rate
go **next to** the numbers, not in a footnote.

Do not rank wards by raw anomaly rate — complaint-mix differences make it meaningless
and it invites a "worst ward" headline we can't defend. Normalise by category or don't
rank.

## Stage 5 — Static site

- Astro or Vite + Leaflet. Fully static, data as partitioned JSON in the repo, served
  by GitHub Pages. No SSR, no backend, no database.
- Per-city "last successful run" timestamp on the front page.
- Each entry: the check that fired, the raw numbers, the archived proof link. Black
  frames may be shown inline; nothing else.
- Standing disclaimer: automated quality-assurance flags on publicly available
  grievance metadata. Include a correction route for authorities to submit valid proof
  against a flag, and log corrections publicly.

## Stage 6 — Forkability

README good enough that a civic group in another city clones it, edits one adapter
file, and runs. Adapters live in `adapters/<city>.py` behind a common interface so a
new portal is one file, not a fork of the pipeline.

## Repo layout

```
adapters/        per-city ingestion, one file each
pipeline/        detection ladder, deterministic, unit-tested
data/            committed JSON + hashes.jsonl
review/          local labelling UI (never deployed)
site/            static frontend
probe/           Stage 0 throwaway scripts
```

## Stack

Python 3.11 (`httpx`, `pillow`, `imagehash`, `pyexiftool`; Playwright only if forced).
Astro/Vite + Leaflet. GitHub Actions cron. No paid services anywhere.

## Stop and ask before

- Writing anything beyond `probe/` until Stage 0 is reported
- Publishing any number before Stage 4 labelling is done
- Adding any dependency that costs money or requires an account
- Any workaround for an access restriction — **restrictions are answers, not
  obstacles**

## Commit attribution

This session runs a third-party model (`stealth/ox-alpha`) through OpenRouter, not
Anthropic's Claude. Do not write `Co-Authored-By: Claude ...` or any Anthropic
attribution in commit messages — it would be a false claim about who wrote the code.
Commit with no AI co-author trailer at all.

## Environment notes

- Running inside WSL2 (Ubuntu) under an OS-level bubblewrap sandbox: filesystem writes
  are confined to this project directory by the kernel, and reads outside it are
  blocked. This is enforced, not advisory.
- Network is default-deny. Only an allowlist of domains is reachable from Bash
  commands. If a host you need for Stage 0 is blocked, **say so and stop** — per
  invariant 4, an access restriction is an answer, not an obstacle. Ask before any
  allowlist change.
- No Python venv is possible here (`ensurepip` is missing from the system Python).
  Install project-local dependencies with
  `python3 -m pip install --target ./pylibs <pkg>` and run with
  `PYTHONPATH=$PWD/pylibs`. `pylibs/` is gitignored.
