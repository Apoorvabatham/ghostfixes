"""Deterministic image hashing + brightness metrics — detection inputs.

Invariant 2: every number here is a reproducible function of file bytes;
no model call ever sees a record. Invariant 1: records persist only the
allowed universe — ticket ID, capture time, URL, hashes, brightness
statistics, dimensions. Device metadata is never extracted.
"""

import hashlib
import io
import json
import os
import sys

from .journal import utc_now_iso


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def image_metrics(data: bytes) -> dict:
    """pHash plus grayscale brightness mean/stddev for one image.

    Imaging imports are lazy so hash-only callers need no imaging stack.
    Undecodable bytes raise — callers journal the failure; nothing is guessed.
    """
    from PIL import Image, ImageStat
    import imagehash

    img = Image.open(io.BytesIO(data))
    img.load()
    gray = img.convert("L")
    stat = ImageStat.Stat(gray)
    return {
        "phash": str(imagehash.phash(img)),
        "brightness_mean": round(stat.mean[0], 2),
        "brightness_stddev": round(stat.stddev[0], 2),
        "width": img.width,
        "height": img.height,
        "format": (img.format or "").lower(),
    }


def record_for(ticket_id, url, image_bytes, captured_at=None) -> dict:
    """Build one hashes.jsonl record — exactly the persisted field set."""
    rec = {
        "ticket_id": str(ticket_id),
        "ts_utc": captured_at or utc_now_iso(),
        "url": url,
        "image_sha256": sha256_bytes(image_bytes),
    }
    rec.update(image_metrics(image_bytes))
    return rec


class HashLog:
    """Append-only hashes.jsonl writer — the public tamper-evidence spine
    (scope-lock Amendment B rule 4). Same durability discipline as
    SweepJournal: flush + fsync per record, warn once if fsync unavailable."""

    def __init__(self, path):
        self.path = path
        self._fh = open(path, "a", encoding="utf-8")
        self._warned_no_fsync = False

    def append(self, record: dict) -> dict:
        line = json.dumps(record, ensure_ascii=False, sort_keys=True)
        self._fh.write(line + "\n")
        self._fh.flush()
        try:
            os.fsync(self._fh.fileno())
        except OSError:
            if not self._warned_no_fsync:
                print("hashlog: fsync unavailable; relying on flush()",
                      file=sys.stderr)
                self._warned_no_fsync = True
        return record

    def existing_pairs(self):
        """(ticket_id, url) pairs already on disk, from replaying the file.
        Gives exact-once per-image work across restarts; an unparsable line
        fails loudly rather than silently shrinking the done-set."""
        out = set()
        if not os.path.exists(self.path):
            return out
        with open(self.path, encoding="utf-8") as fh:
            for lineno, line in enumerate(fh, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"{self.path}:{lineno}: unparsable "
                                     "hash record — fail loudly") from exc
                out.add((rec["ticket_id"], rec["url"]))
        return out

    def close(self):
        self._fh.close()
