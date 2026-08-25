"""Stage A manifest — the candidate superset, built once and committed.

Consumes raw publisher-CSV rows ONLY through adapter.parse_csv_row (so
column knowledge stays portal-side and no other field is ever read),
applies adapter.selection Stage A, dedupes ticket IDs (first occurrence
wins, duplicates counted), orders numerically for deterministic resume.
Records carry nothing beyond ID, source label, raw CSV date, and the two
match flags. The manifest pins the sweep's input set before any per-ticket
request exists.
"""

import json


def build_candidates(adapter, rows_by_label):
    """rows_by_label: iterable of (label, iterable-of-raw-row-dicts).
    Returns (candidates_sorted, duplicate_count)."""
    seen = {}
    duplicates = 0
    for label, rows in rows_by_label:
        for raw in rows:
            crow = adapter.parse_csv_row(raw)
            if crow is None:
                continue
            ok, note = adapter.selection.is_stage_a_candidate(
                crow.category, crow.csv_date)
            if not ok:
                continue
            tid = crow.ticket_id
            if tid in seen:
                duplicates += 1
                continue
            seen[tid] = {
                "ticket_id": tid,
                "source": label,
                "csv_date_raw": crow.csv_date,
                "category_exact": (note["category_matched"]
                                   and not note["normalization_fired"]),
                "normalization_fired": note["normalization_fired"],
            }

    def order(tid):
        return (0, int(tid)) if tid.isdigit() else (1, tid)

    return [seen[t] for t in sorted(seen, key=order)], duplicates


def write_manifest(path, candidates):
    with open(path, "w", encoding="utf-8") as fh:
        for rec in candidates:
            fh.write(json.dumps(rec, ensure_ascii=False, sort_keys=True) + "\n")


def load_manifest(path):
    out = []
    with open(path, encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{lineno}: unparsable manifest "
                                 "line — fail loudly") from exc
            out.append(rec)
    return out
