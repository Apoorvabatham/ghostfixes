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

Every other city waits. Not in parallel, not "while that's running" — the next city
starts only once this one is shipped, at Stage 7.

### Before locking: prove the source can actually produce check 1

Check 1 (re-complaint rate) is the headline metric, and it needs two fields that are
easy to assume and easy not to have:

- **A resolution/closure timestamp.** "Re-filed within N days of being *marked
  resolved*" is uncomputable without knowing when it was marked resolved. A single
  filing date plus a current status snapshot is not enough — a snapshot tells you
  where a ticket stands today, not when it moved.
- **A location granularity finer than ward.** A BBMP ward holds tens of thousands of
  people. "Same category + same ward within 30 days" fires for garbage in essentially
  every ward, every month. That is a description of a city, not a signal about a
  specific closed ticket.

Stage 0 established that the published `bbmp-grievances-data` CSVs (~767k rows,
2020–2025) have **neither**: `Grievance Date` is the only date, and `Ward Name` is the
only location. So the open dataset alone cannot produce check 1 as specified.

Before you lock scope, state in writing — in `docs/` — which reachable source supplies
the closure date and the sub-ward location, or that none does.

If none does, **do not quietly redefine the metric to fit the data and keep calling it
the headline number.** That is the single most likely way this project ends up
publishing something indefensible. The honest options are, in order of preference:

1. Find a source that carries closure dates and finer location (a portal ticket view,
   an API field, a per-ticket page).
2. Redefine check 1 explicitly, write down precisely what the weaker version does and
   does not support, and demote it from "headline" if it no longer carries that weight.
3. Report that the data does not support the project's central metric. Per the Stage 0
   spirit, that is a finding, not a failure — and it is worth more than a published
   number nobody can defend.

Whichever it is, the reasoning goes in `docs/` before Stage 2 begins.

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

At this point the interface is a guess — it has only ever had to fit one portal. Do not
over-engineer it here trying to predict what city 2 needs. Stage 7 is what tests it, and
a wrong guess is cheaper to correct with a real second portal in hand than to design
around in advance.

## Stage 7 — Next city · repeat, one at a time

Only once the current city is **actually shipped** — pipeline running, Stage 4 precision
measured and reviewed, site published, README forkable. Not "nearly done." A second city
started on top of a half-finished first city produces two half-finished cities.

Then pick the next city and run it through the same ladder:

1. **Stage 0 probe, again, for the new portal.** Every finding is portal-specific — API
   availability, logged-out visibility, EXIF survival, whether it's JSON or
   `__VIEWSTATE`. Assume nothing carries over. Report before building.
2. **Ask for the new domains.** They will not be reachable — see *Expanding the network
   allowlist* below. Do this first; it blocks everything else.
3. **Stage 1 scope lock** for that city: one category, same reasoning as before, still
   not streetlights.
4. **Write `adapters/<city>.py` and nothing else.** This is the real forkability test.
   If a new portal needs changes inside `pipeline/`, the adapter interface is wrong —
   fix the interface so the change lives in the adapter, rather than special-casing the
   pipeline per city. A pipeline with `if city == "..."` in it has failed Stage 6.
5. **Stage 4 validation again, per city.** Precision does not transfer. A threshold
   tuned on Bengaluru garbage photos is not a measured claim about Delhi. Re-label,
   re-measure, and publish that city's own precision figure next to its numbers.
6. Add the city to the site, with its own "last successful run" timestamp.

Rules for the loop:

- **One city at a time.** Never two in flight.
- **Never cross-contaminate detection.** No shared image-hash corpus across cities
  unless it's deliberate and documented — a recycled-image match across two different
  municipalities means something quite different from one inside a single ward, and it
  needs saying explicitly rather than falling out of an implementation detail.
- **Do not rank cities against each other.** Same reasoning as not ranking wards:
  portal-mix, category-mix and reporting-culture differences make the comparison
  indefensible, and it invites exactly the headline we can't stand behind.
- Every hard invariant applies unchanged to every new city. There is no
  "we already validated this approach" exemption.

## Expanding the network allowlist

The sandbox is default-deny and **you cannot widen it yourself** — settings files are
write-protected inside the sandbox by design, so any attempt to edit them will fail.
That is intentional, not a bug to work around.

When you need a domain that isn't reachable:

1. Stop.
2. List the exact domains, one per line, and say what each is for.
3. Ask for them to be added, then wait.

Never infer that a portal blocks you when the sandbox might be what refused the
connection — the two are indistinguishable from inside a failed request, and confusing
them writes a false finding into a probe report. If a request fails on a host that isn't
on the allowlist, the honest result is "not yet reachable from this sandbox," never "the
portal denied us."

## Repo layout

```
adapters/        per-city ingestion, one file each
pipeline/        detection ladder, deterministic, unit-tested
data/            committed JSON + hashes.jsonl
review/          local labelling UI (never deployed)
site/            static frontend
probe/           Stage 0 throwaway scripts
docs/            per-city probe reports and written findings
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
- Changing the locked city or category after Stage 1
- Starting a second city before the first one has actually shipped (Stage 7)
- Editing anything in `pipeline/` to accommodate a specific city's portal

## Credentials — do not look at them

`.github_token` and `.env` hold live secrets. **Never `cat`, `head`, `wc`, `grep`,
echo, log, or otherwise open them**, and never paste their contents into a command,
a file, or your own output. They exist to be used by tooling, not read by you. Reads
are blocked at the OS level, so an attempt will simply fail — that is expected, not a
bug to route around.

This matters more than usual here: this session runs on a third-party model whose
provider retains prompts, so anything that lands in your context has left the machine.
Pushing already works without you touching the token — the credential is embedded in
the git remote URL. `git push origin main` is all you need.

Never run `git remote add`, `set-url`, or `remove`, and never print the output of
`git remote -v` or `.git/config` without redacting anything after `https://` and
before `@`.

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
  sites. Any other city's portal is **not** reachable until it is added — expect this
  to be the first blocker at Stage 7.
- A blocked request and a portal refusing you are indistinguishable from inside the
  sandbox. Never report one as the other. If the host isn't on the allowlist above,
  the finding is "not yet reachable from this sandbox," and the fix is to ask for the
  domain, not to conclude anything about the portal. See *Expanding the network
  allowlist* for the procedure.
- Per invariant 4, a genuine access restriction — a login wall, a 403 with the domain
  allowed — is an answer, not an obstacle. Report it and stop.
- No Python venv is possible here (`ensurepip` is missing from the system Python).
  Install project-local dependencies with
  `python3 -m pip install --target ./pylibs <pkg>` and run with
  `PYTHONPATH=$PWD/pylibs`. `pylibs/` is gitignored.
