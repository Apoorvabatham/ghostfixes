# Stage 1 scope lock — Bengaluru/GBA · Solid Waste (Garbage) Related · Q1 2025

**Status: LOCKED 2026-08-25.** Written per CLAUDE.md §Stage 1 immediately after the
Stage 1 gate decision (option 2, same date — see `docs/stage1-gate.md`). Nothing in
Stage 2 begins ahead of this file. Any change to city, category, window, ward set,
or selection rule requires a dated amendment committed **before** the affected sweep
run; silent deviation is prohibited.

---

## 1. The lock, stated once

| Dimension | Value |
|---|---|
| City | Bengaluru (BBMP, under GBA) |
| Category | `Solid Waste (Garbage) Related` — exact top-level string, all sub-categories |
| Window | `Grievance Date` 2025-01-01 00:00 → 2025-03-31 23:59 portal-local (Q1 2025) |
| Rule form | Last complete calendar quarter before the corpus freeze (see §4) |
| Ward set | All 198 wards — no ward filtering |
| Corpus size | **16,747 ticket IDs** (CSV row count for the window) |
| Sources | opencity CSV = ID corpus · keyless Sahaaya API = timestamps/statuses · staff+citizen images = proof artifacts · archive.org = tamper-evidence |

Every other category, quarter, year and city is out of scope until this one ships.

## 2. Selection rule — verbatim, mechanical, two-stage

The 12-hour AM/PM artifact measured in the published CSV (`docs/citizen-exif-probe-2026-08-25.md`: 12/45 sampled rows shifted exactly 12 h vs the live API) means a CSV-date window cannot be trusted at its edges. The rule therefore runs in two stages:

> **Stage A — candidate set (published CSV, resource `BBMP Grievances 2025`).**
> Take every row whose `Category` equals the literal string
> `Solid Waste (Garbage) Related`, and whose `Grievance Date` field begins with
> `2024-12-31`, `2025-01`, `2025-02`, `2025-03`, or `2025-04-01`. Collect their
> `Complaint ID` values verbatim. (Padding of one calendar day on each side of the
> window fully absorbs a ±12 h shift.)

> **Stage B — membership (live API).** For each candidate ID, fetch
> `GetComplaintDetailforCitizen` and keep the ticket **iff** the API's
> `GrievanceDate` falls inside `[2025-01-01T00:00:00, 2025-04-01T00:00:00)` in the
> portal's own local-clock frame. The API date is the sole membership and
> timestamp authority thereafter; the CSV date is never used in any arithmetic.

No other filtering, ordering preference, or manual removal is applied. The
candidate set, the kept set, and every dropped-at-Stage-B ID with its two dates
are logged to the run journal, so the rule's application is reproducible end to end.
(Whitespace normalisation of the category comparison is permitted; if it ever
fires differently from exact equality, that fact is recorded.)

## 3. Why this city

Decided by Stage 0 (`docs/stage0-report.md`): Bengaluru is the only examined city
with a sanctioned public bulk corpus (767k rows, six yearly CSVs) **and** a
measured keyless per-ticket surface (`GetComplaintDetailforCitizen`,
`docs/stage1-gate.md` §1) supplying filing timestamps, status, and staff/citizen
image URLs logged-out. Delhi has no sanctioned route to ticket content at all
(keyed vendor API, replay forbidden by invariant 4). No new evidence has arrived.

## 4. Why this category — measured

Six-year category volumes (aggregated from the published CSVs, method in Appendix):

| Category | 2020 | 2021 | 2022 | 2023 | 2024 | 2025* | total |
|---|---|---|---|---|---|---|---|
| Electrical | 33,822 | 50,229 | 56,892 | 51,892 | 75,155 | 42,138 | 310,128 |
| **Solid Waste (Garbage) Related** | **24,022** | **24,184** | **22,828** | **28,639** | **57,329** | **38,151** | **195,153** |
| Road Maintenance(Engg) | 16,372 | 16,680 | 21,485 | 17,901 | 24,973 | 14,124 | 111,535 |
| Forest | 4,349 | 2,640 | 3,821 | 5,760 | 11,723 | 6,325 | 34,618 |

\* 2025 ends at the 2025-06-19 freeze.

- **Garbage, not potholes: no pothole category exists in this corpus.** Roads
  appear only as `Road Maintenance(Engg)` / `Road Infrastructure` — mixed work
  orders (paving, drains, footpaths) whose photo subjects vary wildly; the
  pothole-specific data on opencity is a separate May–Jun 2022 dataset outside
  the grievance corpus.
- **Garbage beats roads on the headline check's failure mode.** Ladder check 1
  (recycled image) must suppress uniform-image collisions, and CLAUDE.md names
  the exact hazard: plain tarmac. Pothole documentation is asphalt close-up
  photography; garbage photos are textured, context-rich frames — the safer
  substrate for pHash matching.
- **Electrical is larger but excluded**: it is the streetlight-adjacent world —
  night photography degrades the brightness/variance checks, and CLAUDE.md
  forbids streetlights outright.
- Garbage spans **all 198 wards in every year measured**, so no geography is
  silently unsampled.

Sub-categories inside Solid Waste are **not filtered**: narrowing would shrink
pHash match opportunities without reducing collision risk, and sub-category is
stored per ticket anyway for later slicing.

## 5. Why this window

Monthly Solid Waste volumes around the candidates: Jul–Dec 2024 averaged ~5,400/mo;
Jan–Mar 2025 ran 4,345 / 5,728 / 6,674; Apr 1–Jun 19 2025 produced 21,404 in a
truncated, right-censored span.

| Candidate window | n | Closure opportunity before freeze | Status at freeze | Verdict |
|---|---|---|---|---|
| 2024-Q4 | 17,981 | 171–261 days | 97.95% Closed | viable, older images likelier pruned/moved |
| **2025-Q1** | **16,747** | **80–170 days** | **97.59% Closed** | **locked** |
| 2025 Apr 1–Jun 19 | 21,404 | 0–79 days, truncated month | 91.63% Closed | rejected: censoring dominates the status field |

- **Rule form: "the last complete calendar quarter before the corpus freeze."**
  Mechanical, needs no judgement about the data's contents, and transfers
  verbatim to any forked city's export — which is the Stage 6 test.
- Every locked ticket has ≥80 days of life before the freeze, so the frozen
  status snapshot is informative rather than censoring-dominated (Apr–Jun 2025
  demonstrates the failure mode: 91.6% closed and falling as filing date
  approaches the freeze).
- Recent-enough that portal-side image retention is likeliest to still serve
  staff photos (samples fetched successfully were 2024-vintage).
- Rejected alternative shape: **single-ward deep slice** (e.g. one ward, all
  six years). It maximises per-ward match depth but amputates the ward
  dimension from every cross-ward analysis and concentrates conclusions in a
  ward nobody chose mechanically. Date-bounded × all-wards keeps the full
  geographic spread inside one temporal box.

Note for honesty: the snapshot also contains a `ReOpen` status value (114 in
window). It carries no transition timestamps, so it bounds nothing about when a
re-open happened and does **not** resurrect check 1; retired means retired
(`docs/stage1-gate.md`).

## 6. Request budget at the hard 1 req / 3 s limit

Two populations, amended 2026-08-25 after the Phase 1 dry-run manifest build
measured them:

- **Candidates** — the Stage A padded superset: **17,137** tickets, each
  incurring exactly one detail call. The unpadded Q1 core is 16,747
  (Jan 4,345 + Feb 5,728 + Mar 6,674); the +390 is exactly the two pad days
  (2024-12-31: 142; 2025-04-01: 248). No whitespace normalisation fired;
  every candidate is category-exact.
- **Kept** — Stage B members, decided on the live API timestamp alone:
  planned ≈ **16,747** as pad-day tickets fail membership and converge the
  set back toward the unpadded quarter. Image work attaches to this set
  only. (Amendment B removed archiving entirely; statuses arrive on the
  detail payload itself, so no separate status-poll request exists.)

Expected requests per kept ticket: staff image ~0.85 (measured populated
17/20, staff block 41/45) + citizen image ~0.40 (ImagePath 8/20) ≈
**1.25**, plus the one detail call every candidate pays. Planned at
**4.5** per candidate with retry headroom in the worst case.

| Quantity | Value |
|---|---|
| Candidates (Stage A, detail calls) | 17,137 |
| Kept (Stage B, image work attaches here) | ≈ 16,747 |
| Expected requests | 17,137 + 16,747 × 1.25 ≈ **38,100** |
| Planned request ceiling | 17,137 × 4.5 ≈ **77,100** |
| Pure limiter floor (× 3 s) | ≈ 32 h expected · ≈ 64 h worst-case ceiling |
| Theoretical max at 100% utilisation | 28,800 req/day ⇒ ~6,400 tickets/day |
| Planning figure at realistic duty cycle | ~4,500 tickets/day ⇒ **~4 calendar days** |
| Under GitHub Actions 6 h job cap | ~7,200 req/run ⇒ **~6–11 runs** expected-to-ceiling, therefore the sweep MUST be checkpointed/resumable |

The 3-second limiter is **global across all hosts** — portal API, image hosts,
S3, and archive.org draw from one budget. These are planning figures; the
limiter, not optimism, sets the floor.

## 7. Surfaces and fields consumed per ticket

- **ID corpus:** `BBMP Grievances 2025` resource on `data.opencity.in`. IDs are
  taken verbatim — never guessed, never enumerated (invariant 4).
- **Metadata:** `GET sahaaya2.bbmp.gov.in/webapi/api/grievance/GetComplaintDetailforCitizen?ComaplaintID=<id>`
  (keyless; their typo is part of the route). Consumed fields:
  `GrievanceId`, `GrievanceDate`, `Ward`, `CategoryEnglish`, `SubCategoryEnglish`,
  `ComplaintStatus`, `ImagePath`; staff block: `GrievanceStatus`,
  `StaffRecentAddedImage`.
- **Parsed-and-discarded in memory, never persisted or logged (invariant 1):**
  `Address`, `Description`, `StaffRemarks`, `StaffName`, `ContactDetails`.
  Enforcement is a response whitelist before anything touches storage.
- **Staff images:** URLs followed exactly as returned (both `bbmp.gov.in` and
  `bbmpgov.in` spellings and legacy paths occur); fetched keyless; loose-TLS
  fallback where the host serves an incomplete chain (documented portal-side
  property, not a workaround of an access restriction).
- **Citizen images:** S3 originals fetched keyless where offered; observed
  403s and literal-`null` paths are recorded as-is, not retried into existence.
- **Archive:** ~~every ticket's detail URL is submitted to archive.org at
  capture time; published links point at archived snapshots, never live
  pages~~ — VOIDED by Amendment B (2026-08-25): no per-ticket or image-URL
  archiving ever; hashes.jsonl + re-fetch instructions carry verification.
- Derived record per ticket (the allowed universe): ticket ID, ward, category,
  sub-category, API filing timestamp, status fields, image SHA-256 + pHash +
  brightness mean/stddev + Laplacian variance, filename-decoded resolution
  moment, capture-time deltas where EXIF offers them. **Device `Make`/`Model`
  is read never — not parsed, not stored, not logged** (quasi-identifying with
  ward + timestamp; Stage 3 constraint).

## 8. Checks enabled on this scope (revised ladder)

| # | Check | Input in this scope | Standing |
|---|---|---|---|
| 1 | Recycled image (pHash, BK-tree, Hamming ≤ 8, uniform-image guard) | staff photos ~85% coverage + citizen photos where served | **headline** |
| 2 | Obstructed lens (brightness mean AND stddev gates + Laplacian variance) | same photos | secondary |
| 3 | Fast closure (staff-filename timestamp − API filing time) | staff-imaged subset | **corroboration only — never leads**; self-reported-artifact weakness printed beside every appearance |
| 4 | Aged-open at freeze (still `Registered`/`In Progress`) | all tickets | backlog measure, labelled as such |

Explicitly **not built**: EXIF mismatch (dead on staff surface, leak-shaped on
citizen surface — Stage 3); re-complaint rate in any form (retired
uncomputable); ward ranking by raw anomaly rate (Stage 4 constraint);
cross-city comparison (Stage 7 constraint).

Interpretation boundary for check 1, fixed now: a pHash match establishes that
the same pixels recur across tickets — a fact about files. Whether recurrence
on two garbage tickets reflects recycled proof or one persisting uncleared pile
photographed twice is exactly what Stage 4 hand-labelling must measure before
any number publishes.

## 9. Binding constraints carried into Stage 2

1. Timestamps: live API only, everywhere (§2 Stage B is the template).
2. No device identifiers, ever (§7).
3. Wording: all published claims scoped as an audit of filings 2025-01-01 →
   2025-03-31 in the frozen corpus ending 2025-06-19 — never current performance.
4. This document is the sweep's selection rule; amendments precede runs (header).
5. Invariants 1–6 unchanged: PII never persists; no LLM sees records; falsifiable
   phrasing; keyless endpoints only; global 1 req/3 s with project UA; no image
   committed or published except pitch-black frames.
6. Fail loudly: a degraded surface (auth wall appears, image hosts start
   refusing, archive.org fails) halts the run with an error — stale silence is
   worse than stopping. An access restriction encountered mid-sweep is reported,
   not routed around.

## 10. Known risks and degradation behaviour

- **Keyless API closes** → sweep stops; that is a finding, reported per invariant 4.
- **Staff-image coverage lands far below the sampled 85%** → checks 1–3 lose
  inputs gracefully; check 4 is unaffected; the shortfall is published with the
  numbers.
- **S3 objects intermittently 403** → recorded per object; no retry storm; the
  citizen layer is corroboration, not the spine.
- **pHash collision pressure** unknown until Stage 4 measures precision; the
  uniform-image guard (stddev + Laplacian floors) is mandatory before any pair
  becomes a flag.

---

## Appendix — measured volumes (provenance)

Method: the six published yearly CSVs were downloaded once each (project UA,
requests spaced ≥3 s), streamed row-by-row with only aggregates retained in
memory, and deleted immediately; no row-level data was persisted anywhere.
Aggregates: `probe/out/sizing/volumes.json` (gitignored).

- Corpus totals: 91,620 / 103,504 / 118,394 / 119,140 / 207,016 / 126,974 =
  **766,648** rows, 2020-02-08 → 2025-06-19 (max `Grievance Date` observed:
  2025-06-19 12:59).
- Columns confirmed identical across all six resources: `Complaint ID`,
  `Category`, `Sub Category`, `Grievance Date`, `Ward Name`, `Grievance Status`,
  `Staff Remarks`, `Staff Name`.
- Distinct `Ward Name` among Solid Waste rows: **198**, in every year.
- Monthly Solid Waste counts 2024: Jan 3,398 · Feb 4,003 · Mar 4,031 · Apr 3,547
  · May 4,965 · Jun 5,005 · Jul 5,662 · Aug 4,834 · Sep 3,903 · Oct 8,188 ·
  Nov 5,215 · Dec 4,578. 2025: Jan 4,345 · Feb 5,728 · Mar 6,674 · Apr 6,719 ·
  May 6,828 · Jun-to-freeze 7,857.
- Frozen-status histograms for candidate windows (Solid Waste only):
  - 2024-Q3 (n=14,399): Closed 14,155 · Non Relevant 212 · ReOpen 25 · Long Term Solution 7
  - 2024-Q4 (n=17,981): Closed 17,613 · Non Relevant 256 · ReOpen 112
  - **2025-Q1 (n=16,747): Closed 16,344 · Non Relevant 288 · ReOpen 114 · In Progress 1**
  - 2025 Apr 1–Jun 19 (n=21,404): Closed 19,613 · Registered 1,227 · Non Relevant 265 · ReOpen 200 · In Progress 86 · null 13

---

# Amendment A — 2026-08-25: measured archival cost forces a two-phase sweep

> **SUPERSEDED IN PART by Amendment B (2026-08-25), at end of file:** the
> Phase 2 plan, its ≤4-in-flight limiter interpretation, and the
> archived-proof-link form never entered service and are void — the sweep is
> Phase 1 only. See Amendment B for the maintainer's decision and what
> replaces them.

Per the header's amendment rule, this correction is committed before any sweep
run touches the locked corpus. It changes §6's planning figures and §7's
archive bullet; nothing else in the lock moves.

**Measured** (`docs/stage0-report.md`, Addendum 2): anonymous Save Page Now
blocks ~78 s per URL until capture completes; CDX spot-checks cost ~27 s; the
canonical snapshot link resolves <1 s. Keyless archiving works — no account,
which the no-accounts constraint requires.

**Consequence:** serializing saves into the scrape loop makes archiving the
dominant wall-clock term (~16,747 × ~81 s ≈ 16 days) and invalidates §6's
"~4 calendar days" as a whole-sweep figure. The sweep therefore runs in two
phases:

- **Phase 1 — scrape:** detail calls + image fetches + hashing + `hashes.jsonl`
  audit trail, exactly the §6 arithmetic (~75,400 requests ≈ 63 h limiter floor
  ≈ 4–5 days realistic). No archive.org time inside this phase.
- **Phase 2 — archive:** one save per ticket URL against the Phase 1 manifest,
  checkpointed and resumable like everything else.

**Limiter interpretation for Phase 2, stated explicitly because invariant 5 is
hard:** request *starts* remain globally ≤1 per 3 s across all hosts; long
server-side capture waits may overlap, with at most **4 saves in flight** and
any throttling signal honoured immediately. Under that rule Phase 2's floor is
the start-rate itself (16,747 × 3 s ≈ 14 h of start slots) plus capture-latency
tail — planned **1–2 days**, bringing the whole-sweep plan to roughly a week.
The stricter alternative reading (fully serial ⇒ ~16 days) is recorded here so
this choice is visible and reversible by a future amendment.

**Also amended:** published proof links take the canonical form
`https://web.archive.org/web/<timestamp>/<original-url>`; CDX lookups are
sampled spot-checks, never a per-ticket step. And the permanence flag from the
Stage 0 report applies here too: archived snapshots are BBMP's keyless JSON and
irreversibly public — **maintainer sign-off is requested before Phase 2 begins**
(the mechanism is validated on one sample URL already; no further URLs are
archived until then).

---

# Amendment B — 2026-08-25: archiving policy reversed; Phase 2 void (maintainer decision)

The permanence flag raised in `docs/stage0-report.md` Addendum 2 was put to
the maintainer with a request for sign-off before Phase 2 ran at scale. The
answer is a decline, at any scale, superseding the parts of Amendment A that
Phase 2 depended on:

> Phase 2 archiving: DECLINED at any scale. Your permanence flag is right and
> decisive. The detail endpoint returns Address, Description, StaffName and
> ContactDetails — the exact fields invariant 1 forbids persisting.
> Submitting those URLs to Save Page Now would permanently publish and index
> that PII for ~16,747 citizens, irreversibly, with us as the cause. That the
> endpoint is keyless does not make it published; unindexed-and-keyless is
> not public.

Rules replacing every contrary statement above:

1. **No per-ticket archiving of API URLs. Ever.**
2. **No archiving of image URLs either** — same exposure through a different
   door (faces, plates, house numbers).
3. **The six source CSVs are archived once** — already-published bulk data,
   no new exposure, and it pins the ID corpus. Execution record in the
   appendix below.
4. **`data/hashes.jsonl` remains the tamper-evidence spine:** SHA-256
   committed publicly at a known date is stronger than a snapshot, because it
   is published before anyone knows which tickets get flagged.
5. **Published register entries carry ticket ID, raw numbers, capture date
   and the committed hash**, with instructions to re-fetch and compare.
   Stage 5 must not imply a human-readable archived record page exists.

Consequences: the sweep is Phase 1 only — §6's archive rows and planning
figures for Phase 2 are void, as is Amendment A's ≤4-in-flight limiter
interpretation (the global start-rate gate of invariant 5 is unaffected).
The single mechanism-validation snapshot recorded in the Stage 0 report
(`ComaplaintID=20446742`) cannot be deleted through any sanctioned keyless
route; it stands recorded as irreversible rather than hidden.

## Appendix — source-CSV archival record (Amendment B rule 3)

Executed 2026-08-25 against the six published CKAN resource URLs, keyless
Save Page Now (`GET web.archive.org/save/<url>`), project User-Agent,
≥3 s between request starts. Measured behaviour differs from the small JSON
page validated in Stage 0: for multi-megabyte CSVs the save endpoint answers
**HTTP 302** in seconds (the capture job is queued, not blocked-on), and the
capture completes server-side moments later. Confirmation is per-resource
via CDX, plus one replay check:

| resource | save HTTP | save seconds | CDX timestamp | CDX status |
|---|---|---|---|---|
| BBMP Grievances 2020 | 302 | 13.3 | 20260825125117 | 200 |
| BBMP Grievances 2021 | 302 | 6.7 | 20260825125150 | 200 |
| BBMP Grievances 2022 | 302 | 6.7 | 20260825125213 | 200 |
| BBMP Grievances 2023 | 302 | 6.6 | 20260825125321 | 200 (confirmed on re-query) |
| BBMP Grievances 2024 | 302 | 6.7 | 20260825125357 | 200 |
| BBMP Grievances 2025 | 302 | 36.8 | 20260825125445 | 200 |

All six CDX entries carry mimetype `text/csv`. Replay spot-check on the 2025
snapshot (canonical form `web.archive.org/web/20260825125445/<url>`):
HTTP 200, `text/csv`, 18,272,067 bytes. The ID corpus for the locked window
is thereby pinned at a known date under Amendment B's rules.

# Amendment C — 2026-08-25: mechanism-validation stride sample for Phase 1 dry runs

Committed **before** any run under this rule, per the lock header.

## Motivation (measured)

The recorded dry-run subset rule — first N manifest rows in ascending
numeric ID order — lands entirely inside the 2024-12-31 padding day: all 50
sampled tickets are genuine December filings by live-API timestamp, and
Stage B correctly drops every one. The rule is therefore structurally
unable to exercise the kept path (image fetch, hashing, scrape-stage
resume) that a dry run exists to validate before a full sweep. The same
would happen from the tail (248 April-pad rows). This amendment adds one
supplementary rule; it does not change the locked selection rule of §2 in
any way.

## The rule

**Stride sample**: over the committed Stage-A manifest in its deterministic
order, take indices `k × ⌊len(candidates) / N⌋` for `k = 0 … N−1`
(N = 50 default). On today's manifest of 17,137 candidates that is every
342nd row — a content-blind positional spread across the whole padded
window. No category, ward, status or outcome ever influences membership;
the rule is computed from list position alone and stated here before the
run it governs.

## What this sample is, and what it must never be cited as

This is a **mechanism-validation sample**, not a statistical sample. It
exists to prove the machinery works end-to-end on kept tickets. It MUST
NOT be cited as evidence about Q1 prevalence, drop rates, ward or category
distributions, or any other substantive property of the window — stride
positions correlate with filing time, and N is far too small for any rate
claim. Detection thresholds tuned against it inherit the same restriction,
mirroring the Stage 4/7 rule that precision does not transfer.

## Containment

- Outputs stay in `probe/out/dryrun/` (gitignored), as sibling files
  (`journal_stride.jsonl`, `hashes_stride.jsonl`, `summary_stride.json`);
  nothing from a stride run ever enters `data/`.
- Request budget: bounded by the same Phase 1 ceiling — at most ~N × 4.5
  additional requests, drawn from the same global 3-second limiter.
- The recorded first-N rule remains the default mode and the reference
  dry run; stride runs are labelled `--sample stride` and their logs name
  Amendment C.


# Amendment D — 2026-08-26 (approved): image-presence expectations re-measured on the locked vintage

Status: maintainer-approved. The ceiling row of §6 is unchanged. The
per-kept-ticket figure below is an **engineering expectation derived from a
mechanism-validation sample** (Amendment C): it comes from 49 kept tickets
and must not harden into a measured rate.

## Measurement

Exhaustive verification over every kept ticket of the stride sample that
produced no hashable image (16 with no URL + 3 whose single URL failed at
object level), by fresh raw-payload refetch:

- All 16 no-URL payloads carry `ImagePath` and `StaffRecentAddedImage` as
  **present-but-empty strings server-side**, with no other URL-bearing key
  in either block; adapter-vs-payload diff: 0 extracted vs 0 present,
  MATCH on all 19 tickets, mismatches zero.
- Fully-hashed control tickets prove extraction correctness end-to-end on
  the same vintage.
- Presence among 49 kept tickets: staff photo **26/49 (53%)**, citizen
  photo **10/49 (20%)**, neither **16/49 (33%)**. Hashed yield
  **0.73 images/kept** (attempted 0.80).
- The earlier sampling's staff ~85% / citizen ~40% does not hold on
  Q1-2025 filings. Vintage drift and storage-side retention decay cannot
  be separated from inside this corpus; any published methodology note
  says so.

## Consequences for §6

- Expected requests become 17,137 + 16,747 × 0.75 ≈ **29,700**
  (limiter floor ≈ 24.8 h). The 4.5-per-candidate worst-case ceiling row
  stands unchanged.
- **The sweep shortening is NOT efficiency.** Roughly **12,200 images
  reach the headline check instead of ~21,000**, and pHash candidate pairs
  shrink faster than image count does (pair-count scales roughly with the
  square of per-ward corpus depth). Stage 4 precision must be read against
  that thinner corpus, and published next to its numbers.

# Amendment E — 2026-08-26 (maintainer ruling): fast-closure check retired on this corpus

Check 3 (time-to-close from staff-photo filename timestamps) is RETIRED
for the locked window; the Stage 3 ladder in CLAUDE.md is reduced to
recycled-image (headline), obstructed-lens (secondary), aged-open
(backlog).

## Why

Every staff-photo filename observed on the Q1-2025 vintage carries a
**packed digit timestamp** (`202511095856STAFF…`) — zero instances of the
space-separated grammar the existing parser requires. Recovering a
timestamp from packed digits by choosing among candidate splits using each
ticket's API filing time is PROHIBITED: check 3 measures closure relative
to filing, so filing-guided disambiguation selects the parses that produce
plausible time-to-close values and then reports them as findings about
filing. A plausibility-biased parse rule suppresses exactly the signal
the check hunts.

## Filing-blind exception, tested and measured

A deterministic rule that never references filing timestamps DOES exist:
fixed 4-digit year, then exhaustively enumerated unpadded month/day/hour/
minute[/second] widths, calendar-validated; a filename is usable only when
EXACTLY ONE distinct valid datetime exists, otherwise dropped. Measured on
the stride corpus's stored URLs:

| surface | usable | ambiguous (dropped) | other |
|---|---|---|---|
| staff filenames | 6/22 (**27%**) | 16 | 0 |
| citizen filenames | 5/14 | 1 | 8 uuid-style, no timestamp run |

Disposition: the rule is **not wired into any runtime**. Combined with
53% staff presence, it would feed roughly one in seven kept tickets — too
thin to carry a published check, and unambiguity correlates with digit
shape, biasing whatever residue remains. If Stage 4 analysis ever consults
filename timestamps as corroboration, it uses THIS rule only, and
publishes its drop rate beside any number it touches. For the locked
window, check 3 records as inputless-by-ruling, not zero-inputs-by-data.

---

# Amendment F — 2026-08-26: Phase 1 executes locally; free-CI sweep retired

Measured basis: docs/stage0-report.md Addendum 3 — three CI batches failed
identically on `httpx.ReadTimeout` from Actions runners (SurfaceGuard halt,
§9.6, working as designed) while the residential vantage sustained a
~900-request local batch cleanly. Item 7's one-GET-per-host probe could not
see this; sustained access is a different measurement and it is
vantage-bound.

Rules:

1. **All Phase 1 sweeping runs locally**, resumed from checkpoint 1
   (8614ece), in bounded batches (`--max-requests`) with a checkpoint commit
   between batches. The journal + hashes.jsonl make every interruption
   exact-once resumable; the failed CI runs' ~1,800–3,700 uncheckpointed
   requests are simply re-decided.
2. **`phase1-sweep.yml` loses its push trigger** (dispatch-only, not
   dispatched): with CI unusable for sweeps, every workflow-file edit used
   to auto-burn a doomed batch from a blocked vantage. The if:always()
   self-publishing fix stays — it was the right fix for the wrong diagnosis.
3. **Forkability consequence carried to Stage 6/README:** the adapter
   contract gains a declared vantage requirement per city; a forking group
   must run its sweep from a residential connection against portal families
   that behave like this one. The stack spec's "GitHub Actions cron" line is
   annotated accordingly in CLAUDE.md.
4. Request-budget planning figures (§6, as amended) are unchanged; only the
   execution venue moves.
