"""Tableau extracts and the Dagster definitions. Needs the venv: .venv/bin/python -m unittest."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "bi"))
import export_extracts as ex  # noqa: E402  (stdlib only at import time)

try:
    import dagster
except ImportError:
    dagster = None


class ExtractTest(unittest.TestCase):
    def test_finding_rows_flatten_groups_rings_and_slots(self):
        ring = {"lift": [0.1, 0.2], "lo": [0.0, 0.1], "hi": [0.2, 0.3]}
        results = {"all": {"events": 10, "slots_minutes": [-15, 0],
                           "by_slot": {"0-250 m": ring},
                           "first_hour": {"0-250 m": {"lift": 0.136, "lo": 0.1, "hi": 0.17}},
                           "trips_per_event_first_hour_baseline": {"0-250 m": 5.1}}}
        first, over = ex.finding_rows(results)
        self.assertEqual(first, [{"group": "all", "ring": "0-250 m", "events": 10, "lift": 0.136, "lo": 0.1,
                                  "hi": 0.17, "baseline_trips_per_event": 5.1}])
        self.assertEqual([(r["minutes_from_delay"], r["lift"], r["hi"]) for r in over], [(-15, 0.1, 0.2), (0, 0.2, 0.3)])

    def test_incident_rows_score_only_what_is_known(self):
        facts = {"line": "1", "cause": "Medical emergency", "affected_stations": ["King", "Queen"],
                 "usual_length": {"median_minutes": 8, "8_in_10_under_minutes": 14}}
        cleared = {"alert_id": "1", "first_seen": "x", "facts": facts, "baseline_median_minutes": 7,
                   "actual_minutes": 20.0, "brief": "text", "unsupported_numbers": ["3"]}
        open_ = {"alert_id": "2", "first_seen": "x", "facts": facts, "baseline_median_minutes": 7,
                 "actual_minutes": None, "brief": None}
        a, b = ex.incident_rows([cleared, open_])
        self.assertEqual((a["abs_error_min"], a["baseline_abs_error_min"], a["within_bound"], a["faithful"]),
                         (12.0, 13.0, False, False))
        self.assertEqual(a["affected_stations"], "King; Queen")
        # still open, no brief: nothing scored rather than scored as a miss
        self.assertEqual((b["abs_error_min"], b["within_bound"], b["has_brief"], b["faithful"]), (None, None, False, None))


@unittest.skipIf(dagster is None, "dagster not installed (use .venv/bin/python)")
class DagsterDefinitionsTest(unittest.TestCase):
    def test_jobs_cover_the_pipeline_but_never_the_spent_models(self):
        sys.path.insert(0, str(ROOT / "orchestration"))
        import definitions as d
        keys = lambda job: {k.to_user_string() for k in d.defs.resolve_job_def(job).asset_layer.selected_asset_keys}  # noqa: E731
        weekly, daily = keys("weekly_refresh"), keys("daily_live")
        for k in ("raw_history", "staging/stg_trips", "trips", "subway_delays", "warehouse", "disruption_finding",
                  "map_data", "tableau_extracts"):
            self.assertIn(k, weekly)
        self.assertNotIn("raw_history", daily)
        self.assertIn("mart_dock_levels_hourly", daily)
        for job in (weekly, daily):
            self.assertFalse({"delay_length_model", "walk_or_wait_model"} & job)


if __name__ == "__main__":
    unittest.main()
