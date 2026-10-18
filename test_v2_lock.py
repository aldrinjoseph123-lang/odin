"""v2.0.0: the hashed Python lock (requirements.lock) holds every pin in requirements.txt with
a hash. Run with: python -m unittest test_v2_lock"""
import pathlib
import re
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parent


class LockTestCase(unittest.TestCase):
    def test_the_lock_holds_every_pin_with_a_hash(self):
        sys.path.insert(0, str(ROOT / "scripts"))
        try:
            import make_lock
        finally:
            sys.path.pop(0)
        locked = {}
        for line in (ROOT / "requirements.lock").read_text().splitlines():
            if m := re.match(r"([A-Za-z0-9_.-]+)==(\S+) \\$", line):
                locked[m[1].lower()] = [m[2], 0]
                last = locked[m[1].lower()]
            elif re.fullmatch(r"\s+--hash=sha256:[0-9a-f]{64}( \\)?", line):
                last[1] += 1
        pins = make_lock.pins()
        self.assertEqual(set(locked), set(pins), "requirements.lock is stale: python3 scripts/make_lock.py")
        for name, version in pins.items():
            self.assertEqual(locked[name][0], version, name)
            self.assertGreaterEqual(locked[name][1], 1, name)
