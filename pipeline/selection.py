"""Selection-rule mechanism: padded-CSV superset in, live-API membership out.

The FORM, not any city's values. Stage A runs over a publisher's bulk CSV and
admits rows whose category matches (whitespace-normalised comparison is
permitted and recorded when it fires) and whose CSV date begins with one of
the configured padding prefixes — padding wide enough to absorb a known
export clock artifact. Stage B decides membership on the live API's filing
timestamp alone; the CSV date is never used in arithmetic. Pure — no I/O,
no network — so tests pin this behaviour. City values come from an adapter
(see pipeline/adapter_api.py and docs/adapter-interface.md).
"""

from datetime import datetime

_DATETIME_FORMATS = (
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
)


def parse_api_datetime(value):
    """Parse a live-API filing-timestamp string to a canonical comparable form.

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


class SelectionRule:
    """Two-stage membership rule (see docs/stage1-scope-lock.md §2 for the
    original wording this mechanism encodes).

    Stage A is deliberately looser than the window: its prefixes form a
    candidate superset padded against clock artifacts in the published CSV.
    Stage B alone decides membership, on the live API timestamp exclusively.
    """

    def __init__(self, category, csv_date_prefixes, window_start,
                 window_end_exclusive, pad_day_prefixes=(),
                 artifact_delta_minutes=None, artifact_tolerance_minutes=2):
        if not isinstance(category, str) or not category:
            raise ValueError("category must be a non-empty string")
        if not csv_date_prefixes or not all(
                isinstance(p, str) and p for p in csv_date_prefixes):
            raise ValueError("csv_date_prefixes must be non-empty strings")
        start = parse_api_datetime(window_start)
        end = parse_api_datetime(window_end_exclusive)
        if start is None or end is None:
            raise ValueError("window bounds must be canonical datetimes")
        if not start < end:
            raise ValueError("window_end_exclusive must be after window_start")
        pads = tuple(pad_day_prefixes)
        for prefix in pads:
            if prefix not in self._as_tuple(csv_date_prefixes):
                raise ValueError(
                    "pad_day_prefixes must be a subset of csv_date_prefixes")
        if artifact_delta_minutes is not None:
            if not artifact_delta_minutes or not all(
                    isinstance(d, (int, float)) and d >= 0
                    for d in artifact_delta_minutes):
                raise ValueError(
                    "artifact_delta_minutes must be non-negative numbers "
                    "when declared")
        if artifact_tolerance_minutes < 0:
            raise ValueError("artifact_tolerance_minutes must be >= 0")
        self.category = category
        self.csv_date_prefixes = tuple(csv_date_prefixes)
        self.pad_day_prefixes = pads
        self.artifact_delta_minutes = (
            None if artifact_delta_minutes is None
            else tuple(float(d) for d in artifact_delta_minutes))
        self.artifact_tolerance_minutes = float(artifact_tolerance_minutes)
        self.window_start = start
        self.window_end_exclusive = end

    @staticmethod
    def _as_tuple(prefixes):
        return prefixes if isinstance(prefixes, tuple) else tuple(prefixes)

    def csv_date_is_pad(self, csv_grievance_date):
        """True when the published CSV date falls on a declared padding day —
        a row admitted only to absorb the publisher's export clock artifact,
        never part of the analysis window proper. The mechanism holds the
        form (padding exists, is declared, stays a subset of Stage-A
        prefixes); the adapter declares which prefixes pad."""
        return (csv_grievance_date or "").startswith(self.pad_day_prefixes)

    def api_csv_delta_minutes(self, api_parsed, csv_date_raw):
        """Absolute minute distance between the live API filing timestamp
        (canonical form) and the published CSV timestamp.

        Returns None when the adapter declared no artifact deltas (checking
        disabled) or when either side is absent or unparseable — nothing
        comparable, never a verdict. The declared deltas plus tolerance are
        the ONLY acceptable distances; the adapter measures them (for this
        corpus: 33/45 pairs within 2 minutes, 12/45 exactly 12 h apart,
        zero anywhere else — docs/citizen-exif-probe-2026-08-25.md), and a
        distance outside them is a read fault, not data.
        """
        if not self.artifact_delta_minutes or api_parsed is None:
            return None
        csv_parsed = parse_api_datetime(csv_date_raw)
        if csv_parsed is None:
            return None
        from datetime import datetime
        api_dt = datetime.strptime(api_parsed, "%Y-%m-%dT%H:%M:%S")
        csv_dt = datetime.strptime(csv_parsed, "%Y-%m-%dT%H:%M:%S")
        return abs((api_dt - csv_dt).total_seconds()) / 60.0

    def is_stage_a_candidate(self, category, csv_grievance_date):
        """Return (is_candidate, note) for one published CSV row.

        `note` records whether whitespace normalisation changed the
        comparison — permitted, but never silently.
        """
        raw = category or ""
        stripped = raw.strip()
        matched_exact = raw == self.category
        matched_normalized = stripped == self.category
        date_ok = (csv_grievance_date or "").startswith(self.csv_date_prefixes)
        note = {
            "category_matched": bool(matched_exact or matched_normalized),
            "normalization_fired": matched_normalized and not matched_exact,
            "csv_date": csv_grievance_date,
        }
        return note["category_matched"] and date_ok, note

    def is_stage_b_member(self, api_grievance_date):
        """Return (is_member, parsed_or_None); window start-inclusive,
        end-exclusive."""
        parsed = parse_api_datetime(api_grievance_date)
        if parsed is None:
            return False, None
        member = self.window_start <= parsed < self.window_end_exclusive
        return member, parsed
