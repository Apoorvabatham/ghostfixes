import unittest
from dataclasses import fields

from pipeline.adapter_api import TicketDetail, check_adapter
from adapters.bengaluru import (
    ADAPTER, CATEGORY, CSV_DATE_PREFIXES, DETAIL_URL_TEMPLATE,
    WINDOW_END_EXCLUSIVE, WINDOW_START, parse_staff_filename,
)

# Synthetic payload: invented PII values prove they never survive
# parsing (invariant 1); nothing here is persisted.
PAYLOAD = {
    "GrievanceId": 20446742,
    "CategoryEnglish": CATEGORY,
    "SubCategoryEnglish": "Garbage dump",
    "GrievanceDate": "2025-02-05T10:30:41",
    "Ward": "  Ward-12  ",
}
PAYLOAD["Address"] = "No 4, Example Street"
PAYLOAD["Description"] = "pile not cleared"
PAYLOAD["ImagePath"] = (
    "https://nammabengaluru.s3.ap-south-1.amazonaws.com/"
    "Sahaaya-Stg/Grievance/Images/20446742_1.jpg")
PAYLOAD["AudioPath"] = None
PAYLOAD["VideoPath"] = "null"
PAYLOAD["ComplaintStatus"] = "Closed"
PAYLOAD["staffComplaintDetails"] = {
    "GrievanceStatus": "Closed",
    "StaffRemarks": "cleared it",
    "StaffName": "Example Name",
    "ContactDetails": "9999999999",
    "StaffRecentAddedImage": (
        "https://sahaaya2.bbmpgov.in/ProjectImages/"
        "GrievanceImages/20446742/2025 2 6 9 15 30.jpg"),
}


class ContractTests(unittest.TestCase):
    def test_conformance_self_check_clean(self):
        self.assertEqual(check_adapter(ADAPTER), [])

    def test_scope_lock_constants_verbatim(self):
        self.assertEqual(CATEGORY, "Solid Waste (Garbage) Related")
        self.assertEqual(CSV_DATE_PREFIXES[0], "2024-12-31")
        self.assertEqual(CSV_DATE_PREFIXES[-1], "2025-04-01")
        self.assertEqual(WINDOW_START, "2025-01-01T00:00:00")
        self.assertEqual(WINDOW_END_EXCLUSIVE, "2025-04-01T00:00:00")

    def test_selection_rule_wired_to_adapter(self):
        self.assertIs(ADAPTER.selection.category, CATEGORY)
        self.assertEqual(ADAPTER.selection.window_start, WINDOW_START)


class DetailUrlTests(unittest.TestCase):
    def test_route_typo_preserved_and_id_substituted(self):
        url = ADAPTER.detail_url("20446742")
        self.assertIn(
            "GetComplaintDetailforCitizen?ComaplaintID=20446742", url)
        self.assertTrue(url.startswith("https://sahaaya2.bbmp.gov.in/"))


class ParseDetailTests(unittest.TestCase):
    def test_whitelist_fields_extracted(self):
        detail = ADAPTER.parse_detail(PAYLOAD)
        self.assertEqual(detail.ticket_id, "20446742")
        self.assertEqual(detail.ward, "Ward-12")
        self.assertEqual(detail.category, CATEGORY)
        self.assertEqual(detail.sub_category, "Garbage dump")
        self.assertEqual(detail.filed_at_raw, "2025-02-05T10:30:41")
        self.assertEqual(detail.citizen_status, "Closed")
        self.assertEqual(detail.staff_status, "Closed")

    def test_both_image_urls_kept_in_order(self):
        detail = ADAPTER.parse_detail(PAYLOAD)
        self.assertEqual(len(detail.image_urls), 2)
        self.assertIn("s3.ap-south-1.amazonaws.com", detail.image_urls[0])
        self.assertIn("bbmpgov.in", detail.image_urls[1])

    def test_invariant1_forbidden_fields_do_not_exist(self):
        names = {f.name for f in fields(TicketDetail)}
        for banned in ("address", "description", "staff_name",
                       "contact_details", "staff_remarks", "audio", "video"):
            self.assertFalse(any(banned in n for n in names), banned)

    def test_invariant1_pii_never_survives_parsing(self):
        rendered = repr(ADAPTER.parse_detail(PAYLOAD))
        for secret in ("Example Street", "Example Name", "9999999999",
                       "cleared it", "pile not cleared"):
            self.assertNotIn(secret, rendered)

    def test_null_literal_and_missing_staff_block_tolerated(self):
        bare = {"GrievanceId": 7, "ImagePath": "null"}
        detail = ADAPTER.parse_detail(bare)
        self.assertEqual(detail.ticket_id, "7")
        self.assertIsNone(detail.staff_status)
        self.assertEqual(detail.image_urls, ())
        self.assertEqual(ADAPTER.parse_detail(None).ticket_id, "")


class ImagePlanTests(unittest.TestCase):
    S3 = "https://nammabengaluru.s3.ap-south-1.amazonaws.com/x.jpg"
    DOTTED = "https://sahaaya2.bbmp.gov.in/Webapi/ProjectImages/a.jpg"

    def test_one_word_host_uses_documented_loose_tls(self):
        plan = ADAPTER.image_plan(
            "https://sahaaya2.bbmpgov.in/ProjectImages/GrievanceImages/1/b.jpg")
        self.assertFalse(plan.verify_tls)

    def test_dotted_host_and_s3_verify_cleanly(self):
        self.assertTrue(ADAPTER.image_plan(self.DOTTED).verify_tls)
        self.assertTrue(ADAPTER.image_plan(self.S3).verify_tls)

    def test_non_http_scheme_is_unfetchable(self):
        self.assertIsNone(ADAPTER.image_plan("ftp://example.invalid/x.jpg"))
        self.assertIsNone(ADAPTER.image_plan("not a url"))


class StaffFilenameTests(unittest.TestCase):
    def test_full_unpadded_timestamp(self):
        self.assertEqual(
            parse_staff_filename("20446742_2024 1 27 13 22 5.jpg"),
            "2024-01-27T13:22:05")

    def test_minute_precision_pads_second_to_zero(self):
        self.assertEqual(
            parse_staff_filename("img_2024 10 20 21 39.jpg"),
            "2024-10-20T21:39:00")

    def test_seconds_running_into_digits_degrade_to_minutes(self):
        self.assertEqual(
            parse_staff_filename("20446742_2024 1 27 13 22 5231.jpg"),
            "2024-01-27T13:22:00")

    def test_no_timestamp_is_none(self):
        self.assertIsNone(parse_staff_filename("no_timestamp_here.jpg"))

    def test_year_inside_longer_digit_run_rejected(self):
        self.assertIsNone(parse_staff_filename("12024 1 27 13 22.jpg"))

    def test_impossible_date_rejected_never_normalised(self):
        self.assertIsNone(parse_staff_filename("x_2024 13 40 99 99.jpg"))
        self.assertIsNone(parse_staff_filename(12345))


if __name__ == "__main__":
    unittest.main()
