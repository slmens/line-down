import io
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

import common
from download_history import check, plan

BASE = "https://ckan0.cf.opendata.inter.prod-toronto.ca/dataset/x/resource/y/download/"


def res(url, fmt="CSV", last_modified="2026-10-26T12:50:40", size=None):
    return {"url": url, "format": fmt, "last_modified": last_modified, "created": "2020-01-01T00:00:00", "size": size}


def zip_bytes():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("trips.csv", "a,b\n1,2\n")
    return buf.getvalue()


class PlanTest(unittest.TestCase):
    def test_keeps_files_and_skips_duplicates(self):
        raw = Path("/r")
        got = plan("ds", [
            res(BASE + "delays-2024.xlsx", "XLSX", size=10),
            res("https://opendata.toronto.ca/a/bikeshare-2017.zip", "ZIP", last_modified=None),
            res(BASE + "since-2025.json", "JSON"),
            res("https://ckan0.cf.opendata.inter.prod-toronto.ca/datastore/dump/abc", "XLSX"),
        ], raw)
        self.assertEqual(got, [
            (BASE + "delays-2024.xlsx", raw / "history/ds/2026-10-26/delays-2024.xlsx"),
            ("https://opendata.toronto.ca/a/bikeshare-2017.zip", raw / "history/ds/2020-01-01/bikeshare-2017.zip"),
        ])

    def test_rejects_unexpected_host_or_name(self):
        for url in ("https://evil.example/a.csv", "http://opendata.toronto.ca/a.csv", BASE + "..", BASE + ".hidden.csv"):
            with self.assertRaises(ValueError):
                plan("ds", [res(url)])


class CheckTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, data):
        p = self.dir / "f.part"
        p.write_bytes(data)
        return p

    def test_accepts_real_zip_and_csv(self):
        z = zip_bytes()
        check(self.write(z), "a.zip")
        check(self.write(b"Date,Time\n2025-01-01,00:01\n"), "a.csv")

    def test_rejects_wrong_type_or_corruption(self):
        z = zip_bytes()
        cases = [
            (b"<html>Not found</html>", "a.zip"),   # error page posing as zip
            (b"<!doctype html>", "a.csv"),          # error page posing as csv
            (z.replace(b"1,2", b"9,9"), "a.zip"),   # CRC mismatch
        ]
        for data, name in cases:
            with self.assertRaises(Exception, msg=name):
                check(self.write(data), name)


class Resp(io.BytesIO):
    """Fake HTTP response; headers carries Content-Length when given."""

    def __init__(self, body, url, length=None):
        super().__init__(body)
        self.url = url
        self.headers = {} if length is None else {"Content-Length": str(length)}

    def geturl(self):
        return self.url


class DownloadTest(unittest.TestCase):
    def test_cut_off_download_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            with mock.patch("urllib.request.urlopen", return_value=Resp(b"abc", "https://opendata.toronto.ca/a.csv", 10)):
                with self.assertRaises(ValueError):
                    common.download("https://opendata.toronto.ca/a.csv", Path(d) / "a.csv", 100, lambda p: None)
            self.assertEqual(list(Path(d).iterdir()), [])

    def test_failed_check_leaves_no_file(self):
        with tempfile.TemporaryDirectory() as d:
            dest = Path(d) / "a.zip"
            with mock.patch("urllib.request.urlopen", return_value=Resp(b"<html>", "https://opendata.toronto.ca/a.zip")):
                with self.assertRaises(ValueError):
                    common.download("https://opendata.toronto.ca/a.zip", dest, 100, lambda p: check(p, "a.zip"))
            self.assertEqual(list(Path(d).iterdir()), [])

    def test_size_cap(self):
        with tempfile.TemporaryDirectory() as d:
            with mock.patch("urllib.request.urlopen", return_value=Resp(b"x" * (3 << 20), "https://opendata.toronto.ca/a.csv")):
                with self.assertRaises(ValueError):
                    common.download("https://opendata.toronto.ca/a.csv", Path(d) / "a.csv", 2 << 20, lambda p: None)
            self.assertEqual(list(Path(d).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
