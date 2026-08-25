import os
import tempfile
import unittest

from pipeline.journal import (SweepJournal, TransitionError, FAILED)


class JournalTests(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".jsonl")
        os.close(fd)
        os.remove(self.path)  # SweepJournal appends; start absent

    def tearDown(self):
        for p in (self.path,):
            if os.path.exists(p):
                os.remove(p)

    def test_roundtrip_across_instances(self):
        j1 = SweepJournal(self.path)
        j1.append(20446742, "api_kept", api_date="2025-02-05T10:30:41",
                  csv_date="2025-02-05 10:30")
        j1.close()
        j2 = SweepJournal(self.path)
        self.assertEqual(j2.state_of(20446742), "api_kept")
        self.assertEqual(j2.state_map()[str(20446742)]["api_date"],
                         "2025-02-05T10:30:41")

    def test_full_forward_chain_allowed(self):
        j = SweepJournal(self.path)
        for st in ("candidate", "api_kept", "scrape_done",
                   "archive_queued", "archive_done"):
            j.append("t1", st)

    def test_regression_raises(self):
        j = SweepJournal(self.path)
        j.append("t1", "scrape_done")
        with self.assertRaises(TransitionError):
            j.append("t1", "api_kept")
        with self.assertRaises(TransitionError):
            j.append("t1", "scrape_done")

    def test_terminal_states_refuse_everything(self):
        j = SweepJournal(self.path)
        j.append("t1", "archive_done")
        with self.assertRaises(TransitionError):
            j.append("t1", "archive_done")
        j.append("t2", "api_dropped")
        with self.assertRaises(TransitionError):
            j.append("t2", "scrape_done")

    def test_failure_recordable_anywhere_and_retry_allowed(self):
        j = SweepJournal(self.path)
        j.append("t1", "scrape_done")
        j.append("t1", FAILED, error="connection reset")   # from mid-chain
        j.append("t1", "scrape_done")                      # retry re-enters
        j.append("t2", FAILED)                             # from nothing
        self.assertEqual(j.state_of("t2"), FAILED)

    def test_branch_switch_kept_to_dropped_forbidden(self):
        j = SweepJournal(self.path)
        j.append("t1", "api_kept")
        with self.assertRaises(TransitionError):
            j.append("t1", "api_dropped")

    def test_corrupt_line_raises_valueerror_loudly(self):
        with open(self.path, "w", encoding="utf-8") as fh:
            fh.write('{"ticket_id": "t1", "state": "api_kept"}\n')
            fh.write("{corrupt json\n")
        with self.assertRaises(ValueError):
            SweepJournal(self.path).counts()

    def test_counts(self):
        j = SweepJournal(self.path)
        j.append("a", "api_kept")
        j.append("b", "api_kept")
        j.append("c", "api_dropped")
        j.append("d", FAILED)
        self.assertEqual(j.counts(), {"api_kept": 2, "api_dropped": 1,
                                      FAILED: 1})


if __name__ == "__main__":
    unittest.main()
