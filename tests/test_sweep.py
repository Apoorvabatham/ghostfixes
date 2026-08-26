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
from pipeline.sweep import (BatchHealthGuard, MassDropDegraded,
                            SurfaceDegraded, SurfaceGuard, SweepRunner)

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

    def detail_handler(self, payload_for):
        body = png_bytes()

        def handler(request):
            url = str(request.url)
            if "portal.test/detail" in url:
                tid = int(url.rsplit("/", 1)[1])
                return httpx.Response(200, json=payload_for(tid))
            if "images.test" in url:
                return httpx.Response(200, content=body)
            return httpx.Response(404)
        return handler


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


class GuardTests(Harness):
    """BatchHealthGuard: structural mass-drop detection (the F1 hole — a
    200 with an unusable payload reads as success to SurfaceGuard)."""

    def run_with(self, handler, **kwargs):
        seen = []
        clock = ManualClock()
        client = PortalClient(
            "GhostFixes/test",
            limiter=GlobalLimiter(clock=clock.clock, sleep=clock.sleep),
            transport=httpx.MockTransport(handler))
        health = kwargs.pop("health", None)
        runner = SweepRunner(StubAdapter(), client,
                             SweepJournal(self.jpath), HashLog(self.hpath),
                             self.manifest, health=health)
        self._closables.append(runner.journal)
        self._closables.append(runner.hashlog)
        self._closables.append(client)
        self.runner = runner
        return runner.run(**kwargs)

    def test_unparseable_batch_halts_and_requeues(self):
        # The F1 signature exactly: 200 + valid JSON, but the consumed
        # fields read from the wrong level, so no filing timestamp exists.
        def payload_for(tid):
            return {"Id": str(tid), "Status": "Closed"}
        health = BatchHealthGuard(RULE, batch_size=5)
        with self.assertRaises(MassDropDegraded) as ctx:
            self.run_with(self.detail_handler(payload_for), health=health)
        suspects = set(ctx.exception.suspect_ticket_ids)
        self.assertEqual(len(suspects), 5)
        states = {t: r["state"] for t, r in
                  self.runner.journal.state_map().items()}
        for tid in suspects:
            # Requeued, not terminally dropped: resume must re-decide them.
            self.assertEqual(states[tid], "failed")

    def test_parseable_mass_drop_below_keep_floor_halts_and_requeues(self):
        # Parseable dates outside the window, CSV dates on no pad day:
        # legitimate-looking drops at a structurally impossible rate.
        def payload_for(tid):
            return {"Id": str(tid), "Filed": "2024-06-01T00:00:00",
                    "Status": "Closed", "Images": []}
        health = BatchHealthGuard(RULE, batch_size=5)
        with self.assertRaises(MassDropDegraded) as ctx:
            self.run_with(self.detail_handler(payload_for), health=health)
        suspects = set(ctx.exception.suspect_ticket_ids)
        self.assertEqual(len(suspects), 5)
        states = {t: r["state"] for t, r in
                  self.runner.journal.state_map().items()}
        for tid in suspects:
            self.assertEqual(states[tid], "failed")

    def test_all_pad_batch_never_fires(self):
        # Every drop is a declared pad-day candidate carrying a parseable
        # API date: expected membership facts, not a health signal.
        pad_rule = SelectionRule(
            CAT, ("2024-12", "2025-01"), "2025-01-01T00:00:00",
            "2025-03-01T00:00:00", pad_day_prefixes=("2024-12",))
        stub = StubAdapter()
        stub.selection = pad_rule
        stub.parse_csv_row = lambda r: CsvRow(
            r["Complaint ID"], r["Category"], r["Grievance Date"])
        rows = [{"Complaint ID": str(t), "Category": CAT,
                 "Grievance Date": "2024-12-05 09:00"}
                for t in range(200, 205)]
        cands, _ = build_candidates(stub, [("2024", rows)])
        clock = ManualClock()
        client = PortalClient(
            "GhostFixes/test",
            limiter=GlobalLimiter(clock=clock.clock, sleep=clock.sleep),
            transport=httpx.MockTransport(self.detail_handler(
                lambda tid: {"Id": str(tid),
                             "Filed": "2024-12-05T08:00:00"})))
        runner = SweepRunner(stub, client, SweepJournal(self.jpath),
                             HashLog(self.hpath), cands)
        self._closables.append(runner.journal)
        self._closables.append(runner.hashlog)
        self._closables.append(client)
        stats = runner.run()
        self.assertEqual(stats["api_dropped"], 5)
        self.assertEqual(stats["scrape_done"], 0)

    def test_healthy_batch_completes_and_finalizes(self):
        stats = self.run_with(self.detail_handler(payloads_for))
        self.assertEqual(stats["scrape_done"], 4)
        self.assertEqual(stats["api_dropped"], 1)

    def test_request_budget_stops_crash_shaped_without_finalize(self):
        # A budgeted CI batch hands over mid-corpus: the stop must not
        # synthesize a trailing-batch evaluation from a partial series.
        stats = self.run_with(self.detail_handler(payloads_for),
                              request_budget=1)
        self.assertEqual(stats["candidates"], 1)
        # Reaching here without MassDropDegraded is itself the assertion:
        # the partial series stayed unevaluated.

    def test_limit_stop_does_not_evaluate_partial_batch(self):
        # Below batch_size and not exhaustion: a limit stop is crash-shaped,
        # and no evaluation may synthesize itself from a partial series.
        def payload_for(tid):
            return {"Id": str(tid), "Filed": "2024-06-01T00:00:00"}
        stats = self.run_with(
            self.detail_handler(payload_for),
            health=BatchHealthGuard(RULE, batch_size=10), limit=2)
        self.assertEqual(stats["candidates"], 2)


class AgreementGuardTests(Harness):
    """Signal 3: API-vs-CSV agreement — the keep-side F1 mirror. A misread
    field landing inside the window keeps every ticket silently; only the
    declared artifact distances can tell reads from data."""

    N = 24

    def setUp(self):
        super().setUp()
        self.rule_d = SelectionRule(
            CAT, ("2025-01",), "2025-01-01T00:00:00",
            "2025-03-01T00:00:00", artifact_delta_minutes=(0, 720))
        stub = StubAdapter()
        stub.selection = self.rule_d
        stub.parse_csv_row = lambda r: CsvRow(
            r["Complaint ID"], r["Category"], r["Grievance Date"])
        rows = [{"Complaint ID": str(t), "Category": CAT,
                 "Grievance Date": "2025-01-05 09:00"}
                for t in range(300, 300 + self.N)]
        self.manifest_d, _ = build_candidates(stub, [("2025", rows)])

    def run_declared(self, payload_for, expect_halt):
        clock = ManualClock()
        client = PortalClient(
            "GhostFixes/test",
            limiter=GlobalLimiter(clock=clock.clock, sleep=clock.sleep),
            transport=httpx.MockTransport(self.detail_handler(payload_for)))
        stub = StubAdapter()
        stub.selection = self.rule_d
        runner = SweepRunner(stub, client,
                             SweepJournal(self.jpath), HashLog(self.hpath),
                             self.manifest_d,
                             health=BatchHealthGuard(self.rule_d,
                                                     batch_size=self.N))
        self._closables.append(runner.journal)
        self._closables.append(runner.hashlog)
        self._closables.append(client)
        self.runner = runner
        if expect_halt:
            with self.assertRaises(MassDropDegraded) as ctx:
                runner.run()
            return ctx
        return runner.run()

    def test_agreeing_timestamps_run_silent(self):
        # Second-precision API vs minute CSV, sub-tolerance distance.
        def payload_for(tid):
            return {"Id": str(tid), "Filed": "2025-01-05T09:00:30",
                    "Status": "Closed", "Images": []}
        stats = self.run_declared(payload_for, expect_halt=False)
        self.assertEqual(stats["scrape_done"], self.N)

    def test_corrupted_keeps_fire_and_requeue(self):
        # Every ticket parses fine and stays IN the window — kept — but its
        # API-vs-CSV distance (5h30m) belongs to no declared artifact.
        # Neither signal 1 nor signal 2 can see this; signal 3 must.
        def payload_for(tid):
            return {"Id": str(tid), "Filed": "2025-01-05T14:30:00",
                    "Status": "Closed", "Images": []}
        ctx = self.run_declared(payload_for, expect_halt=True)
        suspects = set(ctx.exception.suspect_ticket_ids)
        self.assertEqual(len(suspects), self.N)
        states = {t: r["state"] for t, r in
                  self.runner.journal.state_map().items()}
        for tid in suspects:
            self.assertEqual(states[tid], "failed")
        # The requeued tickets really were keeps before the halt.
        kept_before = [json.loads(l) for l in open(self.jpath)]
        self.assertTrue(any(r["state"] == "api_kept" for r in kept_before))

    def test_subthreshold_disagreement_stays_silent(self):
        one_bad = {str(300): {"Id": "300", "Filed": "2025-01-05T14:30:00",
                              "Status": "Closed", "Images": []}}

        def payload_for(tid):
            return one_bad.get(str(tid)) or {
                "Id": str(tid), "Filed": "2025-01-05T09:00:30",
                "Status": "Closed", "Images": []}
        stats = self.run_declared(payload_for, expect_halt=False)
        self.assertEqual(stats["scrape_done"], self.N)

    def test_trailing_batch_halt_at_finalize_still_requeues(self):
        # Regression (review blocker): the halt fires from finalize() at
        # natural exhaustion, outside the per-ticket try block. The requeue
        # must happen there too, or corrupt keeps ship as terminal.
        self.N_SMALL = 12

        def payload_for(tid):
            return {"Id": str(tid), "Filed": "2025-01-05T14:30:00",
                    "Status": "Closed", "Images": []}
        clock = ManualClock()
        client = PortalClient(
            "GhostFixes/test",
            limiter=GlobalLimiter(clock=clock.clock, sleep=clock.sleep),
            transport=httpx.MockTransport(self.detail_handler(payload_for)))
        stub = StubAdapter()
        stub.selection = self.rule_d
        # batch_size far above N: evaluation can only happen at finalize().
        runner = SweepRunner(stub, client, SweepJournal(self.jpath),
                             HashLog(self.hpath), self.manifest_d,
                             health=BatchHealthGuard(self.rule_d,
                                                     batch_size=100))
        self._closables.append(runner.journal)
        self._closables.append(runner.hashlog)
        self._closables.append(client)
        with self.assertRaises(MassDropDegraded) as ctx:
            runner.run()
        suspects = set(ctx.exception.suspect_ticket_ids)
        self.assertEqual(len(suspects), len(self.manifest_d))
        states = {t: r["state"] for t, r in
                  runner.journal.state_map().items()}
        for tid in suspects:
            self.assertEqual(states[tid], "failed")

    def test_mixed_fault_reports_all_and_requeues_everyone(self):
        # Signal 2 and signal 3 fire together: out-of-window parseable
        # drops AND disagreeing in-window keeps. No masking — one halt
        # naming both conditions, every decided ticket requeued.
        drops = {str(t): {"Id": str(t), "Filed": "2024-06-01T00:00:00",
                          "Status": "Closed", "Images": []}
                 for t in range(300, 320)}
        bad_keeps = {str(t): {"Id": str(t),
                              "Filed": "2025-01-05T14:30:00",
                              "Status": "Closed", "Images": []}
                     for t in range(320, 324)}

        def payload_for(tid):
            return drops.get(str(tid)) or bad_keeps[str(tid)]
        clock = ManualClock()
        client = PortalClient(
            "GhostFixes/test",
            limiter=GlobalLimiter(clock=clock.clock, sleep=clock.sleep),
            transport=httpx.MockTransport(self.detail_handler(payload_for)))
        stub = StubAdapter()
        stub.selection = self.rule_d
        rows_rule_manifest = self.manifest_d
        runner = SweepRunner(stub, client, SweepJournal(self.jpath),
                             HashLog(self.hpath), rows_rule_manifest,
                             health=BatchHealthGuard(self.rule_d,
                                                     batch_size=24))
        self._closables.append(runner.journal)
        self._closables.append(runner.hashlog)
        self._closables.append(client)
        with self.assertRaises(MassDropDegraded) as ctx:
            runner.run()
        message = str(ctx.exception)
        self.assertIn("kept among non-pad candidates", message)
        self.assertIn("API-vs-CSV distances", message)
        suspects = set(ctx.exception.suspect_ticket_ids)
        self.assertEqual(len(suspects), 24)
        states = {t: r["state"] for t, r in
                  runner.journal.state_map().items()}
        for tid in suspects:
            self.assertEqual(states[tid], "failed")

    def test_exact_threshold_fraction_fires(self):
        # >= semantics: exactly AGREEMENT_MAX_FRAC (1/20 = 5%) must fire,
        # with MIN_COMPARED satisfied exactly.
        n_agree = [f"{t}" for t in range(300, 319)]

        def payload_for(tid):
            if str(tid) == "319":
                return {"Id": str(tid), "Filed": "2025-01-05T14:30:00",
                        "Status": "Closed", "Images": []}
            return {"Id": str(tid), "Filed": "2025-01-05T09:00:30",
                    "Status": "Closed", "Images": []}
        clock = ManualClock()
        client = PortalClient(
            "GhostFixes/test",
            limiter=GlobalLimiter(clock=clock.clock, sleep=clock.sleep),
            transport=httpx.MockTransport(self.detail_handler(payload_for)))
        stub = StubAdapter()
        stub.selection = self.rule_d
        runner = SweepRunner(stub, client, SweepJournal(self.jpath),
                             HashLog(self.hpath), self.manifest_d[:20],
                             health=BatchHealthGuard(self.rule_d,
                                                     batch_size=20))
        self._closables.append(runner.journal)
        self._closables.append(runner.hashlog)
        self._closables.append(client)
        with self.assertRaises(MassDropDegraded) as ctx:
            runner.run()
        self.assertEqual(len(set(ctx.exception.suspect_ticket_ids)), 20)

    def test_below_min_compared_cannot_fire_signal_three(self):
        # Documented limitation: a trailing batch smaller than
        # MIN_COMPARED never fires signal 3 regardless of disagreement.
        small_manifest = self.manifest_d[:12]

        def payload_for(tid):
            return {"Id": str(tid), "Filed": "2025-01-05T14:30:00",
                    "Status": "Closed", "Images": []}
        clock = ManualClock()
        client = PortalClient(
            "GhostFixes/test",
            limiter=GlobalLimiter(clock=clock.clock, sleep=clock.sleep),
            transport=httpx.MockTransport(self.detail_handler(payload_for)))
        stub = StubAdapter()
        stub.selection = self.rule_d
        runner = SweepRunner(stub, client, SweepJournal(self.jpath),
                             HashLog(self.hpath), small_manifest,
                             health=BatchHealthGuard(self.rule_d,
                                                     batch_size=100))
        self._closables.append(runner.journal)
        self._closables.append(runner.hashlog)
        self._closables.append(client)
        stats = runner.run()          # completes clean, by design
        self.assertEqual(stats["scrape_done"], 12)


if __name__ == "__main__":
    unittest.main()


class HeartbeatTests(Harness):
    def test_progress_callback_fires_per_n_candidates(self):
        seen = []
        clock = ManualClock()
        client = PortalClient(
            "GhostFixes/test",
            limiter=GlobalLimiter(clock=clock.clock, sleep=clock.sleep),
            transport=make_transport([]))
        runner = SweepRunner(StubAdapter(), client,
                             SweepJournal(self.jpath), HashLog(self.hpath),
                             self.manifest)
        runner.run(progress_every=2, on_progress=seen.append)
        self.assertGreaterEqual(len(seen), 2)
        self.assertIn("requests_made", seen[0])
        client.close()
