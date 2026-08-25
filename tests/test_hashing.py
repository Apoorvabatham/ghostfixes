import io
import json
import os
import tempfile
import unittest

from pipeline.hashing import HashLog, image_metrics, record_for, sha256_bytes


def png_bytes(mode="L", size=(32, 24), value=128):
    from PIL import Image
    img = Image.new(mode, size, value)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def gradient_png():
    from PIL import Image
    img = Image.new("L", (16, 16))
    img.putdata(list(range(256)))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class ShaTests(unittest.TestCase):
    def test_known_vector(self):
        self.assertEqual(
            sha256_bytes(b"abc"),
            "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")


class MetricsTests(unittest.TestCase):
    def test_solid_gray_has_zero_variance(self):
        m = image_metrics(png_bytes(value=128))
        self.assertEqual(m["brightness_mean"], 128.0)
        self.assertEqual(m["brightness_stddev"], 0.0)
        self.assertEqual(m["width"], 32)
        self.assertEqual(m["height"], 24)
        self.assertEqual(m["format"], "png")

    def test_gradient_has_variance_and_stable_phash(self):
        m1 = image_metrics(gradient_png())
        m2 = image_metrics(gradient_png())
        self.assertGreater(m1["brightness_stddev"], 0.0)
        self.assertEqual(m1["phash"], m2["phash"])
        self.assertNotEqual(m1["phash"], image_metrics(png_bytes())["phash"])

    def test_undecodable_raises_loudly(self):
        with self.assertRaises(Exception):
            image_metrics(b"not an image at all")


class RecordTests(unittest.TestCase):
    def test_record_field_set_is_exact_whitelist(self):
        rec = record_for(20446742, "https://example.invalid/x.jpg",
                         png_bytes(), captured_at="2026-08-25T00:00:00Z")
        self.assertEqual(
            set(rec),
            {"ticket_id", "ts_utc", "url", "image_sha256", "phash",
             "brightness_mean", "brightness_stddev", "width", "height",
             "format"})
        self.assertEqual(rec["ticket_id"], "20446742")


class HashLogTests(unittest.TestCase):
    def test_roundtrip(self):
        fd, path = tempfile.mkstemp(suffix=".jsonl")
        os.close(fd)
        os.remove(path)
        log = HashLog(path)
        rec = record_for(1, "https://example.invalid/a.jpg", png_bytes())
        log.append(rec)
        log.close()
        with open(path, encoding="utf-8") as fh:
            loaded = json.loads(fh.readline())
        self.assertEqual(loaded["image_sha256"], rec["image_sha256"])
        os.remove(path)


if __name__ == "__main__":
    unittest.main()
