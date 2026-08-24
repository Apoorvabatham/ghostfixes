# Stage 0 feasibility probe — report (interim)

**Date:** 2026-08-24 · **Script:** `probe/probe.py` (throwaway) · **Raw evidence:** `probe/out/` (gitignored)

Method: unauthenticated GETs only, global 1-request-per-3-seconds limiter,
`User-Agent: GhostFixes/0.0-stage0 (+https://github.com/Apoorvabatham/ghostfixes;
contact: apba00001@uni-saarland.de)` on every request. No ticket IDs guessed or
enumerated: the only ticket identifiers touched came from BBMP's own published
open dataset. Scope covered both candidate cities (Delhi MCD, Bengaluru GBA/BBMP).

---

## 1. Sanctioned API?

**Delhi MCD — no.** On `mcdonline.nic.in`: `/robots.txt` → 404; the standard
Open311 paths `/open311/v2/discovery.json`, `/georeport/v2/discovery.json`,
`/georeport/v2/requests.json` → **404**. `/api/v2/discovery.json` and `/api/v2/`
→ **403** with JSON body `{"status":403,"message":"Forbidden"}` (application/json,
Apache). That is an application-level rejection, not an HTML WAF page: an API
gateway exists but refuses unauthenticated access. Per invariant 4 this is an
answer, not an obstacle.

**Bengaluru — found but unreachable.** The public `bbmp.gov.in` SPA bundle names
its API base: `https://api.bbmpgov.in/gba/v1`. Note that host is under
`bbmpgov.in` (one word), which is a *different* domain family from the allowlisted
`bbmp.gov.in`. Requests to it fail at the sandbox proxy (502), so its capabilities
are unknown — not "denied by the portal," just not yet reachable from this sandbox.

## 2. Is the data already published?

**Yes, substantially — for Bengaluru.** `data.opencity.in` (CKAN) hosts
**`bbmp-grievances-data`**: six yearly CSVs, 2020–2025, ~767,000 rows total
(2024 is the largest at ~207k rows; metadata last modified 2025-11-27).
Fields: `Complaint ID`, `Category`, `Sub Category`, `Grievance Date`,
`Ward Name`, `Grievance Status`, `Staff Remarks`, `Staff Name`.
Sample row (sanitised): complaint `20771690`, Category *Electrical / Street Light
Not Working*, Ward *Jagajeevanram Nagar*, status *Registered*, timestamped to the
minute. Target category exists: *Solid Waste (Garbage) Related → Garbage dump*.

What this dataset does **not** give us:

- **One date per record.** No resolution/closure timestamp → the headline
  re-complaint metric (re-filed within N days of being marked resolved) cannot be
  computed from this file alone.
- **No coordinates** — ward granularity only.
- **No image references** — EXIF, recycled-image and obstructed-lens checks are
  impossible from this source.
- **Staff Name / Staff Remarks** are present; treat as PII-adjacent per invariant 1
  until classified.
- Update cadence unknown (files end with 2025; whether 2026 arrives is open).

Adjacent datasets (`bbmp-fix-my-street-data`, May–Jun 2022 pothole KML+CSV;
pothole-filling PDF updates) are context, not pipeline inputs.

For Delhi: no equivalent bulk publication was found on data.opencity.in.

## 3. Logged-out visibility of closed tickets + photos

**Unresolved — blocked on sandbox allowlist, not on portal answers.**

- Delhi: the MCD 311 grievance system is hosted on the vendor domain
  **`mcd.everythingcivic.com`** — `citizen/createissue` and `citizen/issuedetail`
  pages are linked directly from `mcdonline.nic.in/portal`, with `app_id`/`api_key`
  embedded in those public URLs. Per invariant 4 we fetch such URLs exactly as
  published, never reuse the embedded keys against any other backend endpoint.
  Domain not allowlisted → untested so far.
- Bengaluru: `sahaaya2.bbmp.gov.in` is live but is the **officials-only**
  application ("GBA Officials Application": username/password form, ASP.NET
  WebForms with `__VIEWSTATE`/`__EVENTVALIDATION`). Citizen-side tracking appears
  to be served from the Sahaaya app and/or `*.bbmpgov.in` hosts (unreachable).
  Whether a logged-out citizen web view of a closed ticket even exists is
  therefore still an open question — possibly the honest answer will be "no."

## 4. Direct image fetch without a session

Untested — no resolution-photo URL could be obtained from anything reachable
today (the open dataset carries none). Everything about the CV layer and
proof-link plan hinges on this once domains are reachable.

## 5. JSON behind the page, or `__VIEWSTATE`?

Mixed, per surface:

| Surface | Tech | Data path |
|---|---|---|
| `bbmp.gov.in` (GBA portal) | React SPA (CRA bundle) | JSON API at `api.bbmpgov.in/gba/v1` |
| `sahaaya2.bbmp.gov.in` | ASP.NET WebForms | `__VIEWSTATE` + `__EVENTVALIDATION` (officials-only anyway) |
| `mcdonline.nic.in/portal` | server-rendered HTML, ~3.9 MB, no VIEWSTATE | links out to vendor domain for 311 |
| `mcdonline.nic.in/esbm-mcd/...PublicConsole` | JS dashboard | ajax endpoints — but it monitors sanitation-vehicle routes, not grievances |

If Bengaluru's citizen tracking runs through `api.bbmpgov.in/gba/v1`, item 5
resolves to "target the JSON API." Delhi's vendor pages look query-param-driven;
unverified.

## 6. EXIF survival

Untested — depends entirely on obtaining real resolution-photo URLs (item 4).
Nothing can be claimed here yet.

## 7. Foreign IP (GitHub Actions runner)

Local baseline recorded in `probe/out/log.jsonl` (all requests above).
The Actions-runner comparison needs a pushed workflow run and has not been done;
pending user decision. Until then this question is open either way.

---

## Blockers requiring the user

1. **Allowlist additions** (per protocol: listed, purpose stated, then wait):
   - `bbmpgov.in` + `*.bbmpgov.in` — GBA API base (`api.`), public ehelpline
     ticket pages (`support.`), other citizen services. Needed for items 1, 3–6
     on Bengaluru.
   - `everythingcivic.com` + `*.everythingcivic.com` — MCD 311 vendor domain.
     Needed for items 3–6 on Delhi.
2. **Push a GitHub Actions reachability probe?** (item 7)
3. Whether to commit `probe/probe.py` + this report now.

## Status of the seven questions

| # | Question | Status |
|---|---|---|
| 1 | Sanctioned API | MCD: no (403/404). BBMP: API base found, unreachable |
| 2 | Data already published | **Yes (Bengaluru)** — 767k rows, 2020–25; no closure dates/images |
| 3 | Logged-out ticket visibility | Blocked on domains; sahaaya2 = officials-only |
| 4 | Direct image fetch | Untested (needs 3) |
| 5 | JSON vs VIEWSTATE | Answered per-surface (see table) |
| 6 | EXIF survival | Untested (needs 4) |
| 7 | Actions-runner reachability | Local baseline only; runner test pending |

**Stage 0 does not clear yet.** Item 2 alone would justify a Bengaluru-first scope
lock for the metadata layer, but items 3–6 decide the image half of the project
and remain open pending the domains above.
