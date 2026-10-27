import tempfile
import unittest
from pathlib import Path

from assembly.change import ChangeError, apply_set, plan_set, retire, supersede
from assembly.kinds import load_kinds
from assembly.records import add_event, load, new_record, save

KINDS = load_kinds(Path(__file__).resolve().parent.parent / "kinds")
Q = {"text": "Which parcels changed owner?", "lens": "land", "trust": "owner", "sensitivity": "private", "intake": "scan"}


class ChangeTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        for i in ("Q-0001", "Q-0002"):
            save(self.root, new_record(KINDS["question"], i, dict(Q)))
        save(self.root, new_record(KINDS["goal"], "G-0001", {"text": "g", "raised_by": "company"}))

    def tearDown(self):
        self._tmp.cleanup()

    def test_plan_set_shows_diff_and_writes_nothing(self):
        before = load(self.root, "Q-0001", KINDS)
        p = plan_set(self.root, KINDS, "Q-0001", {"lens": "law"}, [])
        self.assertEqual(p["errors"], [])
        self.assertEqual(p["diff"], [{"field": "lens", "old": "land", "new": "law"}])
        self.assertEqual(load(self.root, "Q-0001", KINDS), before)

    def test_apply_set_changes_field_bumps_rev_and_records_history(self):
        r = apply_set(self.root, KINDS, "Q-0001", {"lens": "law", "region": "Hamilton, ON"}, [], actor="morgen")
        self.assertEqual(r["rev"], 1)
        rec = load(self.root, "Q-0001", KINDS)
        self.assertEqual((rec["fields"]["lens"], rec["fields"]["region"], rec["rev"]), ("law", "Hamilton, ON", 1))
        ev = rec["history"][-1]
        self.assertEqual(ev["event"], "changed")
        self.assertIn("lens: land -> law", ev["detail"])
        self.assertIn("by morgen", ev["detail"])

    def test_set_validates_like_creation(self):
        for changes, unset, field in (({"lens": "weather"}, [], "lens"), ({"colour": "red"}, [], "colour"),
                                      ({}, ["lens"], "lens"), ({"goal": "Q-0001"}, [], "goal")):
            with self.assertRaises(ChangeError) as cm:
                apply_set(self.root, KINDS, "Q-0001", changes, unset)
            self.assertTrue(any(field in e for e in cm.exception.errors), cm.exception.errors)
        self.assertEqual(load(self.root, "Q-0001", KINDS).get("rev", 0), 0)

    def test_set_noop_changes_nothing(self):
        r = apply_set(self.root, KINDS, "Q-0001", {"lens": "land"}, [])
        self.assertEqual(r["diff"], [])
        rec = load(self.root, "Q-0001", KINDS)
        self.assertEqual((rec.get("rev", 0), rec["history"]), (0, []))

    def test_set_cannot_touch_status_or_id(self):
        for k in ("status", "id", "rev"):
            with self.assertRaises(ChangeError):
                apply_set(self.root, KINDS, "Q-0001", {k: "x"}, [])

    def test_unset_removes_an_optional_field(self):
        apply_set(self.root, KINDS, "Q-0001", {"region": "Hamilton"}, [])
        apply_set(self.root, KINDS, "Q-0001", {}, ["region"])
        self.assertNotIn("region", load(self.root, "Q-0001", KINDS)["fields"])

    def test_missing_record_is_an_error(self):
        with self.assertRaises(ChangeError):
            apply_set(self.root, KINDS, "Q-0099", {"lens": "law"}, [])

    def test_retire_sets_status_and_history_and_refuses_twice(self):
        retire(self.root, KINDS, "Q-0001", "asked twice", actor="morgen")
        rec = load(self.root, "Q-0001", KINDS)
        self.assertEqual(rec["status"], "retired")
        self.assertIn("asked twice", rec["history"][-1]["detail"])
        with self.assertRaises(ChangeError):
            retire(self.root, KINDS, "Q-0001", "again")

    def test_retired_records_are_read_only(self):
        retire(self.root, KINDS, "Q-0001", "done with it")
        with self.assertRaises(ChangeError) as cm:
            apply_set(self.root, KINDS, "Q-0001", {"lens": "law"}, [])
        self.assertTrue(any("retired" in e for e in cm.exception.errors))

    def test_supersede_links_new_and_retires_old(self):
        supersede(self.root, KINDS, "Q-0001", "Q-0002", actor="morgen")
        old, new = load(self.root, "Q-0001", KINDS), load(self.root, "Q-0002", KINDS)
        self.assertEqual(old["status"], "retired")
        self.assertIn("superseded by Q-0002", old["history"][-1]["detail"])
        self.assertEqual(new["fields"]["supersedes"], "Q-0001")
        self.assertEqual(new["rev"], 1)

    def test_supersede_refusals(self):
        with self.assertRaises(ChangeError):
            supersede(self.root, KINDS, "Q-0001", "Q-0001")          # same record
        with self.assertRaises(ChangeError):
            supersede(self.root, KINDS, "Q-0001", "G-0001")          # different kinds
        with self.assertRaises(ChangeError):
            supersede(self.root, KINDS, "G-0001", "G-0001")          # kind has no supersedes field
        retire(self.root, KINDS, "Q-0001", "x")
        with self.assertRaises(ChangeError):
            supersede(self.root, KINDS, "Q-0001", "Q-0002")          # old already retired
        self.assertNotIn("supersedes", load(self.root, "Q-0002", KINDS)["fields"])


if __name__ == "__main__":
    unittest.main()
