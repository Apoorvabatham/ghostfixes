# Citizen-photo EXIF measurement — Sahaaya surfaces (Stage 1 gate addendum)

**Date:** 2026-08-25 (late session) · **Script:** `probe/exif_citizen_probe.py` ·
**Raw aggregates:** `probe/out/citizen_exif_summary.json` (gitignored)

Question posed by the maintainer: if citizen complaint photos carry GPS EXIF,
that supplies the sub-ward locator check 1 has been missing, and combined with
the staff-filename resolution timestamps both halves of check 1 would exist.
This file records the field-level measurement. Per instruction, the
option-2-vs-option-3 choice is **not** made here.

Method unchanged from Stage 0: unauthenticated GETs only; hard global
1-request-per-3-second limiter; project User-Agent; ticket IDs verbatim from
BBMP's own published CSV (two deliberately distant windows of the 2024
resource — one contiguous-ID cluster per window — 45 Closed garbage tickets).
Detail payloads were filtered in memory against an explicit whitelist
(Address, Description, StaffName, ContactDetails, StaffRemarks never
persisted or printed); photos were held in the job tmp dir, read by exiftool,
and deleted immediately; no image and no raw coordinate was persisted or
printed anywhere — only presence counts, delta statistics, and bounding-box
containment classes.

## Where citizen photos live (three hosts, two generations)

`ImagePath` values observed across the cohort: legacy dotted host
`sahaaya2.bbmp.gov.in/Admin|Webapi/ProjectImages/…` (9), one-word host
`sahaaya2.bbmpgov.in` (3), and `nammabengaluru.s3.ap-south-1.amazonaws.com/
Sahaaya-Stg/Grievance/Images/<id>_<suffix>_<epoch-ms>.jpg` (10). The legacy
paths serve server-resized thumbnails (~36 KB median); the S3 paths serve
near-original camera files (~2.1 MB median, up to 4032×3024).

## Field-level EXIF survival (22 citizen photos measured)

| tag group | S3 originals (n=10) | legacy resized (n=12) |
|---|---|---|
| DateTimeOriginal / CreateDate | 8/10 | 2/12 |
| OffsetTimeOriginal (UTC offset) | 4/10 | 1/12 |
| Make + Model | 6/10 | 1/12 |
| Software / CreatorTool | 2/10 | 0/12 |
| embedded thumbnail (IFD1) | 6/10 | 0/12 |
| GPS latitude + longitude | **1/10** | **1/12** |

Six distinct devices appear among S3 originals (Samsung Note10+, iPhone 6s
Plus, four OnePlus models). Both GPS-bearing images fall inside the Bengaluru
bounding box and carry altitude. Nominal string precision is 13 decimal
digits — a value with no physical meaning at that scale; positional accuracy
cannot be established from metadata alone.

Presence-pattern inference (labelled as inference): S3 originals retain
camera, timezone, XMP and thumbnail metadata broadly while lacking GPS in 9
of 10 cases — consistent with deliberate location-tag removal on upload
rather than blanket EXIF stripping. The 2 leaks (≈9% overall) show citizen
devices do geotag when the strip does not fire.

## Capture time vs recorded filing second

Using the API's second-precision `GrievanceDate` as reference:

- S3 originals: n=8 parsed; photo-timestamp minus filing ∈ [−1650.7,
  −1.1] minutes; median −17.2 min; negative in 8/8 cases (capture precedes
  the recorded filing moment). Magnitudes are the publishable fact; device
  clock skew is an unquantified confounder.
- Legacy: n=2 parsed; −31.8 and −1.1 minutes; same sign pattern.
- Legacy CITIZEN *filenames* decode to −1.1..0.0 min vs filing (n=3): the
  filename moment ≈ the filing moment.

## Staff-side contrast (fresh cohort, same session)

- `staffComplaintDetails` populated for **41/45** tickets once extraction
  matched the payload shape (the block sits beside the ticket object at top
  level, not inside it) — consistent with the memo's 17/20.
- Staff photos fetched keyless: 4/4 carry **zero** EXIF tags of any group —
  memo §2 re-confirmed on new data.
- Staff filenames: strict parser handled 1/4 (+30163 min ≈ 21 days after
  filing; within §4b's observed range). Parser limitation noted (seconds can
  run straight into id digits); not claimed as a data finding.

## Publisher-side data-quality finding (material to any TTC math)

Same-ticket filing timestamp, published CSV vs live API:
33/45 equal within 2 minutes; **12/45 differ by exactly 12 h ±5 min**; 0
other. The open dataset carries a 12-hour shift on ~27% of this cohort —
consistent with an AM/PM-boundary artifact in their export. Any closure-time
arithmetic anchored on CSV timestamps inherits this; API timestamps are
internally consistent with photo and filename artifacts.

## Endpoint access observations (facts, not conclusions)

- The S3 bucket served all 10 sampled objects keyless this pass; earlier the
  same session two genuine-path objects returned 403 and one `ImagePath`
  held the literal string `null`. Public/private mix or deleted-object state
  cannot be distinguished from inside the sandbox.
- S3 responses carried no `Content-Type` header (observation only).
- The legacy host still requires the established loose-TLS fallback.

## `ipgrs.karnataka.gov.in` fresh-session retry

HTTPS and plain HTTP both time out (25 s, zero bytes received) while the
control host answers 200 in under a second through the same egress, with the
allowlist entry present in this session. Signature identical to
`api.bbmpgov.in`. Finding unchanged: unreachable, cause undeterminable from
inside the sandbox; nothing is concluded about Janaspandana itself.

## Gate arithmetic after this measurement

- **Closure/resolution moment:** computable for the staff-imaged subset via
  staff-filename timestamps (memo §4b) — staff block present 41/45, staff
  photos confirmed EXIF-free, so the filename remains the only resolution
  moment available.
- **Sub-ward location:** still supplied by no systematic source. GPS
  survival is ~9% overall and leak-shaped; it cannot power check 1's location
  half at scale. `Address` is free text excluded from storage by invariant 1
  regardless.
- **What EXIF newly supplies:** citizen capture timestamps (8/10) and device
  identity (6/10) on the S3-original subset — corroboration inputs for
  ladder checks 2–3, not a location source for check 1.

Both remaining options of CLAUDE.md §Stage 1 stay open, now against these
sharpened facts.
