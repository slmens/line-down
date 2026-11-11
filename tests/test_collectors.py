import gzip
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import check_fresh
import common
import ttc

ALERTS = b'{"lastUpdated":"2026-11-10T22:19:05.29Z","routes":[{"route":"1","routeType":"Subway"}]}'


class FakeResponse:
    def __init__(self, body, url):
        self.body, self.url = body, url

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass

    def geturl(self):
        return self.url

    def read(self, n):
        return self.body[:n]


class FetchTest(unittest.TestCase):
    def test_refuses_plain_http(self):
        with self.assertRaises(ValueError):
            common.fetch("http://alerts.ttc.ca/x")

    def test_refuses_redirect_to_other_host(self):
        with mock.patch("urllib.request.urlopen", return_value=FakeResponse(b"{}", "https://evil.example/x")):
            with self.assertRaises(ValueError):
                common.fetch("https://alerts.ttc.ca/x")

    def test_refuses_oversized_response(self):
        big = b"x" * (common.MAX_BYTES + 1)
        with mock.patch("urllib.request.urlopen", return_value=FakeResponse(big, "https://alerts.ttc.ca/x")):
            with self.assertRaises(ValueError):
                common.fetch("https://alerts.ttc.ca/x")


class TtcTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.raw = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_stores_only_changes(self):
        p1 = ttc.save(ALERTS, 1794367086, self.raw)
        self.assertEqual(p1, self.raw / "ttc" / "live_alerts" / "2026-11-11" / "1794367086.json.gz")
        self.assertEqual(gzip.decompress(p1.read_bytes()), ALERTS)
        self.assertIsNone(ttc.save(ALERTS, 1794367116, self.raw))
        self.assertIsNotNone(ttc.save(ALERTS.replace(b"Subway", b"Bus"), 1794367146, self.raw))
        self.assertEqual(len(list(self.raw.rglob("*.gz"))), 2)

    def test_unexpected_response_writes_nothing(self):
        for bad in (b"<html>", b"[]", b'{"routes":"x","lastUpdated":"t"}', b'{"routes":[]}'):
            with self.assertRaises(Exception):
                ttc.save(bad, 1794367086, self.raw)
        self.assertEqual(list(self.raw.rglob("*")), [])


class FreshTest(unittest.TestCase):
    def test_flags_missing_and_old_feeds_only(self):
        with tempfile.TemporaryDirectory() as d:
            raw = Path(d)
            for feed, age in (("bikeshare/station_status", 60), ("ttc/live_alerts", 3600)):
                last = raw / feed / "LAST"
                last.parent.mkdir(parents=True)
                last.write_text("k")
                os.utime(last, (1_000_000 - age, 1_000_000 - age))
            found = dict(check_fresh.stale(raw, now=1_000_000))
        self.assertEqual(found, {"bikeshare/station_information": None, "ttc/live_alerts": 3600})


if __name__ == "__main__":
    unittest.main()
