import json
import os
import tempfile
import unittest

import httpx

from pipeline.fetcher import PortalClient
from pipeline.hashing import HashLog
from pipeline.journal import SweepJournal
from pipeline.limiter import GlobalLimiter
from pipeline.manifest import build_candidates
from pipeline.selection import SelectionRule
from pipeline.adapter_api import CsvRow, ImageFetch, TicketDetail
from pipeline.sweep import SurfaceDegraded, SurfaceGuard, SweepRunner

CAT = "Example Category"
RULE = SelectionRule(CAT, ("2025-01", "2025-02"), "2025-01-01T00:00:00",
                     "2025-03-01T00:00:00")


def png_bytes():
    import io
    from PIL import Image
    img = Image.new("L", (8, 8), 90)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class StubAdapter:
    """Duck-typed adapter for mechanism tests — no portal knowledge."""

    name = "stub"
    selection = RULE
    IMAGE = "https://images.test/staff/1.png"

    def detail_url(self, ticket_id):
        return f"https://portal.test/detail/{ticket_id}"

    def parse_detail(self, payload):
        return TicketDetail(
            ticket_id=str(payload.get("Id") or ""),
            ward=payload.get("Ward"),
            category=payload.get("Cat"),
            filed_at_raw=payload.get("Filed"),
            citizen_status=payload.get("Status"),
            image_urls=tuple(payload.get("Images") or ()),
        )

    def image_plan(self, url):
        return ImageFetch(url=url, verify_tls=True)


class ManualClock:
    """Deterministic time: sleeps advance the clock without waiting."""

    def __init__(self, start=1000.0):
        self.now = start
        self.sleeps = []

    def clock(self):
        return self.now

    def sleep(self, duration):
        self.sleeps.append(duration)
        self.now += duration


def payloads_for(tid):
    if tid % 10 == 7:                       # deterministic outside-window ids
        return {"Id": str(tid), "Filed": "2024-06-01T00:00:00",
                "Status": "Closed", "Images": []}
    return {"Id": str(tid), "Filed": "2025-01-15T10:00:00", "Ward": "W1",
            "Cat": CAT, "Status": "Closed", "Images": [StubAdapter.IMAGE]}


def make_transport(seen):
    body = png_bytes()

    def handler(request):
        seen.append(request)
        url = str(request.url)
        if "portal.test/detail" in url:
            tid = int(url.rsplit("/", 1)[1])
            return httpx.Response(200, json=payloads_for(tid))
        if "images.test" in url:
            return httpx.Response(200, content=body)
        return httpx.Response(404)
    return httpx.MockTransport(handler)


class Harness(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._closables = []
        self.jpath = os.path.join(self.tmp.name, "journal.jsonl")
        self.hpath = os.path.join(self.tmp.name, "hashes.jsonl")
        stub = StubAdapter()
        stub.parse_csv_row = lambda r: CsvRow(
            r["Complaint ID"], r["Category"], r["Grievance Date"])
        # One id ends in 7 -> deterministic api_dropped case.
        rows = [{"Complaint ID": str(t), "Category": CAT,
                 "Grievance Date": "2025-01-05 09:00"}
                for t in (100, 101, 102, 103, 107)]
        cands, dups = build_candidates(stub, [("2025", rows)])
        self.assertEqual(dups, 0)
        self.manifest = cands

    def tearDown(self):
        for closable in self._closables:
            closable.close()
        self.tmp.cleanup()

    def make_runner(self, seen=None):
        clock = ManualClock()
        limiter = GlobalLimiter(clock=clock.clock, sleep=clock.sleep)
        client = PortalClient("GhostFixes/test", limiter=limiter,
                              transport=make_transport(seen or []))
        runner = SweepRunner(StubAdapter(), client,
                             SweepJournal(self.jpath), HashLog(self.hpath),
                             self.manifest)
        self._closables.append(runner.journal)
        self._closables.append(runner.hashlog)
        self._closables.append(client)
        return runner


class SweepTests(Harness):
    def test_happy_path_states_and_hashes(self):
        runner = self.make_runner()
        stats = runner.run()
        self.assertEqual(stats["api_dropped"], 1)      # ids ending in 7
        self.assertEqual(stats["scrape_done"], 4)
        jstates = {t: r["state"] for t, r in
                   runner.journal.state_map().items()}
        self.assertEqual(jstates["101"], "scrape_done")
        self.assertEqual(jstates["107"], "api_dropped")
        records = [json.loads(l) for l in open(self.hpath)]
        self.assertEqual(len(records), 4)

    def test_journal_records_carry_whitelist_keys_only(self):
        runner = self.make_runner()
        runner.run()
        allowed = {"ticket_id", "ts_utc", "state", "api_date",
                   "api_date_raw", "csv_date_raw", "ward", "category",
                   "sub_category", "citizen_status", "staff_status",
                   "image_urls", "images_hashed", "images_failed_object"}
        for line in open(self.jpath):
            extra = set(json.loads(line)) - allowed
            self.assertEqual(extra, set())

    def test_resume_is_exact_once(self):
        seen = []
        runner = self.make_runner(seen)
        runner.run(limit=1)                 # crash after first candidate
        first = sum(1 for _ in open(self.hpath))
        self.assertEqual(first, 1)
        runner2 = self.make_runner(seen)
        stats = runner2.run()
        self.assertEqual(stats["scrape_done"], 3)
        self.assertEqual(stats["already_done"], 1)
        lines = [json.loads(l) for l in open(self.hpath)]
        self.assertEqual(len(lines), 4)     # no duplicate hash record
        pairs = {(r["ticket_id"], r["url"]) for r in lines}
        self.assertEqual(len(pairs), 4)

    def test_detail_auth_wall_halts_via_guard(self):
        seen = []

        def handler(request):
            seen.append(request)
            if "portal.test/detail" in str(request.url):
                return httpx.Response(403, json={"m": "Forbidden"})
            return httpx.Response(200, content=png_bytes())
        clock = ManualClock()
        client = PortalClient(
            "GhostFixes/test",
            limiter=GlobalLimiter(clock=clock.clock, sleep=clock.sleep),
            transport=httpx.MockTransport(handler))
        runner = SweepRunner(StubAdapter(), client,
                             SweepJournal(self.jpath), HashLog(self.hpath),
                             self.manifest)
        with self.assertRaises(SurfaceDegraded):
            runner.run()
        failed = [r for r in runner.journal.state_map().values()
                  if r["state"] == "failed"]
        self.assertEqual(len(failed), 5)    # guard limit reached, then halt


class ObjectFailureTests(Harness):
    def test_image_403_recorded_not_guarded(self):
        seen = []

        def handler(request):
            seen.append(request)
            if "images.test" in str(request.url):
                return httpx.Response(403, text="AccessDenied")
            return httpx.Response(200, json=payloads_for(
                int(str(request.url).rsplit("/", 1)[1])))
        clock = ManualClock()
        client = PortalClient(
            "GhostFixes/test",
            limiter=GlobalLimiter(clock=clock.clock, sleep=clock.sleep),
            transport=httpx.MockTransport(handler))
        runner = SweepRunner(StubAdapter(), client,
                             SweepJournal(self.jpath), HashLog(self.hpath),
                             self.manifest)
        stats = runner.run()
        self.assertEqual(stats["scrape_done"], 4)
        self.assertEqual(stats["images_failed_object"], 4)
        self.assertEqual(len(open(self.hpath).readlines()), 0)

    def test_request_count_matches_per_ticket_plan(self):
        runner = self.make_runner()
        runner.run()
        # 5 detail calls + 4 image calls (one ticket dropped has no images).
        self.assertEqual(runner.client.requests_made, 9)


if __name__ == "__main__":
    unittest.main()
