"""Bengaluru / GBA (Sahaaya 2.0) — every portal-specific fact in one file.

Sources for everything below: docs/stage0-report.md, docs/stage1-gate.md,
docs/citizen-exif-probe-2026-08-25.md, docs/stage1-scope-lock.md. Nothing
here may be generalised into pipeline/ until a second portal forces the
question (CLAUDE.md Stage 6/7).
"""

import re
from datetime import datetime
from urllib.parse import urlsplit

from pipeline.adapter_api import CityAdapter, ImageFetch, TicketDetail
from pipeline.selection import SelectionRule

# --- locked scope (docs/stage1-scope-lock.md §1–§2) ---
CATEGORY = "Solid Waste (Garbage) Related"

# Stage A padding: a ±12 h export artifact moves a CSV timestamp by at most
# one calendar day, so exactly one day of pad on each side absorbs it.
CSV_DATE_PREFIXES = (
    "2024-12-31",  # pad below window
    "2025-01",
    "2025-02",
    "2025-03",
    "2025-04-01",  # pad above window
)
WINDOW_START = "2025-01-01T00:00:00"
WINDOW_END_EXCLUSIVE = "2025-04-01T00:00:00"

# Keyless per-ticket endpoint (measured in docs/stage1-gate.md §1). The
# misspelling `ComaplaintID` is part of the vendor route — do not correct it.
DETAIL_URL_TEMPLATE = (
    "https://sahaaya2.bbmp.gov.in/webapi/api/grievance/"
    "GetComplaintDetailforCitizen?ComaplaintID={ticket_id}"
)

# Hosts carrying images (docs/citizen-exif-probe-2026-08-25.md): staff photos
# on the one-word spelling, citizen photos on S3, legacy thumbnails on the
# dotted spelling. The one-word host serves a TLS chain that does not match
# its name — a documented property of this portal's infrastructure since the
# first probe; fetching measures reachability, not certificate validity.
_TLS_UNTRUSTED_HOSTS = frozenset({"sahaaya2.bbmpgov.in"})

# Staff-photo filename timestamp grammar (docs/stage1-gate.md §4b): an
# unpadded local timestamp as space-separated groups YYYY M D H M [S].
# Measured limitation: a trailing seconds group can run straight into
# adjacent id digits, so seconds are accepted only when digit-bounded;
# otherwise the moment degrades to minute precision (:00 second), which any
# consumer must treat as minute-accurate at best.
_STAFF_TS_RE = re.compile(
    r"(?<!\d)(\d{4}) (\d{1,2}) (\d{1,2}) (\d{1,2}) (\d{1,2})"
    r"(?: (\d{1,2})(?!\d))?"
)


def parse_staff_filename(filename):
    """Strictly parse a staff-photo filename's embedded timestamp.

    Returns canonical 'YYYY-MM-DDTHH:MM:SS', or None when nothing
    unambiguous matches — impossible dates are rejected, never normalised.
    """
    if not isinstance(filename, str):
        return None
    match = _STAFF_TS_RE.search(filename)
    if not match:
        return None
    year = int(match.group(1))
    if not 2000 <= year <= 2100:
        return None
    parts = [int(match.group(i)) for i in range(2, 6)]
    second = int(match.group(6)) if match.group(6) is not None else 0
    try:
        stamp = datetime(year, *parts, second)
    except ValueError:
        return None
    return stamp.strftime("%Y-%m-%dT%H:%M:%S")


def _text(value):
    """Whitespace-stripped text or None; payload noise never becomes data."""
    if isinstance(value, str):
        stripped = value.strip()
        if stripped and stripped.lower() != "null":
            return stripped
    return None

class BengaluruAdapter(CityAdapter):
    name = "bengaluru"
    selection = SelectionRule(CATEGORY, CSV_DATE_PREFIXES, WINDOW_START,
                              WINDOW_END_EXCLUSIVE)

    def detail_url(self, ticket_id: str) -> str:
        return DETAIL_URL_TEMPLATE.format(ticket_id=ticket_id)

    def parse_detail(self, payload) -> TicketDetail:
        # Invariant 1: Address, Description, StaffName, ContactDetails and
        # StaffRemarks exist on this payload and are deliberately NEVER read.
        # The staff block sits beside the ticket object at top level, not
        # inside it (documented extraction quirk).
        data = payload if isinstance(payload, dict) else {}
        staff = data.get("staffComplaintDetails")
        if not isinstance(staff, dict):
            staff = {}
        urls = []
        for candidate in (data.get("ImagePath"),
                          staff.get("StaffRecentAddedImage")):
            text = _text(candidate)
            if text:
                urls.append(text)
        return TicketDetail(
            ticket_id=str(data.get("GrievanceId") or ""),
            ward=_text(data.get("Ward")),
            category=_text(data.get("CategoryEnglish")),
            sub_category=_text(data.get("SubCategoryEnglish")),
            filed_at_raw=_text(data.get("GrievanceDate")),
            citizen_status=_text(data.get("ComplaintStatus")),
            staff_status=_text(staff.get("GrievanceStatus")),
            image_urls=tuple(urls),
        )

    def image_plan(self, url: str) -> ImageFetch | None:
        parsed = urlsplit(url)
        if (parsed.scheme or "").lower() not in ("http", "https"):
            return None
        host = (parsed.netloc or "").lower()
        return ImageFetch(url=url, verify_tls=host not in _TLS_UNTRUSTED_HOSTS)

    def staff_resolution_timestamp(self, filename: str) -> str | None:
        return parse_staff_filename(filename)


ADAPTER = BengaluruAdapter()
