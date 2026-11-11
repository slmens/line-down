import gzip
import tempfile
import unittest
from pathlib import Path

from collectors.bikeshare import save

BODY = b'{"last_updated":1794367086,"ttl":10,"data":{"stations":[]}}'


class SaveTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.raw = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_stores_body_exactly_under_utc_date(self):
        path = save("station_status", BODY, self.raw)
        self.assertEqual(path, self.raw / "station_status" / "2026-11-11" / "1794367086.json.gz")
        self.assertEqual(gzip.decompress(path.read_bytes()), BODY)

    def test_repeat_is_stored_once(self):
        save("station_status", BODY, self.raw)
        self.assertIsNone(save("station_status", BODY, self.raw))
        self.assertEqual(len(list(self.raw.rglob("*.gz"))), 1)

    def test_malformed_response_writes_nothing(self):
        for bad in (b"<html>502 Bad Gateway</html>", b'{"data":{}}'):
            with self.assertRaises(Exception):
                save("station_status", bad, self.raw)
        self.assertEqual(list(self.raw.rglob("*")), [])


if __name__ == "__main__":
    unittest.main()
