# Stage 1 gate — can any reachable source produce check 1?

**Status: DECISION REQUESTED — every candidate source has now been measured.**
Check 1 (re-complaint rate) as specified remains **not computable**: no source
supplies a closure/resolution *field*, and location stays ward-level everywhere.
But the 2026-08-25 evening rerun measured two previously unknown surfaces
(a keyless per-ticket API on `sahaaya2.bbmpgov.in`, and prior CSV generations in
the Wayback Machine) and found that **resolution-moment timestamps are encoded in
staff-photo filenames**, which changes what a weakened metric could honestly be.
Sections 1–5 below are that assessment; §6 lists the maintainer's options.
Nothing proceeds to Stage 2 until this file records the outcome.

Last examined 2026-08-25 (evening rerun; the original memo is retained at the
bottom of this file for record).

---

## 1. Decision rule run against the newly allowlisted hosts

### `nammabengaluru.org.in` — reachable, measured, negative on both required fields

Angular SPA ("Namma Bengaluru"); `/login` and every path serve the same shell;
no `robots.txt`. Routes: `login`, `register`, `otp/verification`, `profile`,
`home`, `home/survekshanform`, `department/{form,list,view,bswml}` — a
**filing** app with no track/status route at all.

Bundle names three API bases:

| Base | Role | Notes |
|---|---|---|
| `https://sahaaya2.bbmp.gov.in/webapi/api` | Sahaaya backend | allowlisted family; measured below |
| `https://nammabengaluru.org.in/api/v1` | auth (`/auths/registeruser\|validateuser\|login`), `/departments/*` | OTP citizen session; not probed further |
| `https://bbmp.oasisweb.in/BBMPWEBAPItest/api/grievance` | legacy test API | host off allowlist; untouched |

**The keyless per-ticket endpoint.** `GET
sahaaya2.bbmp.gov.in/webapi/api/grievance/GetComplaintDetailforCitizen?ComaplaintID=<id>`
(their typo is part of the route) returns HTTP 200 with no session, no token,
no headers — the SPA itself calls it bare. Measured fields:
`GrievanceId`, `CategoryEnglish/Kannada`, `SubCategoryEnglish/Kannada`,
`GrievanceDate` (filing, minute precision), `Ward`, `Address`, `Description`,
`ImagePath`, `AudioPath`, `VideoPath`, `ComplaintStatus`, `Rating`; plus a
`staffComplaintDetails` block: `GrievanceStatus`, `StaffRemarks`,
`StaffName`, `ContactDetails`, `StaffRecentAddedImage`.

Gate-relevant verdict per decision-rule step 2/3:

- **Closure/resolution timestamp field: ABSENT** from the payload.
- **Sub-ward locator: ABSENT** for our purposes — `Ward` only; `Address` is
  free text that may contain house-level detail and is banned from storage by
  invariant 1 regardless.
- Sample of 20 published garbage/Closed IDs (Stage 0 precedent: IDs verbatim
  from BBMP's own dataset, one lookup each, PII filtered in memory):
  `ImagePath` populated 8/20, `StaffRecentAddedImage` populated **17/20**.
- Observed quirk: citizen side `Closed` while staff block says `Registered`
  on some tickets — the portal's own status fields disagree; recorded as an
  observable fact, uninterpreted.

### `ipgrs.karnataka.gov.in` — allowlisted but failing past the egress

HTTPS fails twice with proxy 502-after-CONNECT; plain HTTP times out; control
host `data.opencity.in` answers 200 through the same proxy seconds later.
Recorded per CLAUDE.md as **cause undeterminable from inside the sandbox**
(same signature as `api.bbmpgov.in`). Given the allowlist-reload failure mode
seen before (see memory note), retry in a fresh session before drawing any
conclusion about Janaspandana. No finding about the portal is claimed.

---

## 2. Stage 0 items 4 & 6 — reopened by the endpoint, split result

- **Item 4 (logged-out image fetch): YES for the staff surface.**
  `StaffRecentAddedImage` URLs live on
  `sahaaya2.bbmpgov.in/ProjectImages/GrievanceImages/<id>/…jpg` — fetched
  keyless, 200, `image/jpeg`.
  Caveat: the one-word domain serves a TLS cert that does not match it
  (same broken-chain property recorded for `support.bbmpgov.in`); probe used
  the established `-k` fallback.
  Citizen-side images live on
  `nammabengaluru.s3.ap-south-1.amazonaws.com` — **off allowlist**; recorded
  as *not yet reachable from this sandbox*, not as portal behavior.
- **Item 6 (EXIF): DEAD on the staff surface.** Sample photo has no APP1
  marker and zero EXIF tags (stripped server-side). Brightness mean/stddev
  remain computable (sample: 104.0/255, σ 56.5). Whether citizen S3 uploads
  retain EXIF is unknown until that host is allowlisted.

---

## 3. Prior versions of the open CSVs — obtainable, but carrying zero signal

Question posed by maintainer 2026-08-25: if successive versions of the yearly
CSVs are recoverable (CKAN revisions or Wayback), diffing yields which
Complaint IDs changed status and bounds when.

Measured answer:

1. **CKAN holds no priors.** Instance is CKAN 2.11.4; legacy revision actions
   return `400 Action name not known`. The dataset's complete activity stream
   is 14 events across 2025-11-25→27: creation batch (all six resources
   created == modified within seconds of each other), resource-view stubs,
   one metadata edit. The current generation began 2025-11-25.
2. **Wayback holds exactly one prior generation.** All six CSVs were captured
   2025-07-18…20 under the previous dataset UUID (`23116d73…`, friendly
   filenames `2020-grievances.csv` …). A domain-wide CDX sweep finds no other
   generation anywhere; the current files have never been archived.
3. **Diffing the pair yields nothing.** Both epochs of the 2024 file contain
   the identical 207,016 IDs with identical status histograms and **zero
   transitions** (every ID's `Grievance Status` identical between 2025-07-18
   and the 2025-11-25 re-upload). The November "re-upload" republished frozen
   exports.
4. **There is no publisher cadence.** One upload event total; the 2025 corpus
   ends at `Grievance Date` 2025-06-19 (DataStore max-date query); the
   DataStore has not moved since its Nov-25 load. At probe date the whole
   corpus is ~14 months stale, and tickets filed after 2025-06-19 are
   published nowhere we can lawfully reach (the portal has no public ticket
   list; discovering new IDs by pattern would violate invariant 4).

**Answer: priors are obtainable (one extra epoch per year) but the pair
differs in nothing — version-diffing this publisher cannot bound any closure
time, and no future cadence exists to wait for.**

---

## 4. Time-to-close as a check — assessment as requested

Definition under test: flag tickets whose closure is implausibly fast relative
to filing. Ticket-level, image-free, location-free by construction.

**4a. Via snapshot diffing — structurally sound, empirically empty.** With two
status observations at t₁<t₂, closure ∈ (t₁,t₂] and TTC ≥ t₁−filing is a
falsifiable fact about records — invariant 3 language satisfied (no persons,
no opinions, fully deterministic). But §3 measured the only recoverable pair
at zero transitions, and future epochs are unobtainable. Even at its
historical best the tightest certifiable bound comes from the boundary window:
tickets filed just before the 2025-06-19 freeze and already Closed in the
2025-07-18…20 captures certify TTC ≲ 29–31 days — nothing tighter exists in
all recoverable history, and ~30 days is not "implausibly fast".

**4b. Via artifact-encoded timestamps — measurable today, with stated limits.**
Staff resolution-photo filenames embed an unpadded timestamp
(`YYYY M D H M S`, verified against filing dates on six samples; every parse
lands after filing, most within hours–days):

| ticket | filed | filename-decoded action | implied TTC |
|---|---|---|---|
| 20446742 | 2024-01-27 05:00 | 2024-01-27 13:22 | ~8.4 h |
| 20481149 | 2024-04-23 07:52 | 2024-04-24 11:13 | ~27 h |
| 20524520 | 2024-07-05 11:16 | 2024-07-06 08:11 | ~21 h |
| 20573609 | 2024-09-16 10:35 | 2024-09-17 09:48 | ~23 h |
| 20595868 | 2024-10-20 21:39 | 2024-10-23 13:55 | ~2.7 d |
| 20437521 | 2024-01-01 00:05 | 2024-07-18 03:31 | ~199 d |

This makes time-to-close computable at minute level for the staff-imaged
subset (~17/20 sampled) of all 767k published tickets — including genuinely
fast closures — using only: filing timestamp (dataset), one keyless API call
per ticket, filename parsing. Invariant compliance of that pipeline shape:
inv 1 ✓ (no PII touched); inv 2 ✓ (deterministic parse + arithmetic);
inv 3 ✓ (publishable as e.g. "filed 2024-10-20T21:39, resolution artifact
named 20241023135557"); inv 4 ✓ (IDs verbatim from BBMP's own publication,
no guessing); inv 5 feasible only per-subset (full sweep = 767k × 3 s ≈ 26.6
days); inv 6 ✓ (no images need be stored to compute it).

Caveats that must sit next to any such number: filenames are generated by the
audited system itself (self-reported artifacts); the unpadded format needs
written disambiguation rules; coverage excludes tickets without staff images;
the corpus is frozen at 2025-06-19 so the population is historical; and
Stage 4 hand-labelling must measure precision before anything publishes.

**4c. Verdict.** Time-to-close satisfies invariant 3 and is genuinely
ticket-level/image-free/location-free. It is computable **only** via 4b's
artifact timestamps, only for a subset, only for a frozen population. It does
**not** rescue check 1: re-complaint rate still needs sub-ward location,
which no source supplies. It is a candidate *replacement* headline, not a
completion of the original one.

Adjacent signal, noted because it falls out of the same data: tickets still
`Registered`/`In Progress` after very long spans are computable without any
closure timestamp at all (the corpus freezes mid-life, so "still open at
freeze + N days" is a plain record fact). That measures backlog, not
anomalous closure — different phenomenon, maintainer's call whether it belongs
in scope.

---

## 5. What survives, in full

| Signal | Computable? | Needs |
|---|---|---|
| Check 1 re-complaint rate as specified | **No** — ward-only location, no closure field, on every source | a source that may not exist |
| TTC via snapshot diffing | No (empty priors, no cadence) | refreshed publisher exports |
| TTC via staff-photo filename timestamps | **Yes — subset, frozen corpus** | ~3 s/ticket sweeps; Stage 4 validation |
| Aged-open / never-closed | Yes | same sweep |
| Brightness/variance checks (ladder 4) | Likely yes (photos fetch keyless) | image fetches at scale |
| Recycled-image pHash (ladder 3) | Likely yes | same + BK-tree |
| EXIF mismatch (ladder 2) | Dead on staff surface; unknown on S3 | allowlist ask for the S3 host |

## 6. Maintainer decision requested (unchanged menu, sharper facts)

Per CLAUDE.md §Stage 1: option 2 (explicit weakened redefinition, demoted from
headline) or option 3 ("the data does not support the project's central
metric"). What is new since the last memo: the weakened candidate is no longer
vague — it is §4b's fast-closure register over staff-imaged closed tickets,
with precision to be measured in Stage 4 before publication. Option 3 remains
honest if the judgement is that a frozen corpus whose timestamps come from the
audited system's own artifacts cannot carry the project.

Re-open this gate if: opencity publishes refreshed exports (new diff epochs);
any public list of post-freeze ticket IDs appears; the S3 image host is
allowlisted and EXIF proves to survive there; or `ipgrs.karnataka.gov.in`
becomes reachable and exposes a public tracker with closure history.

---

## 7. Addendum — citizen-photo EXIF measured (2026-08-25 late)

The S3 image host was allowlisted and the last open question measured;
field-level results in `docs/citizen-exif-probe-2026-08-25.md`. One-line
result: S3-era citizen originals keep capture-time (8/10) and device (6/10)
EXIF, but GPS survives only ~9% overall (2/22, leak-shaped) — so it is **not**
a systematic sub-ward locator. Closure-moment half of check 1 stands (§4b;
staff blocks 41/45, staff photos still fully EXIF-free); the location half
remains unsupplied by any systematic source. Option 2 vs 3 remains open per
maintainer instruction. New publisher-side fact: the open CSV's filing minute
is shifted exactly 12 h on 12/45 sampled rows (AM/PM export artifact) —
material to any dataset-anchored TTC arithmetic.

---

# Original memo (pre-rerun, retained for record)

**Status then: OPEN — one candidate source requested, not yet reachable.**
Last examined 2026-08-25 (Stage 0 rerun, `probe/probe.py` phases p5a–p7b).

Check 1 (re-complaint rate) needs two things per CLAUDE.md §Stage 1: a
resolution/closure timestamp, and a location granularity finer than ward.
This file states, in writing, which reachable source supplies them.

## Sources examined

| Source | Closure ts | Sub-ward loc | Photos | Outcome |
|---|---|---|---|---|
| `data.opencity.in` `bbmp-grievances-data` (~767k rows, 2020–2025) | no | no (`Ward Name` only) | no | metadata corpus only |
| `support.bbmpgov.in/ehelpline/CitizensSearchTickets.aspx` | — | — | — | different system — e-Khata "Ekata helpline"; published Sahaaya IDs return not-found |
| `sahaaya2.bbmp.gov.in` | — | — | — | officials-only login ("GBA Officials Application") — superseded by §1 above: its `/webapi/api` surface answers keyless |
| `bbmp.gov.in` GBA portal | — | — | — | static info site; no tracking surface in bundle |
| `api.bbmpgov.in/gba/v1` | ? | ? | ? | **unreachable**: gateway 502 both schemes on every path, while family hosts serve 200 through the same proxy — not an allowlist block; cause undeterminable from inside the sandbox |
| `mcd.everythingcivic.com` + `api-admin.everythingcivic.com` (Delhi) | — | — | — | keyless: 404 / 405 / **401 "Access denied"**; keyed replay forbidden by invariant 4 → no sanctioned route |
| `updates.bbmpgov.in/public`, `bbmpgov.in` apex | — | — | — | news CMS with server-rendered rows / GoDaddy parked page |
| `nammabengaluru.org.in` (Sahaaya 2.0 citizen portal) | see §1 | see §1 | ImagePath present 8/20 | measured 2026-08-25 evening — negative on required fields, positive on images |

## Current answer (as originally written)

**No reachable source supplies a closure/resolution timestamp or a sub-ward
location.** On present reachability, check 1 as specified is not computable,
for Bengaluru or any other city examined.

Consistent with §Stage 1 and the maintainer's instruction, nothing is being
quietly redefined to fit the data, and no proposal to proceed on image checks
alone is being made. The single remaining candidate source has been requested
through the allowlist procedure first; declaring option 3 before testing it
would be premature, and proceeding without it would be indefensible.

## Decision rule once `nammabengaluru.org.in` is reachable (as originally written)

1. Run Stage 0 items 3–6 against it (and whatever API host its bundle names).
   Logged-out only; link-following discipline; no ID guessing.
2. If a logged-out ticket view exists carrying a status-history/closure
   timestamp plus any sub-ward locator (locality/street/lat-lng): record the
   exact field names here, and the Stage 1 lock proceeds on that basis — city
   Bengaluru/GBA, category garbage or potholes (never streetlights), with the
   open dataset as bulk corpus and this portal as the per-ticket source.
3. If it does not (login-walled, snapshot-only statuses, ward-only locations):
   the honest options are exactly those in CLAUDE.md §Stage 1 — option 2
   (explicit weakened redefinition, demoted from headline) or option 3 ("the
   data does not support the project's central metric"). That choice belongs to
   the maintainer, informed by a written statement here of precisely what the
   surviving evidence supports. Nothing proceeds to Stage 2 until this file
   records the outcome.

Executed this date; outcome in §1–§6 above.
