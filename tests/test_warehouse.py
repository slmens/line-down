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
class DelayMatchingTest(unittest.TestCase):
    """Runs the real 30_delays.sql on a toy Line 1 (Union - King - Queen) and Line 2 stretch."""

    @classmethod
    def setUpClass(cls):
        c = cls.con = duckdb.connect()
        c.execute((ROOT / "warehouse" / "sql" / "00_macros.sql").read_text())
        c.execute("""
            create table line_stations as select * from (values
                ('1', 1, 'Union Station'), ('1', 2, 'King Station'), ('1', 3, 'Queen Station'),
                ('1', 4, 'Sheppard West Station'), ('1', 5, 'Sheppard-Yonge Station'),
                ('2', 1, 'Kennedy Station'), ('2', 2, 'Victoria Park Station')) t(line, seq, station);
            create table subway_stations as select distinct station from line_stations;
            create table seed_station_aliases as select * from (values ('SHEPPARD', 'Sheppard-Yonge Station')) t(key, station);
            create table stg_delay_codes as select 'MUIS' as "CODE", 'Ill customer' as "DESCRIPTION";
            create table stg_delays as select '45000' as date, '08:15' as time, null as day, station,
                'MUIS' as code, '12' as min_delay, '15' as min_gap, 'N' as bound, line, null as vehicle,
                'test' as source_file
            from (values
                ('UNION STATION TO QUEEN', 'YU'),    -- stretch, both ends exact
                ('VICTORIA PARK TO KENNE', 'BD'),    -- end cut off, unique on Line 2
                ('QUEEN STATION TO SH', 'YU'),       -- end ambiguous on Line 1
                ('MCCOWAN STATION TO KEN', 'SRT'),   -- closed line, no line_stations
                ('KING STATION', 'YU'),              -- single station
                ('SHEPPARD STATION', 'YU')           -- alias
            ) t(station, line);
        """)
        c.execute((ROOT / "warehouse" / "sql" / "30_delays.sql").read_text())

    def test_stretches_and_singles(self):
        got = {r: (s, t) for r, s, t in self.con.execute("select station_raw, station, station_to from subway_delays").fetchall()}
        self.assertEqual(got, {
            "UNION STATION TO QUEEN": ("Union Station", "Queen Station"),
            "VICTORIA PARK TO KENNE": ("Victoria Park Station", "Kennedy Station"),
            "QUEEN STATION TO SH": (None, None),
            "MCCOWAN STATION TO KEN": (None, None),
            "KING STATION": ("King Station", None),
            "SHEPPARD STATION": ("Sheppard-Yonge Station", None),
        })

    def test_stretch_expands_to_every_station_between(self):
        rows = self.con.execute("""
            select d.station_raw, list(s.station order by s.station) from delay_stations s
            join subway_delays d using (delay_id) group by 1""").fetchall()
        got = dict(rows)
        self.assertEqual(got["UNION STATION TO QUEEN"], ["King Station", "Queen Station", "Union Station"])
        self.assertEqual(got["VICTORIA PARK TO KENNE"], ["Kennedy Station", "Victoria Park Station"])
        self.assertEqual(got["KING STATION"], ["King Station"])
        self.assertNotIn("QUEEN STATION TO SH", got)


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


try:
    import numpy as np
except ImportError:
    np = None


@unittest.skipIf(np is None or duckdb is None, "numpy/duckdb not installed (use .venv/bin/python)")
class LiftTest(unittest.TestCase):
    def test_lift_divides_out_the_citywide_change(self):
        sys.path.insert(0, str(ROOT / "analysis"))
        import disruption_effect as de
        K = len(de.K)
        # one event: near rings x1.2, x1.1, x1.0 of baseline; far x1.0 -> +20%, +10%, 0%
        base = np.ones((1, K, 4)) * [10, 20, 40, 1000]
        ev = base * [1.2, 1.1, 1.0, 1.0]
        np.testing.assert_allclose(de.lift(ev, base)[:, 0], [0.2, 0.1, 0.0])
        # a citywide +10% (far ring too) is divided out: near x1.32 -> +20%
        np.testing.assert_allclose(de.lift(base * [1.32, 1.1, 1.1, 1.1], base)[:, 0], [0.2, 0.0, 0.0], atol=1e-12)
        # events are pooled by summing counts, so a big event outweighs a small one
        two_base = np.concatenate([base, base * 3])
        two_ev = np.concatenate([base * [2, 1, 1, 1], base * 3])
        self.assertAlmostEqual(de.lift(two_ev, two_base)[0, 0], 0.25)  # (20+30)/(10+30) - 1
        self.assertAlmostEqual(de.lift_window(two_ev, two_base, slice(0, 4))[0], 0.25)


try:
    import sklearn
except ImportError:
    sklearn = None


@unittest.skipIf(np is None or sklearn is None or duckdb is None, "analysis libraries not installed (use .venv/bin/python)")
class DelayBaselineTest(unittest.TestCase):
    def test_code_baselines_use_train_only_and_fall_back(self):
        sys.path.insert(0, str(ROOT / "models"))
        import delay_length as dl
        code = np.array(["A"] * 40 + ["B"] * 5 + ["A", "C"])
        y = np.array([10.0] * 40 + [100.0] * 5 + [999.0, 999.0])
        train = np.array([True] * 45 + [False, False])  # the 999s are test rows and must not leak
        med, share, med_all = dl.code_baselines(code, y, train)
        self.assertEqual(med_all, 10.0)
        self.assertEqual(med[0], 10.0)        # A: own median
        self.assertEqual(med[40], 10.0)       # B: only 5 rows -> overall median
        self.assertEqual(med[46], 10.0)       # C: unseen in train -> overall median
        big_all = 5 / 45
        self.assertAlmostEqual(share[40], (5 + 10 * big_all) / (5 + 10))  # smoothed toward overall
        self.assertAlmostEqual(share[46], big_all)


@unittest.skipIf(np is None or duckdb is None, "analysis libraries not installed (use .venv/bin/python)")
class WalkOrWaitTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(ROOT / "models"))
        import walk_or_wait
        cls.w = walk_or_wait

    def test_remaining_time_only_counts_delays_that_lasted_this_long(self):
        history = {"A": np.array([3.0] * 100 + [20.0] * 40), "B": np.array([50.0] * 5)}
        left = self.w.remaining_samples(history, "A", 10)
        self.assertEqual(sorted(set(left)), [10.0])          # the 3-minute ones are gone
        self.assertEqual(len(left), 40)
        # too few B delays: falls back to every cause that reached 10 minutes
        self.assertEqual(len(self.w.remaining_samples(history, "B", 10)), 45)

    def test_decide_leaves_only_when_waiting_usually_loses(self):
        left = np.array([1.0] * 6 + [30.0] * 4)                # usually short
        self.assertEqual(self.w.decide(left, bike=10, walk=20)[0], "wait")
        left = np.array([1.0] * 4 + [30.0] * 6)                # usually long
        choice, p, _ = self.w.decide(left, bike=10, walk=20)
        self.assertEqual((choice, p), ("bike", 0.6))
        self.assertEqual(self.w.decide(left, bike=20, walk=10)[0], "walk")

    def test_option_minutes(self):
        # 800 m apart, docks 80 m from each station, 800 m dock to dock
        bike, walk = self.w.option_minutes(("1", "A", "B", 800, 80, 80, 800))
        self.assertAlmostEqual(walk, 3 + 800 * 1.3 / 80 + 2)
        self.assertAlmostEqual(bike, 3 + 80 * 1.3 / 80 + 800 * 1.3 / 250 + 80 * 1.3 / 80 + 2)
