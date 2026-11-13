"""Incident-brief agent: which alerts count, station matching, the faithfulness check, brief writing."""
import io
import json
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "agent"))
import brief  # noqa: E402

LINE2 = ["Keele Station", "Dundas West Station", "Lansdowne Station", "Dufferin Station"]
LINE1 = ["Highway 407 Station", "Vaughan Metropolitan Centre Station", "St George Station", "St Clair Station",
         "St Clair West Station"]


def alert(id_, effect="NO_SERVICE", cause="MEDICAL_EMERGENCY", route_type="Subway"):
    return {"id": id_, "routeType": route_type, "effect": effect, "cause": cause}


class DisruptionTest(unittest.TestCase):
    def test_which_alerts_count(self):
        self.assertTrue(brief.is_disruption(alert("1")))
        self.assertTrue(brief.is_disruption(alert("1", effect="SIGNIFICANT_DELAYS")))
        self.assertFalse(brief.is_disruption(alert("1", effect="NO_EFFECT")))       # "Regular service has resumed"
        self.assertFalse(brief.is_disruption(alert("1", cause="MAINTENANCE")))      # planned closures
        self.assertFalse(brief.is_disruption(alert("1", route_type="Bus")))

    def test_step_finds_starts_and_ends(self):
        current, started, ended = brief.step(["a", "b"], [alert("b"), alert("c"), alert("a", effect="NO_EFFECT")])
        self.assertEqual(sorted(current), ["b", "c"])
        self.assertEqual((started, ended), (["c"], ["a"]))

    def test_cause_text_to_codes(self):
        self.assertEqual(brief.cause_prefixes("Medical emergency"), ["MUI"])
        self.assertEqual(brief.cause_prefixes("Trespasser at track level"), ["SUUT"])
        self.assertEqual(brief.cause_prefixes("LRT - Signal issue"), ["PUS"])
        self.assertIsNone(brief.cause_prefixes("Something new"))
        self.assertIsNone(brief.cause_prefixes(None))


class StationTest(unittest.TestCase):
    def test_match(self):
        self.assertEqual(brief.match_station("Vaughan", LINE1), "Vaughan Metropolitan Centre Station")
        self.assertEqual(brief.match_station("St Clair", LINE1), "St Clair Station")   # exact beats prefix
        self.assertIsNone(brief.match_station("Oakwood", LINE1))

    def test_stretch_either_direction(self):
        self.assertEqual(brief.stretch("Lansdowne", "Keele", LINE2)[0], LINE2[:3])
        self.assertEqual(brief.stretch("Keele", "Keele", LINE2)[0], LINE2[:1])

    def test_stretch_unmatched(self):
        self.assertEqual(brief.stretch("Oakwood", "Oakwood", LINE2), ([], ["Oakwood", "Oakwood"]))
        self.assertEqual(brief.stretch("Keele", "Nowhere", LINE2), (LINE2[:1], ["Nowhere"]))

    def test_length_summary(self):
        self.assertEqual(brief.length_summary(list(range(1, 11))),
                         {"based_on_past_delays": 10, "median_minutes": 6, "8_in_10_under_minutes": 8})


class FaithfulnessTest(unittest.TestCase):
    facts = {"line": "2", "usual_length": {"median_minutes": 8, "8_in_10_under_minutes": 15},
             "bikes": {"bikes_available": 1234}}

    def test_numbers_from_facts_pass(self):
        self.assertEqual(brief.unsupported_numbers("Line 2: usually 8 min, 8 in 10 under 15; 1,234 bikes.", self.facts), [])

    def test_made_up_numbers_fail(self):
        self.assertEqual(brief.unsupported_numbers("About 20 min, 1,242 bikes.", self.facts), ["20", "1242"])


class WriteBriefsTest(unittest.TestCase):
    def setUp(self):
        tmp = Path(tempfile.mkdtemp())
        self.patches = [mock.patch.object(brief, "INCIDENTS", tmp), mock.patch.object(brief, "KEY_FILE", tmp / "key"),
                        mock.patch.dict("os.environ", {"OPENROUTER_API_KEY": ""})]
        for p in self.patches:
            p.start()
        brief.save(tmp / "9.json", {"alert_id": "9", "facts": {"median_minutes": 8}, "brief": None})

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def test_no_key_keeps_pending(self):
        self.assertEqual(brief.write_briefs(["9"]), ["9"])

    def test_brief_saved_with_check(self):
        brief.KEY_FILE.write_text("test-key\n")
        reply = {"model": brief.MODEL, "choices": [
            {"finish_reason": "stop", "message": {"content": "Usually 8 min, sometimes 30."}}]}
        with mock.patch.object(brief, "chat", return_value=reply) as chat:
            self.assertEqual(brief.write_briefs(["9"]), [])
        key, messages = chat.call_args.args
        self.assertEqual(key, "test-key")
        self.assertEqual(json.loads(messages[1]["content"]), {"median_minutes": 8})
        saved = json.loads((brief.INCIDENTS / "9.json").read_text())
        self.assertEqual(saved["brief"], "Usually 8 min, sometimes 30.")
        self.assertEqual(saved["unsupported_numbers"], ["30"])

    def test_bad_key_stops_and_keeps_pending(self):
        brief.KEY_FILE.write_text("bad")
        err = urllib.error.HTTPError(brief.OPENROUTER_URL, 401, "Unauthorized", {}, io.BytesIO(b"{}"))
        with mock.patch.object(brief, "chat", side_effect=err), mock.patch("sys.stderr", io.StringIO()):
            self.assertEqual(brief.write_briefs(["9"]), ["9"])


if __name__ == "__main__":
    unittest.main()
