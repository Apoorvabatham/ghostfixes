#!/usr/bin/env python3
"""Stage 1 gate probe — EXIF survival on CITIZEN grievance photos (Sahaaya 2.0).

docs/stage1-gate.md left exactly one gate-relevant question open: staff-side
photos on sahaaya2 are EXIF-stripped server-side (memo §2), but citizen-side
photos are hosted separately (nammabengaluru.s3.ap-south-1.amazonaws.com),
which was unreachable when the memo was written. If citizen photos retain GPS
EXIF, a sub-ward locator exists for check 1; combined with the resolution
timestamps embedded in staff-photo filenames (memo §4b), both halves of
check 1 would be supplied. This script measures that and nothing else.

Method identical to Stage 0 (probe/probe.py): unauthenticated GETs only;
global hard 1-request-per-3-second limiter; honest User-Agent on every
request; ticket IDs taken verbatim from BBMP's own published open dataset
(no guessing, no enumeration — invariant 4).

PII discipline (invariant 1): the detail payload carries Address, StaffName,
ContactDetails, StaffRemarks, Description — filtered in memory against an
explicit whitelist and NEVER persisted or printed; raw payloads are never
written to disk at all. Downloaded photos go to the job tmp dir only and are
deleted immediately after exiftool reads them; only aggregated tag statistics
survive. Raw GPS coordinates are likewise never printed or stored — the
report keeps presence, precision class, and bounding-box containment only.

Usage: PYTHONPATH=/mnt/c/Users/batha/ghostfixes/pylibs python3 \\
       probe/exif_citizen_probe.py
"""

from __future__ import annotations

import json
import os
import re
import secrets
import statistics
import subprocess
import sys
import tempfile
import time
try:
    import urllib3

    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
except ImportError:  # httpx does not require it; silence is best-effort only
    pass
from collections import Counter
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse

PROBE_OUT = Path(__file__).resolve().parent / "out"

CONTACT_EMAIL = "apba00001@uni-saarland.de"  # approved for UA use 2026-08-24
USER_AGENT = (
    "GhostFixes/0.0-stage0 "
    "(+https://github.com/Apoorvabatham/ghostfixes; "
    f"contact: {CONTACT_EMAIL})"
)
MIN_REQUEST_GAP_S = 3.0  # invariant 5, hard floor

CKAN = "https://data.opencity.in/api/3/action"
DETAIL_BASE = (
    "https://sahaaya2.bbmp.gov.in/webapi/api/grievance/"
    "GetComplaintDetailforCitizen"
)
S3_HOST = "https://nammabengaluru.s3.ap-south-1.amazonaws.com"

# Bengaluru urban bbox (generous) and Karnataka bbox — containment classes
# only; individual points are never emitted.
BBOX_BLR = (12.70, 13.30, 77.20, 77.90)   # lat_min, lat_max, lon_min, lon_max
BBOX_KA = (11.50, 18.50, 74.00, 78.60)

CITIZEN_IMAGE_CAP = 25
STAFF_IMAGE_CAP = 4
SAMPLE_WANT = 45


class Limiter:
    """Global wall-clock gate: >= MIN_REQUEST_GAP_S between request starts."""

    def __init__(self, gap_s: float) -> None:
        self.gap_s = gap_s
        self._last_start = float("-inf")

    def wait(self) -> None:
        delta = self.gap_s - (time.monotonic() - self._last_start)
        if delta > 0:
            time.sleep(delta)
        self._last_start = time.monotonic()


LIMITER = Limiter(MIN_REQUEST_GAP_S)

_strict = None
_loose = None


def _clients():
    global _strict, _loose
    if _strict is None:
        import httpx

        _strict = httpx.Client(headers={"User-Agent": USER_AGENT},
                               follow_redirects=True)
        _loose = httpx.Client(headers={"User-Agent": USER_AGENT},
                              follow_redirects=True, verify=False)
    return _strict, _loose


def log(url: str, status: int | None, note: str = "") -> None:
    print(f"[{status if status is not None else 'ERR'}] {url}"
          + (f"  ({note})" if note else ""))


def fetch(url: str, *, note: str = ""):
    """One rate-limited GET; strict TLS first, flagged loose-TLS fallback.

    The loose fallback exists because sahaaya2 hosts serve an incomplete /
    mismatching chain (recorded property of their infra, see gate memo §2).
    Returns httpx.Response or None."""
    LIMITER.wait()
    strict, loose = _clients()
    try:
        resp = strict.get(url, timeout=30.0)
    except Exception as exc:  # noqa: BLE001
        msg = f"{type(exc).__name__}: {exc}"
        if "ertificate" in msg or "SSL" in msg.upper() or "TLS" in msg.upper():
            try:
                LIMITER.wait()
                resp = loose.get(url, timeout=30.0)
                log(url, resp.status_code, f"{note}; tls-fallback" if note
                    else "tls-fallback")
                return resp
            except Exception as exc2:  # noqa: BLE001
                log(url, None, f"{msg[:160]} | loose: {str(exc2)[:120]}")
                return None
        log(url, None, msg[:200])
        return None
    log(url, resp.status_code, note)
    return resp


# --------------------------------------------------------------------------
# 1. Sample garbage/Closed ticket IDs verbatim from BBMP's own publication
# --------------------------------------------------------------------------

def pick_2024_resource() -> str | None:
    r = fetch(f"{CKAN}/package_show?id=bbmp-grievances-data",
              note="package_show")
    if r is None or r.status_code != 200:
        return None
    resources = r.json().get("result", {}).get("resources", [])
    chosen = None
    for res in resources:
        name = (res.get("name") or "").lower()
        if res.get("datastore_active") and "2024" in name:
            chosen = res["id"]
            print(f"  resource: {res.get('name')} -> {chosen}")
            break
    if chosen is None and resources:
        ds = [r_ for r_ in resources if r_.get("datastore_active")]
        if ds:
            chosen = ds[-1]["id"]
            print(f"  (no 2024 match) falling back to: {chosen}")
    return chosen


def fetch_window(res_id: str, offset: int, limit: int) -> list[dict]:
    """One plain datastore_search page; SQL endpoint is disabled on this
    CKAN instance (measured 2026-08-25), so filtering happens client-side."""
    LIMITER.wait()
    strict, _ = _clients()
    try:
        resp = strict.get(
            f"{CKAN}/datastore_search",
            params={"resource_id": res_id, "limit": limit, "offset": offset},
            timeout=30.0)
    except Exception as exc:  # noqa: BLE001
        log(f"datastore_search(offset={offset})", None,
            f"{type(exc).__name__}: {exc}"[:160])
        return []
    log(f"datastore_search(offset={offset})", resp.status_code)
    if resp.status_code != 200:
        try:
            err = resp.json().get("error", {})
        except Exception:  # noqa: BLE001
            err = resp.text[:200]
        log("", None, f"  error body: {str(err)[:220]}")
        return []
    return resp.json().get("result", {}).get("records", [])


def is_closed_garbage(row: dict) -> bool:
    status = str(row.get("Grievance Status") or "").strip().lower()
    if status != "closed":
        return False
    blob = (str(row.get("Category") or "") + " " +
            str(row.get("Sub Category") or "")).lower()
    return "garbage" in blob

def sample_ids(res_id: str, want: int) -> list[dict]:
    """Closed+garbage rows, verbatim from the publisher's own export."""
    r = fetch(f"{CKAN}/datastore_search?resource_id={res_id}&limit=1",
              note="total rowcount")
    total = 1_000_000
    if r is not None and r.status_code == 200:
        total = int(r.json().get("result", {}).get("total") or total)
    print(f"  resource rows ~{total}")

    records: list[dict] = []
    # two deliberately distant windows: halves of the year, so the sample
    # is not one contiguous ID cluster from a single fortnight
    half = max(1000, total // 2)
    offsets = [
        secrets.randbelow(max(1, half - 1000)),
        half + secrets.randbelow(max(1, total - half - 1000)),
    ]
    for offset in offsets:
        window = fetch_window(res_id, offset, 1000)
        hits = [row for row in window if is_closed_garbage(row)]
        print(f"  window@{offset}: {len(window)} rows, "
              f"{len(hits)} Closed+garbage")
        records.extend(hits)
    # de-duplicate, then take a random subset
    seen: dict[str, dict] = {}
    for row in records:
        cid = str(row.get("Complaint ID") or "")
        if cid and cid not in seen:
            seen[cid] = {
                "complaint_id": cid,
                "grievance_date": row.get("Grievance Date"),
                "ward_name": row.get("Ward Name"),
                "category": row.get("Category"),
                "sub_category": row.get("Sub Category"),
                "dataset_status": row.get("Grievance Status"),
            }
    pool = list(seen.values())
    print(f"  unique Closed+garbage candidates: {len(pool)}")
    if len(pool) <= want:
        return pool
    rng = secrets.SystemRandom()
    return rng.sample(pool, want)


# --------------------------------------------------------------------------
# 2. Keyless per-ticket detail (whitelist-only field extraction)
# --------------------------------------------------------------------------

def _ticket_dict(obj) -> dict:
    """Depth-first: first dict carrying GrievanceId anywhere in the payload."""
    if isinstance(obj, list):
        for item in obj:
            got = _ticket_dict(item)
            if got:
                return got
        return {}
    if isinstance(obj, dict):
        lowered = {str(k).lower() for k in obj}
        if "grievanceid" in lowered:
            return obj
        for v in obj.values():
            got = _ticket_dict(v)
            if got:
                return got
    return {}


def _find_key(obj, wanted: str):
    """Depth-first value of key `wanted` (case-insensitive) ANYWHERE in the
    payload — needed because staffComplaintDetails sits beside the ticket
    object at the top level, not inside it (structure dump 2026-08-25)."""
    if isinstance(obj, list):
        for item in obj:
            got = _find_key(item, wanted)
            if got is not None:
                return got
        return None
    if isinstance(obj, dict):
        for k, v in obj.items():
            if str(k).lower() == wanted:
                return v
        for v in obj.values():
            got = _find_key(v, wanted)
            if got is not None:
                return got
    return None


def get_detail(ticket_id: str) -> dict | None:
    r = fetch(f"{DETAIL_BASE}?ComaplaintID={ticket_id}",
              note=f"detail {ticket_id}")  # their typo is part of the route
    if r is None or r.status_code != 200:
        return None
    try:
        payload = r.json()
    except Exception:  # noqa: BLE001
        return None
    d = _ticket_dict(payload)
    if not d:
        return None
    staff = _find_key(payload, "staffcomplaintdetails") or {}
    if isinstance(staff, list):
        staff = staff[0] if staff else {}
    if not isinstance(staff, dict):
        staff = {}
    # WHITELIST — anything not named here (Address, Description, StaffName,
    # ContactDetails, StaffRemarks, AudioPath, VideoPath, Rating …) is dropped
    # in memory and never reaches disk or console.
    return {
        "api_grievance_id": d.get("GrievanceId"),
        "ward_api": d.get("Ward"),
        "category_en": d.get("CategoryEnglish"),
        "subcategory_en": d.get("SubCategoryEnglish"),
        "grievance_date_api": d.get("GrievanceDate"),
        "citizen_status": d.get("ComplaintStatus"),
        "image_path": d.get("ImagePath") or "",
        "staff_image_path": staff.get("StaffRecentAddedImage") or "",
        "staff_status": staff.get("GrievanceStatus"),
    }


# --------------------------------------------------------------------------
# 3. Image download (job tmp only) + exiftool, two passes
# --------------------------------------------------------------------------

def tmpdir() -> Path:
    base = os.environ.get("CLAUDE_JOB_DIR")
    d = (Path(base) / "tmp" / "exif_probe") if base else \
        (Path(tempfile.gettempdir()) / "exif_probe")
    d.mkdir(parents=True, exist_ok=True)
    return d


def exiftool_passes(path: Path) -> tuple[dict, dict]:
    """(numeric-GPS pass, human-date pass) as flat tag->value dicts."""
    results = []
    for extra in (["-n"], ["-d", "%Y-%m-%d %H:%M:%S"]):
        proc = subprocess.run(
            ["exiftool", "-j", "-a", "-G1", *extra, str(path)],
            capture_output=True, text=True, timeout=60)
        arr = []
        if proc.returncode == 0 and proc.stdout.strip():
            try:
                arr = json.loads(proc.stdout)
            except json.JSONDecodeError:
                arr = []
        results.append(arr[0] if arr else {})
    return results[0], results[1]


SKIP_TAG_PREFIXES = ("System:",)
SKIP_TAGS = {"File:FileName", "File:Directory", "File:Permissions",
             "File:FileInodeChangeDate", "File:FileInodeModifyDate",
             "File:FileAccessDate", "File:FileInodeBirthDate"}


def classify_point(lat: float, lon: float) -> str:
    la, lb, oa, ob = BBOX_BLR
    if la <= lat <= lb and oa <= lon <= ob:
        return "bengaluru"
    la, lb, oa, ob = BBOX_KA
    if la <= lat <= lb and oa <= lon <= ob:
        return "karnataka_other"
    return "outside_karnataka"


def decimal_digits(value: str) -> int:
    s = str(value)
    return len(s.split(".")[-1]) if "." in s else 0


def parse_filing_date(raw: str | None):
    if not raw:
        return None
    text = re.sub(r"\.\d+$", "", str(raw).strip().replace("T", " "))
    fmts = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d",
            "%d-%m-%Y %H:%M:%S", "%d-%m-%Y %H:%M", "%d-%m-%Y",
            "%d/%m/%Y %H:%M", "%d/%m/%Y")
    for f in fmts:
        try:
            return datetime.strptime(text, f)
        except ValueError:
            continue
    return None


STAFF_TS_RE = re.compile(r"(?<![0-9])(\d{4})(\d{1,2})(\d{1,2})(\d{1,2})(\d{1,2})(\d{1,2})(?![0-9])")


STAFF_TS_RE_LOOSE = re.compile(r"(\d{4})(\d{1,2})(\d{1,2})(\d{1,2})(\d{1,2})(\d{1,2})")


def parse_staff_filename_ts(url_or_path: str):
    stem = re.sub(r"\.[A-Za-z0-9]+$", "", str(url_or_path).rsplit("/", 1)[-1])
    m = STAFF_TS_RE.search(stem)
    if not m:
        # relaxed: some filenames append id digits straight after the seconds;
        # ranges are validated below either way
        m = STAFF_TS_RE_LOOSE.search(stem)
    if not m:
        return None
    y, mo, d, h, mi, s = (int(g) for g in m.groups())
    try:
        return datetime(y, mo, d, h, mi, s)
    except ValueError:
        return None


def process_images(entries: list[dict], label: str, summary: dict) -> None:
    """entries: [{ticket_id, url, kind}] — downloads, measures, deletes."""
    workdir = tmpdir()
    tag_presence: Counter = Counter()
    outcomes: Counter = Counter()
    n_ok = 0
    gps_points_class = Counter()
    gps_digits: list[int] = []
    has_altitude = 0
    dt_original_vs_filing: list[float] = []   # minutes, photo - filing
    lastmod_vs_filing: list[float] = []       # minutes, lastmod - filing
    staff_ts_vs_filing: list[float] = []      # minutes, filename-ts - filing
    software_values: Counter = Counter()
    model_values: Counter = Counter()
    content_types: Counter = Counter()
    sizes_kb: list[float] = []
    dims: list[tuple[int, int]] = []
    fname_ts_vs_filing: list[float] = []
    lm_present = 0

    for ent in entries:
        url = ent["url"]
        dest = workdir / f"{ent['kind']}_{ent['ticket_id']}.bin"
        try:
            r = fetch(url, note=f"{label} image {ent['ticket_id']}")
            if r is None:
                outcomes["transport_error"] += 1
                continue
            outcomes[r.status_code] += 1
            if r.headers.get("last-modified"):
                lm_present += 1
            if r.status_code != 200:
                continue
            ctype = r.headers.get("content-type", "")
            content_types[ctype] += 1
            sizes_kb.append(round(len(r.content) / 1024, 1))
            dest.write_bytes(r.content)
            num, hum = exiftool_passes(dest)
            n_ok += 1

            # --- presence table over the numeric pass ---
            for tag, val in num.items():
                if tag.startswith(SKIP_TAG_PREFIXES) or tag in SKIP_TAGS:
                    continue
                if val not in ("", None):
                    tag_presence[tag] += 1

            # --- GPS ---
            lat_raw, lon_raw = num.get("GPS:GPSLatitude"), num.get("GPS:GPSLongitude")
            lat_ref = str(num.get("GPS:GPSLatitudeRef", "N")).upper()
            lon_ref = str(num.get("GPS:GPSLongitudeRef", "E")).upper()
            if isinstance(lat_raw, (int, float)) and isinstance(lon_raw, (int, float)):
                lat = float(lat_raw) * (-1 if lat_ref == "S" else 1)
                lon = float(lon_raw) * (-1 if lon_ref == "W" else 1)
                gps_points_class[classify_point(lat, lon)] += 1
                gps_digits.append(min(decimal_digits(lat_raw), decimal_digits(lon_raw)))
                if num.get("GPS:GPSAltitude") not in (None, ""):
                    has_altitude += 1

            # --- capture timestamp vs filing timestamp ---
            filing = parse_filing_date(ent.get("filing"))
            taken_raw = (hum.get("ExifIFD:DateTimeOriginal")
                         or hum.get("ExifIFD:CreateDate")
                         or hum.get("Composite:SubSecDateTimeOriginal"))
            taken = None
            if taken_raw:
                try:
                    taken = datetime.strptime(str(taken_raw),
                                              "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    taken = None
            if filing and taken:
                dt_original_vs_filing.append(
                    (taken - filing).total_seconds() / 60.0)

            # --- S3 Last-Modified header vs filing ---
            lm = r.headers.get("last-modified")
            if lm and filing:
                try:
                    from email.utils import parsedate_to_datetime
                    lmdt = parsedate_to_datetime(lm)
                    lastmod_vs_filing.append(
                        (lmdt - filing).total_seconds() / 60.0)
                except Exception:  # noqa: BLE001
                    pass

            # --- embedded filename timestamps (portal naming scheme) ---
            fts = parse_staff_filename_ts(url)
            if fts and filing:
                fname_ts_vs_filing.append(
                    (fts - filing).total_seconds() / 60.0)

            # --- editor/device hints ---
            if hum.get("XMP-xmp:CreatorTool"):
                software_values[str(hum["XMP-xmp:CreatorTool"])] += 1
            for sw_tag in ("EXIF:Software", "XMP-x:XMPTitle", "IFD0:Software"):
                if hum.get(sw_tag):
                    software_values[str(hum[sw_tag])] += 1
            for mk in ("EXIF:Model", "IFD0:Model"):
                if hum.get(mk):
                    model_values[f"{hum.get('EXIF:Make') or hum.get('IFD0:Make') or '?'} {hum[mk]}"] += 1

            w = num.get("File:ImageWidth")
            hgt = num.get("File:ImageHeight")
            if isinstance(w, int) and isinstance(hgt, int):
                dims.append((w, hgt))
        finally:
            dest.unlink(missing_ok=True)  # invariant 6: binaries never linger

    s = summary.setdefault(label, {})
    s["attempted"] = len(entries)
    s["fetched_and_parsed"] = n_ok
    s["content_types"] = dict(content_types)
    s["size_kb_median"] = round(statistics.median(sizes_kb), 1) if sizes_kb else None
    s["distinct_dimensions"] = sorted(set(dims))[:8]
    s["tag_presence_over_n_images"] = {
        k: v for k, v in sorted(tag_presence.items())}
    s["gps_points_bbox_class"] = dict(gps_points_class)
    if gps_digits:
        s["gps_decimal_digits_range"] = [min(gps_digits), max(gps_digits)]
        approx_m = 111_320 * (10 ** -max(gps_digits))
        s["gps_precision_approx_m_at_coarsest"] = round(approx_m, 3)
    else:
        s["gps_decimal_digits_range"] = None
    s["gps_altitude_present"] = has_altitude
    s["http_outcomes"] = dict(outcomes)
    s["server_lastmodified_header_present"] = lm_present
    if fname_ts_vs_filing:
        fname_ts_vs_filing.sort()
        s["filename_embedded_ts_minus_filing_minutes"] = {
            "n": len(fname_ts_vs_filing),
            "min": round(fname_ts_vs_filing[0], 1),
            "median": round(statistics.median(fname_ts_vs_filing), 1),
            "max": round(fname_ts_vs_filing[-1], 1)}
    if dt_original_vs_filing:
        dt_original_vs_filing.sort()
        s["photo_taken_minus_filing_minutes"] = {
            "n": len(dt_original_vs_filing),
            "min": round(dt_original_vs_filing[0], 1),
            "median": round(statistics.median(dt_original_vs_filing), 1),
            "max": round(dt_original_vs_filing[-1], 1),
            "negative_count_before_filing":
                sum(1 for x in dt_original_vs_filing if x < 0)}
    if lastmod_vs_filing:
        lastmod_vs_filing.sort()
        s["object_lastmodified_minus_filing_minutes"] = {
            "n": len(lastmod_vs_filing),
            "min": round(lastmod_vs_filing[0], 1),
            "median": round(statistics.median(lastmod_vs_filing), 1),
            "max": round(lastmod_vs_filing[-1], 1)}
    if software_values:
        s["software_creator_tags"] = dict(software_values.most_common(6))
    if model_values:
        s["camera_make_model"] = dict(model_values.most_common(6))


def main() -> int:
    print(f"GhostFixes citizen-photo EXIF probe — UA: {USER_AGENT}")

    # -- sample (or reuse the previous run's IDs unchanged) -----------------
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    records_prev = None
    if mode == "--images-only":
        records_prev = json.loads(
            (PROBE_OUT / "citizen_exif_records.json").read_text())
        sample = []
        print(f"--images-only: reloading {len(records_prev)} records "
              "(no detail-API calls)")
    elif mode == "--redetails":
        prev = json.loads(
            (PROBE_OUT / "citizen_exif_records.json").read_text())
        keep = ("complaint_id", "grievance_date", "ward_name", "category",
                "sub_category", "dataset_status")
        sample = [{k: r_.get(k) for k in keep} for r_ in prev]
        print(f"--redetails: reloading {len(sample)} sampled IDs "
              "(same cohort, fixed extractor)")
    else:
        print("\n== sampling Closed+garbage ticket IDs from BBMP's published CSV ==")
        res_id = pick_2024_resource()
        if res_id is None:
            print("!! no datastore-active resource found; aborting")
            return 1
        sample = sample_ids(res_id, SAMPLE_WANT)
        print(f"  sampled {len(sample)} ticket IDs")
        if not sample:
            return 1

    # -- details -----------------------------------------------------------
    records: list[dict] = []
    if records_prev is not None:
        records = records_prev
    else:
        print("\n== keyless per-ticket detail (whitelisted fields only) ==")
        for row in sample:
            det = get_detail(row["complaint_id"])
            if det is None:
                continue
            merged = {**row, **det}
            records.append(merged)

        PROBE_OUT.mkdir(parents=True, exist_ok=True)
        (PROBE_OUT / "citizen_exif_records.json").write_text(
            json.dumps(records, indent=2, ensure_ascii=False))

    n_img = sum(1 for r in records if r.get("image_path"))
    n_staff_img = sum(1 for r in records if r.get("staff_image_path"))
    print(f"\n  details retrieved: {len(records)}; "
          f"ImagePath populated {n_img}/{len(records)}; "
          f"StaffRecentAddedImage populated {n_staff_img}/{len(records)}")

    # -- normalise image URLs ----------------------------------------------
    def abs_url(path: str) -> str | None:
        p = str(path).strip()
        if not p or p.lower() == "null":
            return None
        if p.startswith("http://") or p.startswith("https://"):
            return p
        return f"{S3_HOST}/{p.lstrip('/')}"

    # URL shapes (structure only) — tells us where the portal points citizens
    shape_counts: Counter = Counter()
    for r in records:
        p = str(r.get("image_path") or "")
        if not p:
            continue
        host = ""
        m = re.match(r"https?://([^/]+)", p)
        host = m.group(1) if m else "(relative)"
        shape_counts[host] += 1
    print(f"  ImagePath URL host shapes: {dict(shape_counts)}")

    citizen_entries = [
        {"ticket_id": r["complaint_id"],
         "filing": r.get("grievance_date_api") or r.get("grievance_date"),
         "kind": "citizen", "url": u}
        for r in records
        if (u := abs_url(r.get("image_path"))) is not None
    ][:CITIZEN_IMAGE_CAP]

    # duplicate-URL observation (miniature recycled-image signal)
    url_counts = Counter(e["url"] for e in citizen_entries)
    dup_urls = {u: c for u, c in url_counts.items() if c > 1}

    staff_entries = [
        {"ticket_id": r["complaint_id"],
         "filing": r.get("grievance_date_api") or r.get("grievance_date"),
         "kind": "staff", "url": abs_url(r.get("staff_image_path"))}
        for r in records if r.get("staff_image_path")
    ]
    fixed_staff = []
    for e in staff_entries:
        u = e["url"]
        if u and not u.startswith("http"):
            u = f"https://sahaaya2.bbmpgov.in/{u.lstrip('/')}"
        if u:
            e["url"] = u
            fixed_staff.append(e)
    staff_entries = fixed_staff[:STAFF_IMAGE_CAP]

    # -- measure ------------------------------------------------------------
    summary: dict = {}

    print("\n== citizen-side photos: EXIF measurement, split by storage ==")
    s3_entries = [e for e in citizen_entries
                  if urlparse(e["url"]).netloc.startswith("nammabengaluru")]
    legacy_entries = [e for e in citizen_entries
                      if not urlparse(e["url"]).netloc.startswith("nammabengaluru")]
    print(f"  s3-generation: {len(s3_entries)}; "
          f"legacy-sahaaya2-generation: {len(legacy_entries)}")
    process_images(s3_entries, "citizen_s3", summary)
    process_images(legacy_entries, "citizen_legacy", summary)

    print("\n== staff-side photos (contrast; expect zero EXIF per memo §2) ==")
    process_images(staff_entries, "staff_contrast", summary)

    # publisher-side data-quality audit: dataset minute vs API second
    # for the same ticket (a 12-hour class would indicate an AM/PM export bug)
    skews = {"equal_within_2min": 0, "shift_12h_plusminus_5min": 0,
             "other": 0, "unparseable": 0}
    for r in records:
        dsdt = parse_filing_date(r.get("grievance_date"))
        apidt = parse_filing_date(r.get("grievance_date_api"))
        if not (dsdt and apidt):
            skews["unparseable"] += 1
            continue
        delta_min = abs((apidt - dsdt).total_seconds() / 60.0)
        if delta_min <= 2:
            skews["equal_within_2min"] += 1
        elif abs(delta_min - 720) <= 5:
            skews["shift_12h_plusminus_5min"] += 1
        else:
            skews["other"] += 1
    summary["dataset_vs_api_filing_delta_classes"] = skews

    summary["citizen_duplicate_image_urls"] = dup_urls
    summary["sample"] = {
        "tickets_sampled": len(sample),
        "details_retrieved": len(records),
        "citizen_images_attempted": len(citizen_entries),
        "staff_images_attempted": len(staff_entries)}

    (PROBE_OUT / "citizen_exif_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False))

    print("\n== SUMMARY (aggregates only; no coordinates, no PII) ==")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
