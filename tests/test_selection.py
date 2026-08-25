import unittest

from pipeline import selection as sel


class StageATests(unittest.TestCase):
    def test_exact_category_inside_window(self):
        ok, note = sel.is_stage_a_candidate(sel.CATEGORY, "2025-02-05 10:30")
        self.assertTrue(ok)
        self.assertFalse(note["normalization_fired"])

    def test_padded_category_recorded_not_silent(self):
        ok, note = sel.is_stage_a_candidate(" " + sel.CATEGORY + "\t",
                                            "2025-02-05 10:30")
        self.assertTrue(ok)
        self.assertTrue(note["normalization_fired"])

    def test_wrong_category_rejected_even_in_window(self):
        ok, _ = sel.is_stage_a_candidate("Electrical", "2025-02-05 10:30")
        self.assertFalse(ok)

    def test_date_padding_boundaries(self):
        cases = {
            "2024-12-30 23:59": False,   # beyond the ±1 day pad
            "2024-12-31 00:00": True,    # pad edge below
            "2025-01-01 00:00": True,
            "2025-03-31 23:59": True,
            "2025-04-01 12:00": True,    # pad edge above
            "2025-04-02 00:00": False,
            "2024-06-01 08:00": False,
        }
        for date, expected in cases.items():
            ok, _ = sel.is_stage_a_candidate(sel.CATEGORY, date)
            self.assertEqual(ok, expected, date)


class ParseTests(unittest.TestCase):
    def test_second_precision_t_separated(self):
        self.assertEqual(sel.parse_api_datetime("2025-02-05T10:30:41"),
                         "2025-02-05T10:30:41")

    def test_minute_precision_space_separated(self):
        self.assertEqual(sel.parse_api_datetime("2025-02-05 10:30"),
                         "2025-02-05T10:30:00")

    def test_unparseable_is_none_never_guessed(self):
        self.assertIsNone(sel.parse_api_datetime("not a date"))
        self.assertIsNone(sel.parse_api_datetime(""))
        self.assertIsNone(sel.parse_api_datetime(None))


class StageBTests(unittest.TestCase):
    def test_window_start_inclusive(self):
        member, parsed = sel.is_stage_b_member("2025-01-01T00:00:00")
        self.assertTrue(member)
        self.assertEqual(parsed, "2025-01-01T00:00:00")

    def test_last_moment_kept_end_exclusive_dropped(self):
        self.assertTrue(sel.is_stage_b_member("2025-03-31T23:59:59")[0])
        self.assertFalse(sel.is_stage_b_member("2025-04-01T00:00:00")[0])

    def test_unparseable_dropped_with_none(self):
        member, parsed = sel.is_stage_b_member("17/03/2025")
        self.assertFalse(member)
        self.assertIsNone(parsed)


if __name__ == "__main__":
    unittest.main()
