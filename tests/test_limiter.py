import threading
import time
import unittest

from pipeline.limiter import GlobalLimiter


class FakeClock:
    def __init__(self, start=100.0):
        self.now = start
        self.sleeps = []

    def clock(self):
        return self.now

    def sleep(self, duration):
        self.sleeps.append(duration)
        self.now += duration


class StartRateTests(unittest.TestCase):
    def test_first_request_sleeps_not_at_all(self):
        fc = FakeClock()
        lim = GlobalLimiter(clock=fc.clock, sleep=fc.sleep)
        with lim.request():
            pass
        self.assertEqual(fc.sleeps, [])

    def test_immediate_second_request_waits_full_interval(self):
        fc = FakeClock()
        lim = GlobalLimiter(clock=fc.clock, sleep=fc.sleep)
        with lim.request():
            pass
        with lim.request():
            pass
        self.assertEqual(fc.sleeps, [3.0])

    def test_burst_of_three_from_t0(self):
        fc = FakeClock()
        lim = GlobalLimiter(clock=fc.clock, sleep=fc.sleep)
        for _ in range(3):
            with lim.request():
                pass
        self.assertEqual(fc.sleeps, [3.0, 3.0])
        self.assertAlmostEqual(fc.now, 106.0)


class InFlightCapTests(unittest.TestCase):
    def test_second_request_blocked_until_first_released(self):
        # Real clock, tiny interval: exercises the actual semaphore path.
        lim = GlobalLimiter(min_interval=0.01, max_in_flight=1)
        entered_first = threading.Event()
        release_first = threading.Event()
        entered_second = threading.Event()

        def first():
            with lim.request():
                entered_first.set()
                release_first.wait(5)

        t1 = threading.Thread(target=first, daemon=True)
        t1.start()
        self.assertTrue(entered_first.wait(5))

        def second():
            with lim.request():
                entered_second.set()

        t2 = threading.Thread(target=second, daemon=True)
        t2.start()
        self.assertFalse(entered_second.wait(0.25),
                         "second request entered despite in-flight cap")
        release_first.set()
        self.assertTrue(entered_second.wait(5))
        t1.join(5)
        t2.join(5)


if __name__ == "__main__":
    unittest.main()
