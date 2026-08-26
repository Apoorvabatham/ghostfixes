"""Tests for the Amendment F local batch driver (probe/phase1_local.py).

The driver must be a transparent observer: every HTTP request gets exactly
one timing line, transport errors are recorded AND re-raised (SurfaceGuard
must see them exactly as the unwrapped client would deliver them), kind is
what the adapter's call site says it is, the run refuses to start unbounded
or while another instance holds the sweep lock, and the dry-run invariant
checks gate the exit code. All network here is httpx.MockTransport; the
limiter runs on a fast-forwarding clock so tests stay fast.
"""

import glob
import io
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

import httpx

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for path in (REPO_ROOT, os.path.join(REPO_ROOT, "probe")):
    if path not in sys.path:
        sys.path.insert(0, path)

import fcntl

import phase1_local
from adapters.bengaluru import ADAPTER
from pipeline.limiter import GlobalLimiter
from pipeline.manifest import build_candidates
from pipeline.sweep import SurfaceDegraded

CAT = "Solid Waste (Garbage) Related"
DETAIL_MARKER = "GetComplaintDetailforCitizen"

# Citizen photos live on an S3 host whose path carries NO /GrievanceImages/
# marker — kind must come from the call-site tag, not URL shape.
CITIZEN_URL = ("https://nammabengaluru.s3.ap-south-1.amazonaws.com/"
               "Grievance/Images/900001/citizen.jpg")


def png_bytes():
    from PIL import Image
    img = Image.new("L", (8, 8), 90)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def csv_rows(tids):
    return [{"Complaint ID": str(t), "Category": CAT,
             "Grievance Date": "2025-01-15 09:16:00.000000000"}
            for t in tids]


def detail_payload(tid):
    return {
        "citizenComplaintDetails": {
            "GrievanceId": str(tid),
            "Ward": "W1",
            "CategoryEnglish": CAT,
            "SubCategoryEnglish": "Garbage dump",
            "GrievanceDate": "2025-01-15T09:16:04",
            "ComplaintStatus": "Closed",
            "ImagePath": (
                "https://sahaaya2.bbmp.gov.in/ProjectImages/"
                f"GrievanceImages/{tid}/202512224151STAFF{tid}001.jpg"),
        },
        "staffComplaintDetails": {
            "GrievanceStatus": "Closed",
            "StaffRecentAddedImage": CITIZEN_URL.replace("900001", str(tid)),
        },
    }


def make_handler(seen, mode="happy"):
    """mode: 'happy' | 'timeout' (ReadTimeout on every detail call)."""
    body = png_bytes()

    def handler(request):
        seen.append(request)
        url = str(request.url)
        if DETAIL_MARKER in url:
            if mode == "timeout":
                raise httpx.ReadTimeout("simulated outage",
                                        request=request)
            tid = url.split("ComaplaintID=", 1)[1]
            return httpx.Response(200, json=detail_payload(tid))
        return httpx.Response(200, content=body)
    return handler


class FastClock:
    """Advances only inside sleep() — the limiter's injectable contract
    (mirrors test_sweep.ManualClock). A no-op sleep against the REAL clock
    would busy-wait ~3 s per request instead of fast-forwarding."""

    def __init__(self):
        self.now = 1000.0

    def clock(self):
        return self.now

    def sleep(self, duration):
        self.now += duration


class LocalDriverTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data_dir = os.path.join(self.tmp.name, "data")
        os.makedirs(self.data_dir)
        candidates, _ = build_candidates(
            ADAPTER, [("2025", csv_rows(range(900001, 900007)))])
        with open(os.path.join(self.data_dir, "manifest.jsonl"), "w") as fh:
            for rec in candidates:
                fh.write(json.dumps(rec, sort_keys=True) + "\n")
        self.timings_path = os.path.join(self.tmp.name, "timings.jsonl")

    def tearDown(self):
        self.tmp.cleanup()

    def run_main(self, mode="happy", extra=None):
        seen = []
        captured = {"user_agent": None}
        real_init = phase1_local.TimedPortalClient

        def patched(user_agent, timings_path, **kwargs):
            captured["user_agent"] = user_agent
            kwargs.setdefault(
                "transport", httpx.MockTransport(make_handler(seen, mode)))
            # Fast-forwarding limiter: spacing assertions belong to prod
            # runs; unit tests measure capture and propagation, not wall.
            fast = FastClock()
            kwargs.setdefault("limiter",
                              GlobalLimiter(clock=fast.clock,
                                            sleep=fast.sleep))
            return real_init(user_agent, timings_path, **kwargs)

        argv = ["--data-dir", self.data_dir,
                "--timings-out", self.timings_path,
                "--progress-every", "2",
                "--max-requests", "1000"] + (extra or [])
        with mock.patch.object(phase1_local, "TimedPortalClient", patched):
            rc = phase1_local.main(argv)
        return rc, seen, captured

    def read_timings(self):
        with open(self.timings_path) as fh:
            return [json.loads(line) for line in fh]

    def test_happy_path_one_timing_line_per_request(self):
        rc, seen, captured = self.run_main()
        self.assertEqual(rc, 0)
        records = self.read_timings()
        self.assertEqual(len(records), len(seen))
        kinds = {r["kind"] for r in records}
        self.assertEqual(kinds, {"detail", "image"})
        for rec, request in zip(records, seen):
            self.assertIn(rec["kind"], ("detail", "image"))
            self.assertEqual(rec["status"], 200)
            self.assertIsInstance(rec["mono_s"], float)
            self.assertNotIn("error", rec)
        by_kind = {}
        for rec in records:
            by_kind[rec["kind"]] = by_kind.get(rec["kind"], 0) + 1
        # 6 detail calls + both images on each kept ticket.
        self.assertEqual(by_kind["detail"], 6)
        self.assertEqual(by_kind["image"], 12)

    def test_citizen_s3_images_are_tagged_image_not_detail(self):
        # The citizen S3 URL carries no /GrievanceImages/ marker; only the
        # call-site tag can classify it correctly.
        rc, _, _ = self.run_main()
        self.assertEqual(rc, 0)
        s3_records = [r for r in self.read_timings()
                      if "s3.ap-south-1.amazonaws.com" in r["host"]]
        self.assertEqual(len(s3_records), 6)
        for rec in s3_records:
            self.assertEqual(rec["kind"], "image")
            self.assertEqual(rec["status"], 200)

    def test_user_agent_is_the_explicit_honest_local_identity(self):
        # Pre-probe review: the UA must be defined here outright — a blind
        # .replace() of another module's literal is a silent no-op away
        # from live traffic misidentifying itself (invariant 5).
        rc, _, captured = self.run_main()
        self.assertEqual(rc, 0)
        ua = captured["user_agent"]
        self.assertEqual(ua, phase1_local.USER_AGENT)
        self.assertIn("GhostFixes/", ua)
        self.assertIn("phase1-local", ua)
        self.assertIn("contact:", ua)

    def test_summary_and_invariants_written_beside_timings(self):
        rc, _, _ = self.run_main()
        self.assertEqual(rc, 0)
        summaries = glob.glob(os.path.join(
            os.path.dirname(self.timings_path), "local_*.json"))
        self.assertEqual(len(summaries), 1)
        with open(summaries[0]) as fh:
            summary = json.load(fh)
        self.assertEqual(summary["requests_total"], 18)
        self.assertEqual(set(summary["by_kind"]), {"detail", "image"})
        self.assertEqual(summary["statuses"],
                         {"detail/200": 6, "image/200": 12})
        self.assertEqual(summary["errors"], {})
        # Monotonic-stamp spacing: present and sane whenever >=2 requests.
        self.assertIsNotNone(summary["min_start_gap_s"])
        self.assertGreaterEqual(summary["min_start_gap_s"], 0.0)

    def test_transport_errors_recorded_then_reraised(self):
        # SurfaceGuard halts at 5 consecutive surface failures; the wrapper
        # must have recorded all five ReadTimeouts before the halt, and the
        # exception must reach main's caller untouched.
        with self.assertRaises(SurfaceDegraded):
            self.run_main(mode="timeout")
        records = self.read_timings()
        self.assertEqual(len(records), 5)
        for rec in records:
            self.assertEqual(rec["error"], "ReadTimeout")
            self.assertNotIn("status", rec)

    def test_invariant_check_failure_returns_two(self):
        bad = os.path.join(self.data_dir, "journal_bad.jsonl")
        with open(bad, "w") as fh:
            fh.write(json.dumps({"ticket_id": "1", "state": "candidate",
                                 "not_in_universe": "x"}) + "\n")
        rc, _, _ = self.run_main()
        self.assertEqual(rc, 2)

    def test_unbounded_run_refused(self):
        # Amendment F batches are bounded by design; omitting both bounds
        # would silently convert a 65-minute batch into a multi-day run.
        # argparse rejects this before the lock, the client, or data/.
        argv = ["--data-dir", self.data_dir,
                "--timings-out", self.timings_path]
        with self.assertRaises(SystemExit):
            phase1_local.main(argv)

    def test_second_instance_refuses_while_lock_held(self):
        os.makedirs(os.path.dirname(phase1_local.LOCK_PATH), exist_ok=True)
        holder = os.open(phase1_local.LOCK_PATH,
                         os.O_CREAT | os.O_RDWR, 0o644)
        try:
            fcntl.flock(holder, fcntl.LOCK_EX | fcntl.LOCK_NB)
            rc, _, _ = self.run_main()
            self.assertEqual(rc, 3)
        finally:
            fcntl.flock(holder, fcntl.LOCK_UN)
            os.close(holder)


class PercentileTests(unittest.TestCase):
    def test_empty_is_none(self):
        self.assertIsNone(phase1_local.percentile([], 95))

    def test_nearest_rank(self):
        values = list(range(1, 11))          # 1..10
        self.assertEqual(phase1_local.percentile(values, 50), 5)
        self.assertEqual(phase1_local.percentile(values, 95), 10)
        self.assertEqual(phase1_local.percentile(values, 100), 10)
        self.assertEqual(phase1_local.percentile([3.5], 99), 3.5)


if __name__ == "__main__":
    unittest.main()
