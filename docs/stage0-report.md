# Stage 0 feasibility probe — report

**Date:** 2026-08-24 · **Script:** `probe/probe.py` · **Raw evidence:** `probe/out/` (gitignored)

Method: unauthenticated GETs only; global 1-request-per-3-second limiter;
`User-Agent: GhostFixes/0.0-stage0 (+https://github.com/Apoorvabatham/ghostfixes;
contact: apba00001@uni-saarland.de)` on every request. No ticket-ID guessing or
enumeration: exactly one lookup used a real ID, taken verbatim from BBMP's own
published open dataset. Raw page bodies stay in `probe/out/`; console output
showed structure only (invariant 1). Scope covered both candidate cities
(Delhi MCD, Bengaluru GBA/BBMP).

---

## 1. Sanctioned API?

**Delhi — no.** On `mcdonline.nic.in`: `/robots.txt`, `/open311/v2/discovery.json`,
`/georeport/v2/discovery.json`, `/georeport/v2/requests.json` → 404.
`/api/v2/discovery.json` and `/api/v2/` → **403**, JSON body
`{"status":403,"message":"Forbidden"}` — an application-level rejection, not an
HTML WAF page. An API gateway exists but refuses unauthenticated access. Per
invariant 4, that is an answer, not an obstacle.

**Bengaluru — base URL known, host unreachable.** The public `bbmp.gov.in` React
bundle names its API base: `https://api.bbmpgov.in/gba/v1`. Note the domain:
`bbmpgov.in` (one word), distinct from the allowlisted `bbmp.gov.in`. Requests
still fail at our egress proxy (502 after CONNECT) even after the allowlist
request — so either the entry needs correcting or the running session predates
it. Recorded honestly as *sandbox-refused*, not as portal behaviour.

## 2. Is the data already published?

**Yes, for Bengaluru.** `data.opencity.in` (CKAN) hosts **`bbmp-grievances-data`**:
six yearly CSVs, 2020–2025, ~767k rows (91,620 / 103,504 / 118,394 / 119,140 /
207,016 / 126,974); metadata last modified 2025-11-27; update cadence unknown.
Fields: `Complaint ID`, `Category`, `Sub Category`, `Grievance Date`,
`Ward Name`, `Grievance Status`, `Staff Remarks`, `Staff Name`. Target category
present (*Solid Waste (Garbage) Related → Garbage dump*). IDs are plain integers,
timestamped to the minute.

What it does **not** contain — decisive for the detection ladder:

- **No resolution/closure timestamp** (one date per record only).
- **No location finer than ward**, no coordinates.
- **No image references whatsoever.**

Adjacent datasets (`bbmp-fix-my-street-data` May–Jun 2022 potholes;
pothole-filling PDF updates) are context, not pipeline inputs. Delhi publishes no
equivalent bulk grievance dataset there.

## 3. Logged-out visibility of closed tickets

**Delhi: publicly linked pages exist; ticket content does not reach them
lawfully for us.** The MCD 311 system lives on the vendor domain
`mcd.everythingcivic.com` (React SPA; both `/citizen/createissue` and
`/citizen/issuedetail` are linked straight off `mcdonline.nic.in/portal`, each a
672-byte shell around bundle `main.5ecd4fb8.js`). The bundle shows how it works:
`app_id` (encrypted) + `api_key` come from the page URL, get stored client-side,
and an axios interceptor attaches `app_id`/`api_key` headers to **every** call to
`https://api-admin.everythingcivic.com/api/v1/` (Rails-style routes such as
`citizen_issue/index`, `complaint_dashboard/issue_details`). Reproducing those
calls means reusing embedded URL credentials against a backend — exactly what
invariant 4 forbids — and no public list of Delhi ticket IDs exists to build
detail URLs from anyway. So: no sanctioned route to Delhi ticket detail pages,
even though a citizen holding their own link presumably sees theirs logged out.

**Bengaluru: no logged-out citizen web view of Sahaaya grievances was found.**
`sahaaya2.bbmp.gov.in` is live but is the officials-only app ("GBA Officials
Application", username/password WebForms). `support.bbmpgov.in/ehelpline/`
offers a genuinely public logged-out ticket search (`CitizensSearchTickets.aspx`,
WebForms round-trip verified working) — but it serves **e-khata support tickets**,
a different system: a real published Sahaaya complaint number returns "No ticket
found with this number!". Whether the Sahaaya app's own status view has a web
equivalent would live behind `api.bbmpgov.in` — unreachable from here.

## 4. Direct image fetch without a session

**Untestable — and that is itself the finding.** Zero resolution-photo URLs were
obtainable through any sanctioned path on either city: the open dataset carries
no image fields, and no reachable page exposed one. Until a public per-ticket
surface appears, the image half of the project (recycled-image, obstructed-lens,
EXIF checks; archived proof links) has **no input source**.

## 5. JSON behind the page, or `__VIEWSTATE`?

| Surface | Tech | Data path |
|---|---|---|
| `bbmp.gov.in` (GBA portal) | React SPA | JSON API `api.bbmpgov.in/gba/v1` |
| `sahaaya2.bbmp.gov.in` | ASP.NET WebForms | `__VIEWSTATE` + `__EVENTVALIDATION` (officials-only) |
| `support.bbmpgov.in/ehelpline` | ASP.NET WebForms | POST-back search, works without JS |
| `mcdonline.nic.in/portal` | server-rendered HTML (~3.9 MB, no VIEWSTATE) | links 311 out to the vendor |
| `mcd.everythingcivic.com` | React SPA | JSON API `api-admin.everythingcivic.com/api/v1/` (key-headered) |
| `mcdonline.nic.in/esbm-mcd/...PublicConsole` | JS dashboard | ajax — sanitation-vehicle routes, not grievances |

## 6. EXIF survival

Untested — dependent on item 4 producing even one legitimate photo URL. Nothing
can be claimed.

## 7. Foreign IP (GitHub Actions runner)

Local baseline captured in `probe/out/log.jsonl`. A one-shot workflow
(`.github/workflows/stage0-reachability.yml`) is written and committed-ready but
**the push was rejected**: the stored PAT lacks the `workflow` scope. Item 7
stays open until the token gains that scope or the workflow is pushed another
way.

---

## Bottom line

For **Bengaluru**, a sanctioned, publicly published metadata corpus exists
(767k rows, six years) and nothing blocks ingesting it. But:

- **Check 1 (re-complaint rate) as specified is not computable** from any source
  reached in this probe: the dataset has no closure timestamps, and no reachable
  public source supplies them (per the Stage 1 gate added to CLAUDE.md, this
  must be resolved or the metric explicitly redefined/demoted *in writing*
  before Stage 2).
- **Checks 2–4 and the proof-link architecture have no input at all**: no
  images are reachable through any sanctioned path, for either city.
- Delhi is worse on every axis: no bulk publication, no sanctioned detail-page
  access (vendor API keyed), no public ID list.

Per the Stage 0 gate: **stop here.** Nothing beyond `probe/` and this report has
been built. The decision this report forces — which city/category survives when
the headline check is uncomputable and the image layer is starved, or whether
the honest answer is option 3 ("the data does not support the central metric")
— belongs to the maintainer before Stage 1 scope lock.

## Blockers requiring the maintainer

1. ~~Allowlist~~ **resolved 2026-08-25** — see addendum below. Note that
   `api.bbmpgov.in` now fails *past* the allowlist (gateway-level), which is a
   separate, portal-side question.
2. Push token lacks GitHub `workflow` scope → item 7 workflow cannot be pushed;
   `.github/workflows/stage0-reachability.yml` left in the working tree, push
   retried when the scope is granted.
3. Decision on the Stage 1 gate: closure dates and sub-ward locations exist on
   no reachable source; see `docs/stage1-gate.md` for the live state of that
   question and the decision rule once the last candidate source is testable.

---

# Addendum — 2026-08-25 rerun (allowlist restored)

Session restarted after `settings.local.json` was rewritten mid-session lost
the new entries. Restored families: `bbmpgov.in`, `*.bbmpgov.in`,
`everythingcivic.com`, `*.everythingcivic.com`. Phases `p5a–p7b` re-ran Stage 0
items 3–6 against every now-reachable host. Method unchanged (same limiter,
UA, link-following discipline); two additions: one keyless empty POST against
the Delhi vendor API, and first-ever fetches of the `bbmpgov.in` apex.

## What changed per question

**Item 1 (sanctioned API).** `api.bbmpgov.in/gba/v1` — named by the GBA bundle,
unchanged since yesterday's capture (`main.b20559ca.js`, same config) — returns
a gateway **502 on both http and https across all probed paths**, while family
hosts through the *same egress* succeed (`updates.bbmpgov.in` 200, apex
`bbmpgov.in` 200). So this is **not an allowlist block**: origin down, DNS gap,
or geo-fence — indistinguishable from inside the sandbox, recorded as
"unreachable, cause undetermined". Open311 discovery paths on it remain
untestable.

**Item 3 (logged-out visibility).**
- *Delhi — definitively closed.* `api-admin.everythingcivic.com/api/v1/`
  keyless → 404 Laravel route-not-found; `/citizen_issue/index` GET keyless →
  405 "Supported methods: POST"; one keyless empty POST → **401 "Access denied,
  your session is expired"**. A real auth middleware sits in front of every
  route, and replaying the page-embedded `app_id`/`api_key` is forbidden by
  invariant 4. No sanctioned access route exists — measured, not assumed.
- *Bengaluru — unchanged, and now precisely bounded.* Every allowed surface is
  exhausted: ehelpline search fronts only the e-Khata system ("Ekata helpline";
  published Sahaaya IDs return not-found), `sahaaya2.bbmp.gov.in` is the
  officials' login, the GBA portal is static, `updates.bbmpgov.in/public` is a
  news CMS (DataTables over server-rendered rows, admin edit stubs, no JSON),
  and the `bbmpgov.in` apex is a **GoDaddy parked page**. The portal itself
  points citizens at **`https://nammabengaluru.org.in/login`** ("SAHAAYA 2.0
  · Public Grievance") — the actual citizen face of the system behind the
  published dataset — and that host is **off the allowlist**. Whether it offers
  any logged-out per-ticket view (its entry URL is literally `/login`, a poor
  sign) is therefore unknown, not negative.
- TLS note: verified-TLS against `support.bbmpgov.in` fails with "unable to get
  local issuer certificate" while other family hosts verify cleanly — an
  incomplete chain served by the portal, confirming last session's
  `verify=False` fallback was necessary and is a property of their infra.

**Items 4 & 6 (images / EXIF).** Still zero legitimate resolution-photo URLs
obtainable from any allowed surface. Both remain untestable, and both now have
exactly one remaining candidate source: the Sahaaya 2.0 citizen portal.

**Item 5 (JSON vs VIEWSTATE).** Table additions: everythingcivic backend =
Laravel JSON API behind auth middleware; GBA SPA → currently-unreachable API
host; updates host = server-rendered HTML + DataTables; apex = parked.

**Housekeeping.** Raw page `mcd_portal.html` (last session, gitignored) held 39
Indian-mobile-pattern matches; deleted under invariant 1. New saves this
session were audited: none contain phone/email patterns.

## Gate-relevant fields after the rerun

- **Closure/resolution timestamp: supplied by no reachable source.**
- **Location finer than ward: supplied by no reachable source.**

Check 1 remains uncomputable on currently-reachable sources. Per the user's
instruction this is reported before any proposal to proceed on image checks
alone; the single remaining candidate source has been requested through the
allowlist procedure instead of concluded about.

## Updated blockers / asks

1. **Domain request:** `nammabengaluru.org.in` and `*.nammabengaluru.org.in` —
   the citizen Sahaaya 2.0 web portal (linked from the official GBA portal);
   sole remaining candidate for closure dates, sub-ward location, and
   resolution-photo URLs. Secondary, optional, same rationale:
   `ipgrs.karnataka.gov.in` (state "Janaspandana" grievance portal, linked from
   the GBA portal). Also whatever API host the Sahaaya bundle names once seen.
2. Workflow-file push still awaits PAT `workflow` scope.
3. `api.bbmpgov.in` gateway failure is portal-side; nothing further actionable
   from here unless it starts answering.

---

# Addendum 2 — 2026-08-25 (later): Actions-runner reachability measured; keyless archiving validated

## Item 7, round 1 — run 32795730414 (workflow pushed by maintainer as 9a14d81)

Results reported by the maintainer from the Actions run (the repository is
private, so runs are not readable from this sandbox — recorded as an access
fact, not worked around):

| Host | Local sandbox | Actions runner |
|---|---|---|
| `sahaaya2.bbmp.gov.in` | 200 | **200** |
| `data.opencity.in` | 200 | **200** |
| `mcdonline.nic.in` | 200 | **200** (9.7 s — slow but answering) |
| `bbmp.gov.in` | 200 | **000 — connection failed** |

**Conclusion:** both hosts the Stage 1 sweep depends on answer from Actions
runners, so the free-runner execution plan is viable and checkpoint/resume is
worth building. The `bbmp.gov.in` flip (works locally, fails from the runner)
is the cautionary case: **these hosts treat datacenter IPs differently, and no
200 generalizes from one network to the other.** Every future reachability
claim must state which vantage point it was measured from.

### Item 7, round 2 — first attempt died at parse; repaired workflow self-publishes

Run 32796402468 failed at startup with zero jobs: YAML parse error. In
`.github/workflows/stage0-reachability.yml`, the heredoc body and terminator
sat at column 0 inside the `run: |` block scalar, so the terminator ended the
scalar itself and YAML met URL lines where top-level keys belong. Repaired in
fca6099: host lists became multi-line shell variables (no heredocs anywhere
in the file), all seven hosts probe in one pass from one vantage, and
pre-push validation (`safe_load` + `bash -n` on the extracted script) now
precedes every workflow change.

Delivery mode changed at the same time: maintainer paste is retired. The
runner appends its results table to `docs/actions-reachability.md`
(job-level `permissions: contents: write`) and pushes; results arrive by
`git pull`. This is the mandatory pattern for all future CI output. Round-2
codes will be recorded here from that file when the repaired run lands.

## Archiving mechanism — both Stage 2 archive decisions validated keyless

Measured against one sample ticket detail URL (`ComaplaintID=20446742`, taken
verbatim from BBMP's own published dataset, consistent with prior probes):

- **Decision (a), submit at capture time: WORKS WITHOUT AN ACCOUNT.**
  Anonymous Save Page Now (`GET web.archive.org/save/<url>`) returned
  **HTTP 200 in 77.7 s**, blocking until capture completed. This matters
  doubly: an account-based SPN2 token would violate the no-accounts
  constraint, so the keyless path is the only sanctioned one — and it exists.
- **Decision (b), link snapshots not live pages: VERIFIED.** CDX lists the
  fresh capture (`20260825011108`, origin statuscode 200, digest
  `4O2FA6SVREKHAQMZU4CKHAIKO7DFMXSU`); the canonical
  `web.archive.org/web/<timestamp>/<url>` form resolves HTTP 200 (<1 s).
  CDX mimetype is listed as `application/xml` for the JSON body — recorded as
  observed, uninterpreted; digest comparison remains available if ever needed.
- CDX verification query: 27.2 s. Treat as sampled spot-check material, not a
  per-ticket step.
- **Budget impact (material):** a blocking save costs ~78 s wall clock per
  ticket. Serialized into the scrape loop this dominates everything else
  (~16,747 tickets × ~81 s ≈ 16 days). Consequence recorded as **Amendment A**
  in `docs/stage1-scope-lock.md`: two-phase sweep — fast scrape phase first,
  archiving as a separate resumable phase with staggered starts. (Phase 2
  was later voided without ever running — see Amendment B in
  `docs/stage1-scope-lock.md`.)
- **Permanence note (flagged for maintainer sign-off before sweep-scale
  use):** the archived artifact is BBMP's own keyless JSON and contains
  whatever BBMP publishes there (address, staff name fields) — fields this
  project never stores or displays. Archiving makes them permanent and public
  elsewhere even if BBMP deletes them. That durability is the tamper-evidence
  rationale, but it is irreversible; sign-off requested before Phase 2 runs at
  scale. One URL is already archived as the mechanism validation above.

**Resolution (2026-08-25, later): DECLINED at any scale — Amendment B.** The
maintainer confirmed the flag as decisive: per-ticket saves would permanently
publish invariant-1 fields (Address, Description, StaffName, ContactDetails)
for ~16,747 citizens, irreversibly, with this project as the cause;
keyless-and-unindexed is not public. Amendment B in
`docs/stage1-scope-lock.md` voids Phase 2 and all per-ticket and image-URL
archiving; only the six source CSVs get archived, once. The single
mechanism-validation snapshot above (`ComaplaintID=20446742`) cannot be
deleted through any sanctioned keyless route — recorded as irreversible, and
as the reason the decision could not wait for scale.

## Blocker list, updated

1. ~~Push token lacks GitHub `workflow` scope~~ **resolved** — workflow pushes
   now accepted (28ff0a6).
2. ~~Actions reachability unknown~~ **answered for round 1** (table above);
   round 2 awaits the repaired workflow (fca6099) — results land via
   `git pull` into `docs/actions-reachability.md`.
3. `api.bbmpgov.in` gateway failure: unchanged, portal-side, not actionable
   from here.
4. ~~Repository privacy means run logs are unreadable from this sandbox~~
   paste mode retired 2026-08-25: CI jobs self-publish their outputs by
   committing them under `docs/` (job-level `contents: write`) and results
   arrive via `git pull`. Mandatory pattern for all future CI output.
