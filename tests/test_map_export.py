"""Map exporter data shaping. Needs DuckDB to import: run with .venv/bin/python -m unittest."""
import math
import sys
import unittest
from pathlib import Path

try:
    import duckdb  # noqa: F401
except ImportError:
    duckdb = None

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "map"))


@unittest.skipIf(duckdb is None, "duckdb not installed (use .venv/bin/python)")
class ShapeEventTest(unittest.TestCase):
    def test_counts_and_normal_days(self):
        from export import K, shape_event
        k0 = K.index(0)
        rows = [
            (0, 0, 7001, 3), (0, 0, 7002, 1),          # the day: 4 trips in slot 0
            (-7, 0, 7001, 1), (7, 0, 7001, 2),         # normal days: 1, 2 and 0 trips
            (7, 0, 7002, 1),
            (14, 0, 7001, 9),                          # a day not in control_days: ignored
            (0, 99, 7001, 5),                          # slot outside the window: ignored
        ]
        out = shape_event(rows, [-7, 7, -14])
        self.assertEqual(out["stations"], [7001, 7002])
        self.assertEqual(out["normal_days"], 3)
        self.assertEqual(out["actual"][0][k0], 3)
        self.assertEqual(out["total_actual"][k0], 4)
        self.assertEqual(sum(out["total_actual"]), 4)
        self.assertEqual(out["normal"][0][k0], 1.0)              # (1 + 2 + 0) / 3
        self.assertEqual(out["total_normal"][k0], round(4 / 3, 2))
        self.assertEqual((out["total_normal_low"][k0], out["total_normal_high"][k0]), (0, 3))
        self.assertTrue(all(len(r) == len(K) for r in out["actual"] + out["normal"]))

    def test_projection_puts_yonge_straight_up(self):
        from export import project
        union, finch = project(43.6453, -79.3806), project(43.7804, -79.4153)   # Union and Finch stations
        self.assertLess(finch[1], union[1])                                     # north is up (smaller y)
        self.assertLess(abs(finch[0] - union[0]), 0.15 * abs(finch[1] - union[1]))   # unturned it would be ~19%
        self.assertAlmostEqual(math.dist(union, finch), 15300, delta=600)        # about 15 km apart

    def test_shoreline_is_south_edge_smoothed(self):
        from export import shoreline
        cells = {(0, 5), (0, 2), (1, 5), (2, 8), (4, 1)}      # column 3 empty
        self.assertEqual(shoreline(cells, 5, window=1), [[0, 6], [1, 6], [2, 9], [4, 2]])
        self.assertEqual(shoreline(cells, 5, window=3)[0], [0, 6.0])   # (6 + 6) / 2 at the edge
        self.assertEqual(shoreline(cells, 5, window=3)[3], [3, 5.5])   # empty column borrows its neighbours

    def test_normal_day_is_closest_to_average(self):
        from export import pick_normal_day
        self.assertEqual(pick_normal_day({-7: 10, 7: 20, 14: 33}), 7)        # average 21
        self.assertEqual(pick_normal_day({-14: 10, -7: 30, 7: 10, 14: 30}), -7)   # all tie at 10 away: nearest week, earlier first
        self.assertEqual(pick_normal_day({21: 5}), 21)


if __name__ == "__main__":
    unittest.main()
