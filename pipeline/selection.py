"""The Stage 1 selection rule, verbatim from docs/stage1-scope-lock.md §2.

Stage A runs over BBMP's published CSV (candidate superset, padded ±1 calendar
day against the measured ±12 h export artifact); Stage B decides membership on
the live API's GrievanceDate alone. The CSV date is never used in arithmetic.
Pure functions only — no I/O, no network — so tests pin this behaviour.
"""

from datetime import datetime

CATEGORY = "Solid Waste (Garbage) Related"

# Stage A: padded window prefixes. A ±12 h shift moves a timestamp by at most
# one calendar day, so padding of exactly one day on each side fully absorbs it.
CSV_DATE_PREFIXES = (
    "2024-12-31",  # pad below window
    "2025-01",
    "2025-02",
    "2025-03",
    "2025-04-01",  # pad above window
)

# Stage B: membership bounds, portal-local frame, end-exclusive.
WINDOW_START = "2025-01-01T00:00:00"
WINDOW_END_EXCLUSIVE = "2025-04-01T00:00:00"


def is_stage_a_candidate(category: str, csv_grievance_date: str):
    """Return (is_candidate, note) for one published CSV row.

    `note` records whether whitespace normalisation changed the comparison —
    the scope lock permits normalised comparison but requires it be recorded.
    """
    raw = category or ""
    stripped = raw.strip()
    matched_exact = raw == CATEGORY
    matched_normalized = stripped == CATEGORY
    date_ok = (csv_grievance_date or "").startswith(CSV_DATE_PREFIXES)
    note = {
        "category_matched": bool(matched_exact or matched_normalized),
        "normalization_fired": matched_normalized and not matched_exact,
        "csv_date": csv_grievance_date,
    }
    return note["category_matched"] and date_ok, note


_DATETIME_FORMATS = (
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
)


def parse_api_datetime(value: str):
    """Parse a live-API GrievanceDate string to a canonical comparable form.

    Observed payloads carry second or minute precision, 'T' or space separated.
    Returns 'YYYY-MM-DDTHH:MM:SS' or None when unparseable — never guesses.
    """
    text = (value or "").strip()
    head = text[:19]
    for fmt in _DATETIME_FORMATS:
        try:
            dt = datetime.strptime(head, fmt)
        except ValueError:
            continue
        return dt.strftime("%Y-%m-%dT%H:%M:%S")
    return None


def is_stage_b_member(api_grievance_date: str):
    """Return (is_member, parsed_or_None) per the scope-lock Stage B rule."""
    parsed = parse_api_datetime(api_grievance_date)
    if parsed is None:
        return False, None
    member = WINDOW_START <= parsed < WINDOW_END_EXCLUSIVE
    return member, parsed
