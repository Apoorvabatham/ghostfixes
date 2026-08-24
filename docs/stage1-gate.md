# Stage 1 gate — can any reachable source produce check 1?

**Status: OPEN — one candidate source requested, not yet reachable.**
Last examined 2026-08-25 (Stage 0 rerun, `probe/probe.py` phases p5a–p7b).

Check 1 (re-complaint rate) needs two things per CLAUDE.md §Stage 1: a
resolution/closure timestamp, and a location granularity finer than ward.
This file states, in writing, which reachable source supplies them.

## Sources examined

| Source | Closure ts | Sub-ward loc | Photos | Outcome |
|---|---|---|---|---|
| `data.opencity.in` `bbmp-grievances-data` (~767k rows, 2020–2025) | no | no (`Ward Name` only) | no | metadata corpus only |
| `support.bbmpgov.in/ehelpline/CitizensSearchTickets.aspx` | — | — | — | different system — e-Khata "Ekata helpline"; published Sahaaya IDs return not-found |
| `sahaaya2.bbmp.gov.in` | — | — | — | officials-only login ("GBA Officials Application") |
| `bbmp.gov.in` GBA portal | — | — | — | static info site; no tracking surface in bundle |
| `api.bbmpgov.in/gba/v1` | ? | ? | ? | **unreachable**: gateway 502 both schemes on every path, while family hosts serve 200 through the same proxy — not an allowlist block; cause undeterminable from inside the sandbox |
| `mcd.everythingcivic.com` + `api-admin.everythingcivic.com` (Delhi) | — | — | — | keyless: 404 / 405 / **401 "Access denied"**; keyed replay forbidden by invariant 4 → no sanctioned route |
| `updates.bbmpgov.in/public`, `bbmpgov.in` apex | — | — | — | news CMS with server-rendered rows / GoDaddy parked page |
| **`nammabengaluru.org.in`** (Sahaaya 2.0 citizen portal, linked from the GBA portal as the public grievance system) | ? | ? | ? | **off the allowlist — requested 2026-08-25, not yet reachable from this sandbox.** Entry URL is `/login`; companion Android app `com.nammabengaluruNew.org`. Capabilities unknown. |

## Current answer

**No reachable source supplies a closure/resolution timestamp or a sub-ward
location.** On present reachability, check 1 as specified is not computable,
for Bengaluru or any other city examined.

Consistent with §Stage 1 and the maintainer's instruction, nothing is being
quietly redefined to fit the data, and no proposal to proceed on image checks
alone is being made. The single remaining candidate source has been requested
through the allowlist procedure first; declaring option 3 before testing it
would be premature, and proceeding without it would be indefensible.

## Decision rule once `nammabengaluru.org.in` is reachable

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
