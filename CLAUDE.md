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

## Stage 1.5 — Portal survey · reconnaissance only, strictly time-boxed

Runs **after** scope lock, **before** Stage 2. Purpose: find out how much the portals
differ *before* the adapter interface gets baked in, so Stage 6 forkability is a design
we chose rather than a retrofit we regret. An interface derived from exactly one portal
will fit exactly one portal.

**This stage looks. It does not build.** You are still committed to the one city and one
category locked in Stage 1 — this does not reopen that decision, and nothing surveyed
here gets scraped, ingested, or turned into a working adapter now.

Survey **2–3 other Indian municipal portals** (different cities, and ideally a different
portal vendor — reusing the same vendor teaches you nothing about generalising). For
each, record only what's visible from a handful of public page loads:

- City, portal URL, and the vendor/software behind it if identifiable
- Open311 or any sanctioned API? (probe the same discovery paths as Stage 0)
- Is logged-out browsing of closed tickets possible at all?
- Are resolution photos publicly fetchable without a session?
- Does EXIF survive? (a couple of images is enough — don't bulk-pull)
- The shape of the data: JSON endpoint, server-rendered HTML, or ASP.NET `__VIEWSTATE`
- What a ticket URL looks like, and whether ward/zone/category are exposed as fields

Write it to `docs/portal-survey.md` as a comparison table, then add a short section:
**what varies across portals, and therefore what the `adapters/<city>.py` interface must
abstract.** That conclusion is the actual deliverable — the table is just evidence.

Constraints, all of them non-negotiable:

- **Every hard invariant still applies in full.** Especially: 1 request per 3 seconds,
  honest User-Agent, no login flows, no ID enumeration, and access restrictions are
  answers rather than obstacles. A survey is not a licence to poke harder.
- **Time-box: 2 hours.** If a portal is fighting you, record "could not determine
  without authentication" and move on. An honest unknown in the table is worth more
  than an hour of prodding.
- **Do not write `adapters/` files for surveyed cities.** One adapter — the Stage 1
  city — is all that exists until Stage 6.
- **Do not expand scope.** If a surveyed portal looks like better data than the one you
  locked, that is a note in `docs/portal-survey.md` and nothing more. Stop and ask
  before acting on it.

### Expanding the network allowlist

The sandbox is default-deny and **you cannot widen it yourself** — settings files are
write-protected inside the sandbox by design, so any attempt to edit them will fail.
That is intentional, not a bug to work around.

When you need domains this stage can't reach:

1. Stop.
2. List the exact domains, one per line, and say what each is for.
3. Ask for them to be added, then wait.

Never infer that a portal blocks you when the sandbox might be what refused the
connection — those two look identical from inside a failed request, and confusing them
puts a false finding into the survey. If a request fails on a host that isn't on the
allowlist, the honest report is "not yet reachable from this sandbox," not "the portal
denied us."

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

The interface is validated against `docs/portal-survey.md` from Stage 1.5: every
variation recorded there must be expressible through the adapter interface without
touching `pipeline/`. If one isn't, the interface is wrong — fix it here, where it is
still cheap, rather than discovering it when someone else's fork fails.

## Repo layout

```
adapters/        per-city ingestion, one file each
pipeline/        detection ladder, deterministic, unit-tested
data/            committed JSON + hashes.jsonl
review/          local labelling UI (never deployed)
site/            static frontend
probe/           Stage 0 throwaway scripts
docs/            portal-survey.md and other written findings
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
- Reaching a domain that isn't on the sandbox allowlist — list what you need and wait
- Changing the locked city or category after Stage 1, including because Stage 1.5
  turned up a portal with better data
- Writing an adapter for any city other than the Stage 1 city, before Stage 6

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
  commands. Currently allowed: the Stage 0 targets (`data.opencity.in`,
  `mcdonline.nic.in`, `bbmp.gov.in`), `archive.org`, package registries, and docs
  sites. Any other city's portal — including everything Stage 1.5 surveys — is **not**
  reachable until it is added.
- A blocked request and a portal refusing you are indistinguishable from inside the
  sandbox. Never report one as the other. If the host isn't on the allowlist above,
  the finding is "not yet reachable from this sandbox," and the fix is to ask for the
  domain, not to conclude anything about the portal. See *Expanding the network
  allowlist* under Stage 1.5 for the procedure.
- Per invariant 4, a genuine access restriction — a login wall, a 403 with the domain
  allowed — is an answer, not an obstacle. Report it and stop.
- No Python venv is possible here (`ensurepip` is missing from the system Python).
  Install project-local dependencies with
  `python3 -m pip install --target ./pylibs <pkg>` and run with
  `PYTHONPATH=$PWD/pylibs`. `pylibs/` is gitignored.
