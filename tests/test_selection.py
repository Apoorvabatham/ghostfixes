import unittest

from pipeline.selection import SelectionRule, parse_api_datetime

# Fixture values. The FORM is under test here; Bengaluru's concrete values
# are pinned in tests/test_bengaluru_adapter.py against the scope lock.
CATEGORY = "Example Category"
PREFIXES = ("2024-12-31", "2025-01", "2025-02", "2025-03", "2025-04-01")
START, END = "2025-01-01T00:00:00", "2025-04-01T00:00:00"


def rule():
    return SelectionRule(CATEGORY, PREFIXES, START, END)


class ConstructorTests(unittest.TestCase):
    def test_rejects_noncanonical_window_bounds(self):
        with self.assertRaises(ValueError):
            SelectionRule(CATEGORY, PREFIXES, "January 2025", END)

    def test_rejects_end_before_start(self):
        with self.assertRaises(ValueError):
            SelectionRule(CATEGORY, PREFIXES, END, START)

    def test_pad_prefixes_must_be_subset_of_stage_a_prefixes(self):
        with self.assertRaises(ValueError):
            SelectionRule(CATEGORY, PREFIXES, START, END,
                          pad_day_prefixes=("2023-12-31",))


class PadDayTests(unittest.TestCase):
    """csv_date_is_pad: the form the mass-drop guard consumes. The adapter
    declares which prefixes pad; mechanism only classifies."""

    def test_declared_pad_days_match_by_prefix(self):
        padded = SelectionRule(CATEGORY, PREFIXES, START, END,
                               pad_day_prefixes=("2024-12-31", "2025-04-01"))
        self.assertTrue(padded.csv_date_is_pad("2024-12-31 18:00"))
        self.assertTrue(padded.csv_date_is_pad("2025-04-01 09:15"))
        self.assertFalse(padded.csv_date_is_pad("2025-02-05 10:30"))
        self.assertFalse(padded.csv_date_is_pad(""))
        self.assertFalse(padded.csv_date_is_pad(None))

    def test_default_declares_no_pad_days(self):
        self.assertFalse(rule().csv_date_is_pad("2024-12-31 18:00"))


class StageATests(unittest.TestCase):
    def test_exact_category_inside_window(self):
        ok, note = rule().is_stage_a_candidate(CATEGORY, "2025-02-05 10:30")
        self.assertTrue(ok)
        self.assertFalse(note["normalization_fired"])

    def test_padded_category_recorded_not_silent(self):
        ok, note = rule().is_stage_a_candidate(
            " " + CATEGORY + "\t", "2025-02-05 10:30")
        self.assertTrue(ok)
        self.assertTrue(note["normalization_fired"])

    def test_wrong_category_rejected_even_in_window(self):
        ok, _ = rule().is_stage_a_candidate("Electrical", "2025-02-05 10:30")
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
            ok, _ = rule().is_stage_a_candidate(CATEGORY, date)
            self.assertEqual(ok, expected, date)


class ParseTests(unittest.TestCase):
    def test_second_precision_t_separated(self):
        self.assertEqual(parse_api_datetime("2025-02-05T10:30:41"),
                         "2025-02-05T10:30:41")

    def test_minute_precision_space_separated(self):
        self.assertEqual(parse_api_datetime("2025-02-05 10:30"),
                         "2025-02-05T10:30:00")

    def test_unparseable_is_none_never_guessed(self):
        self.assertIsNone(parse_api_datetime("not a date"))
        self.assertIsNone(parse_api_datetime(""))
        self.assertIsNone(parse_api_datetime(None))


class StageBTests(unittest.TestCase):
    def test_window_start_inclusive(self):
        member, parsed = rule().is_stage_b_member("2025-01-01T00:00:00")
        self.assertTrue(member)
        self.assertEqual(parsed, "2025-01-01T00:00:00")

    def test_last_moment_kept_end_exclusive_dropped(self):
        self.assertTrue(rule().is_stage_b_member("2025-03-31T23:59:59")[0])
        self.assertFalse(rule().is_stage_b_member("2025-04-01T00:00:00")[0])

    def test_unparseable_dropped_with_none(self):
        member, parsed = rule().is_stage_b_member("17/03/2025")
        self.assertFalse(member)
        self.assertIsNone(parsed)


class DeltaTests(unittest.TestCase):
    """api_csv_delta_minutes: the keep-side agreement signal's input."""

    def declared_rule(self):
        return SelectionRule(CATEGORY, PREFIXES, START, END,
                             artifact_delta_minutes=(0, 720))

    def test_undeclared_deltas_disable_checking(self):
        self.assertIsNone(rule().api_csv_delta_minutes(
            "2025-02-05T10:30:00", "2025-02-05 10:30"))

    def test_same_moment_is_zero(self):
        self.assertEqual(self.declared_rule().api_csv_delta_minutes(
            "2025-02-05T10:30:00", "2025-02-05 10:30"), 0.0)

    def test_twelve_hour_artifact_is_720(self):
        self.assertEqual(self.declared_rule().api_csv_delta_minutes(
            "2025-02-04T22:30:00", "2025-02-05 10:30"), 720.0)

    def test_any_third_distance_is_measured(self):
        # A timezone-style 5h30m shift must land at 330, not fold into
        # either declared delta.
        self.assertEqual(self.declared_rule().api_csv_delta_minutes(
            "2025-02-05T16:00:00", "2025-02-05 10:30"), 330.0)

    def test_incomparable_sides_return_none_never_verdicts(self):
        r = self.declared_rule()
        self.assertIsNone(r.api_csv_delta_minutes(None, "2025-02-05 10:30"))
        self.assertIsNone(r.api_csv_delta_minutes("2025-02-05T10:30:00",
                                                  None))
        self.assertIsNone(r.api_csv_delta_minutes("2025-02-05T10:30:00",
                                                  "not a date"))

    def test_rejects_bad_declarations(self):
        with self.assertRaises(ValueError):
            SelectionRule(CATEGORY, PREFIXES, START, END,
                          artifact_delta_minutes=())
        with self.assertRaises(ValueError):
            SelectionRule(CATEGORY, PREFIXES, START, END,
                          artifact_delta_minutes=(-30,))
        with self.assertRaises(ValueError):
            SelectionRule(CATEGORY, PREFIXES, START, END,
                          artifact_delta_minutes=(0,),
                          artifact_tolerance_minutes=-1)


if __name__ == "__main__":
    unittest.main()
