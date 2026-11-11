"""Warehouse parsing rules. Needs DuckDB: run with .venv/bin/python -m unittest (skipped on system Python)."""
import io
import sys
import tempfile
import unittest
import zipfile
from datetime import datetime
from pathlib import Path

try:
    import duckdb
except ImportError:
    duckdb = None

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "warehouse"))


@unittest.skipIf(duckdb is None, "duckdb not installed (use .venv/bin/python)")
class MacroTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.con = duckdb.connect()
        cls.con.execute((ROOT / "warehouse" / "sql" / "00_macros.sql").read_text())

    def one(self, sql, *params):
        return self.con.execute("select " + sql, list(params)).fetchone()[0]

    def test_trip_time_formats(self):
        cases = [
            ("2025-12-01 00:00:37", "iso", datetime(2025, 12, 1, 0, 0, 37)),
            ("1/1/2018 0:47", "mdy", datetime(2018, 1, 1, 0, 47)),
            ("10/01/17 00:00:01", "mdy2s", datetime(2017, 10, 1, 0, 0, 1)),
            ("1/4/2017 0:01", "dmy", datetime(2017, 4, 1, 0, 1)),
            ("42606.567361111112", "excel", datetime(2016, 8, 24, 13, 37)),
            ("13/10/2016 0:00", "dmy_or_swapped_excel", datetime(2016, 10, 13, 0, 0)),
            # Excel read "05/10/2016" as May 10; the file is Oct-Dec, so it is Oct 5.
            ("42500.5", "dmy_or_swapped_excel", datetime(2016, 10, 5, 12, 0)),
            ("not a date", "iso", None),
        ]
        for raw, fmt, want in cases:
            self.assertEqual(self.one("parse_trip_time(?, ?)", raw, fmt), want, (raw, fmt))

    def test_ids_and_names(self):
        self.assertEqual(self.one("clean_id(?)", "7130.0"), 7130)
        self.assertIsNone(self.one("clean_id(?)", ""))
        self.assertIsNone(self.one("clean_name(?)", "NULL"))
        self.assertEqual(self.one("clean_name(?)", " Bay St  /  Queen "), "Bay St / Queen")
        self.assertEqual(self.one("user_kind(?)", "Annual Member"), "member")
        self.assertEqual(self.one("user_kind(?)", "Casual Member"), "casual")

    def test_station_key(self):
        same = [
            ("BLOOR STATION (ENTERIN", "BLOOR"),
            ("ST. GEORGE BD/YUS STATION", "ST GEORGE"),
            ("PIONEER VILLAGE STATIO", "PIONEER VILLAGE"),
            ("Queen's Park Station", "QUEEN S PARK"),
            ("YONGE SHP STATION", "SHEPPARD YONGE"),
            ("Sheppard-Yonge Station", "SHEPPARD YONGE"),
        ]
        for raw, key in same:
            self.assertEqual(self.one("station_key(?)", raw), key, raw)

    def test_subway_line(self):
        for raw, want in [("YU", "1"), ("B/D", "2"), ("SHP", "4"), ("YU/BD", "multi"), ("29 DUFFERIN", None), (None, None)]:
            self.assertEqual(self.one("subway_line(?)", raw), want, raw)


@unittest.skipIf(duckdb is None, "duckdb not installed (use .venv/bin/python)")
class BuildHelpersTest(unittest.TestCase):
    def test_column_map(self):
        import build
        m = build.column_map(["Trip  Duration", "Start_Station_Id", "trip_start_time"], build.TRIP_COLUMNS)
        self.assertEqual(m, {"duration": "Trip  Duration", "start_id": "Start_Station_Id", "start_time": "trip_start_time"})
        with self.assertRaises(ValueError):
            build.column_map(["Surprise"], build.TRIP_COLUMNS)
        self.assertEqual(build.column_map(["_id", "Date"], {"date": "date"}, build.DELAY_IGNORED), {"date": "Date"})

    def test_trip_time_format(self):
        import build
        self.assertEqual(build.trip_time_format(2017, "Bikeshare Ridership (2017 Q2).csv"), "dmy")
        self.assertEqual(build.trip_time_format(2017, "Bikeshare Ridership (2017 Q4).csv"), "mdy2s")
        self.assertEqual(build.trip_time_format(2020, "2020-01.csv"), "mdy")
        self.assertEqual(build.trip_time_format(2026, "x.csv"), "iso")

    def test_unpack_handles_encodings_nested_zip_and_lock_files(self):
        import build
        inner = io.BytesIO()
        with zipfile.ZipFile(inner, "w") as z:
            z.writestr("2022-11.csv", "a\nnested\n")
        outer = io.BytesIO()
        with zipfile.ZipFile(outer, "w") as z:
            z.writestr("dir/bom.csv", b"\xef\xbb\xbfa\nbom\n")
            z.writestr("cp.csv", "a\nCafé\n".encode("cp1252"))
            z.writestr("dir/2022-11.zip", inner.getvalue())
            z.writestr("2017 Data/~$lock.csv", b"junk")
            z.writestr("../evil name.csv", b"a\nx\n")
        with tempfile.TemporaryDirectory() as d:
            found = []
            build.unpack_csvs(zipfile.ZipFile(outer), Path(d), "2022", found)
            got = {p.name: p.read_text("utf-8") for p, _ in found}
            self.assertEqual(sorted(p.name for p in Path(d).iterdir()), sorted(got))  # nothing written elsewhere
        self.assertEqual(got, {
            "2022__bom.csv": "a\nbom\n",
            "2022__cp.csv": "a\nCafé\n",
            "2022__2022-11.csv": "a\nnested\n",
            "2022__evil_name.csv": "a\nx\n",
        })


if __name__ == "__main__":
    unittest.main()
