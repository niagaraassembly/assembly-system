import tempfile
import unittest
from datetime import date
from pathlib import Path

from assembly.bundle import CAP, bundle_key, due, plan
from assembly.create import apply_create
from assembly.change import apply_set, retire
from assembly.kinds import load_kinds
from assembly.period import week_id

KINDS = load_kinds(Path(__file__).resolve().parent.parent / "kinds")
BASE = {"text": "q", "lens": "law", "trust": "owner", "sensitivity": "private", "intake": "scan",
        "region": "Niagara", "cadence": "weekly", "origin": "internal"}


class PeriodTest(unittest.TestCase):
    def test_news_week_starts_sunday(self):          # Review Focus 6
        self.assertEqual(week_id(date(2026, 10, 11)), "2026-W42")
        self.assertEqual(week_id(date(2026, 10, 17)), "2026-W42")
        self.assertEqual(week_id(date(2026, 10, 18)), "2026-W43")
        self.assertEqual(week_id(date(2026, 10, 27)), "2026-W44")


class DueTest(unittest.TestCase):
    def test_cadences(self):
        self.assertTrue(due("daily", date(2026, 10, 28)))
        self.assertTrue(due("weekly", date(2026, 10, 25)))      # Sunday
        self.assertFalse(due("weekly", date(2026, 10, 26)))     # Monday
        self.assertTrue(due("monthly", date(2026, 11, 1)))
        self.assertFalse(due("monthly", date(2026, 11, 2)))
        self.assertTrue(due("once", date(2026, 10, 28)))
        self.assertTrue(due(None, date(2026, 10, 28)))


class PlanTest(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.root = Path(self._t.name) / "r"
        self.root.mkdir()
        self.out = Path(self._t.name) / "out"

    def tearDown(self):
        self._t.cleanup()

    def mk(self, **over):
        return apply_create(self.root, KINDS, "question", dict(BASE, **over), self.out, hold_handoffs=True)["id"]

    def p(self, on=date(2026, 10, 25), **kw):
        return plan(self.root, KINDS, on, **kw)

    def test_same_key_groups_regardless_of_order_and_sources_do_not_split(self):
        a, b, c = self.mk(path="x"), self.mk(path="y"), self.mk(text="other")
        out = self.p()
        self.assertEqual(len(out["bundles"]), 1)
        self.assertEqual([m["id"] for m in out["bundles"][0]["members"]], sorted([a, b, c]))

    def test_each_key_field_splits_bundles(self):
        self.mk()
        for k, v in (("origin", "external"), ("sensitivity", "public"), ("trust", "derived"), ("region", "Erie"),
                     ("cadence", "daily"), ("intake", "file")):
            self.mk(**{k: v})
        self.assertEqual(len(self.p()["bundles"]), 7)

    def test_single_question_is_a_valid_bundle(self):
        self.mk()
        self.assertEqual(len(self.p()["bundles"]), 1)

    def test_over_cap_splits_into_numbered_parts_deterministically(self):
        ids = [self.mk() for _ in range(CAP + 1)]
        bs = self.p()["bundles"]
        self.assertEqual([(b["part"], b["of"]) for b in bs], [(1, 2), (2, 2)])
        self.assertEqual(len(bs[0]["members"]), CAP)
        self.assertEqual([b["key_id"] for b in bs], [b["key_id"] for b in self.p()["bundles"]])
        self.assertEqual(sorted(m["id"] for b in bs for m in b["members"]), sorted(ids))

    def test_retired_and_answered_are_excluded_with_reason_not_dropped(self):
        a, b = self.mk(), self.mk()
        retire(self.root, KINDS, a, "dup")
        out = self.p()
        self.assertEqual([x["id"] for x in out["excluded"]], [a])
        self.assertIn("retired", out["excluded"][0]["reason"])
        self.assertEqual([m["id"] for bb in out["bundles"] for m in bb["members"]], [b])

    def test_due_flag_per_member_and_only_due_filter(self):
        self.mk(cadence="weekly")
        mon = date(2026, 10, 26)
        out = self.p(on=mon)
        self.assertFalse(out["bundles"][0]["members"][0]["due"])
        self.assertFalse(out["bundles"][0]["due"])
        self.assertEqual(self.p(on=mon, only_due=True)["bundles"], [])
        self.assertTrue(self.p(on=date(2026, 10, 25))["bundles"][0]["due"])

    def test_period_and_key_shown_with_unstated_effort(self):
        self.mk()
        b = self.p()["bundles"][0]
        self.assertEqual(b["period"], "2026-W44")
        self.assertEqual(b["key"]["effort"], None)       # v0 questions do not carry effort; never invented
        self.assertEqual(bundle_key({"region": "A"})["region"], "A")

    def test_plan_writes_nothing_and_does_not_change_records(self):
        self.mk()
        before = sorted(str(p) for p in self.root.rglob("*") if p.is_file())
        self.p()
        self.assertEqual(before, sorted(str(p) for p in self.root.rglob("*") if p.is_file()))


if __name__ == "__main__":
    unittest.main()
