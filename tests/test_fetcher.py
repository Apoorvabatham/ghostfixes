import json
import unittest

import httpx

from adapters.bengaluru import ADAPTER
from pipeline.fetcher import PortalClient
from pipeline.limiter import GlobalLimiter

UA = "GhostFixes/0.0-test (+https://example.invalid; contact: test@example.invalid)"


class ManualClock:
    def __init__(self, start=100.0):
        self.now = start
        self.sleeps = []

    def clock(self):
        return self.now

    def sleep(self, duration):
        self.sleeps.append(duration)
        self.now += duration


def make_transport(seen, detail_body):
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if "GetComplaintDetailforCitizen" in str(request.url):
            return httpx.Response(200, json=detail_body)
        return httpx.Response(200, content=b"\xff\xd8jpgbytes")
    return httpx.MockTransport(handler)


DETAIL = {"GrievanceId": 20446742, "GrievanceDate": "2025-02-05T10:30:41"}


class FetchDetailTests(unittest.TestCase):
    def test_hits_adapter_url_with_honest_ua(self):
        seen = []
        with PortalClient(UA, transport=make_transport(seen, DETAIL)) as pc:
            resp = pc.fetch_detail(ADAPTER, 20446742)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["GrievanceId"], 20446742)
        self.assertEqual(str(seen[0].url), ADAPTER.detail_url("20446742"))
        self.assertEqual(seen[0].headers["User-Agent"], UA)


class FetchImageTests(unittest.TestCase):
    def test_unfetchable_plan_short_circuits_without_request(self):
        seen = []
        with PortalClient(UA, transport=make_transport(seen, DETAIL)) as pc:
            self.assertIsNone(pc.fetch_image(ADAPTER, "ftp://x/y.jpg"))
        self.assertEqual(seen, [])

    def test_image_url_passes_through_adapter_plan(self):
        seen = []
        url = ("https://sahaaya2.bbmpgov.in/ProjectImages/"
               "GrievanceImages/1/a.jpg")
        with PortalClient(UA, transport=make_transport(seen, DETAIL)) as pc:
            resp = pc.fetch_image(ADAPTER, url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(str(seen[0].url), url)


class ClientPolicyTests(unittest.TestCase):
    def test_one_client_per_trust_level(self):
        with PortalClient(UA) as pc:
            a = pc.client_for(True)
            b = pc.client_for(False)
            self.assertIs(a, pc.client_for(True))
            self.assertIsNot(a, b)

    def test_user_agent_required(self):
        with self.assertRaises(ValueError):
            PortalClient("")


class LimiterWiringTests(unittest.TestCase):
    def test_second_request_waits_full_interval(self):
        seen, fc = [], ManualClock()
        lim = GlobalLimiter(clock=fc.clock, sleep=fc.sleep)
        transport = make_transport(seen, DETAIL)
        with PortalClient(UA, limiter=lim,
                          transport=transport) as pc:
            pc.fetch_detail(ADAPTER, 1)
            pc.fetch_detail(ADAPTER, 2)
        self.assertEqual(fc.sleeps, [3.0])
        self.assertEqual(len(seen), 2)


class RedirectPolicyTests(unittest.TestCase):
    def test_3xx_is_returned_not_followed(self):
        # Pre-probe review (2026-08-26): following a redirect chain puts
        # un-gated wire requests on the network inside one limiter window
        # (invariant 5) and hides them from request accounting. A 3xx is
        # returned to the caller as the recorded fact it is.
        seen = []

        def handler(request):
            seen.append(request)
            return httpx.Response(
                302, headers={"Location": "https://portal.test/elsewhere"})

        fc = ManualClock()
        with PortalClient(UA, limiter=GlobalLimiter(clock=fc.clock,
                                                    sleep=fc.sleep),
                          transport=httpx.MockTransport(handler)) as pc:
            resp = pc.get_bytes("https://portal.test/start")
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.headers["Location"],
                         "https://portal.test/elsewhere")
        self.assertEqual(len(seen), 1)      # one gated request, no chase
        self.assertEqual(fc.sleeps, [])     # no second gate entry either


if __name__ == "__main__":
    unittest.main()
