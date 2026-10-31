import tempfile
import unittest
from pathlib import Path

from assembly.actions import confirm_record, dispatch_record
from assembly.change import ChangeError, apply_set, retire, supersede
from assembly.create import apply_create
from assembly.kinds import load_kinds
from assembly.records import load, save

KINDS = load_kinds(Path(__file__).resolve().parent.parent / "kinds")
Q = {"text": "q", "lens": "law", "trust": "owner", "sensitivity": "private", "intake": "scan"}


class ActionsTest(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.root = Path(self._t.name) / "r"
        self.root.mkdir()
        self.out = Path(self._t.name) / "out"

    def tearDown(self):
        self._t.cleanup()

    def mk(self, hold=True, **o):
        return apply_create(self.root, KINDS, "question", dict(Q, **o), self.out, hold_handoffs=hold)["id"]

    def set_status(self, id, st):
        r = load(self.root, id, KINDS)
        r["status"] = st
        save(self.root, r)

    # ---- confirm
    def test_confirm_only_from_awaiting_and_records_who(self):
        id = self.mk()
        with self.assertRaises(ChangeError):
            confirm_record(self.root, KINDS, id)
        self.set_status(id, "awaiting-confirmation")
        confirm_record(self.root, KINDS, id, actor="owner (site)")
        r = load(self.root, id, KINDS)
        self.assertEqual(r["status"], "answered")
        self.assertEqual(r["history"][-1]["event"], "confirmed")
        self.assertIn("owner (site)", r["history"][-1]["detail"])
        with self.assertRaises(ChangeError):
            confirm_record(self.root, KINDS, id)                 # a second confirm is refused, not repeated

    # ---- dispatch
    def test_dispatch_writes_task_moves_status_and_is_idempotent(self):
        id = self.mk(hold=False)                                  # already dispatched by creation
        id2 = self.mk(hold=True)
        paths = dispatch_record(self.root, KINDS, id2, self.out)
        self.assertEqual(len(paths), 1)
        self.assertTrue(paths[0].exists())
        r = load(self.root, id2, KINDS)
        self.assertEqual(r["status"], "dispatched")
        n = len(r["history"])
        dispatch_record(self.root, KINDS, id2, self.out)           # same content: no new event, no duplicate file
        self.assertEqual(len(load(self.root, id2, KINDS)["history"]), n)
        self.assertEqual(len(list(self.out.glob("*as-q-0002*"))), 1)

    def test_dispatch_refuses_retired_and_kinds_without_handoff(self):
        id = self.mk()
        retire(self.root, KINDS, id, "dup")
        with self.assertRaises(ChangeError):
            dispatch_record(self.root, KINDS, id, self.out)
        g = apply_create(self.root, KINDS, "goal", {"text": "g", "raised_by": "company"}, self.out)["id"]
        with self.assertRaises(ChangeError):
            dispatch_record(self.root, KINDS, g, self.out)

    def test_dispatch_of_a_changed_record_writes_a_revised_document(self):
        id = self.mk()
        dispatch_record(self.root, KINDS, id, self.out)
        apply_set(self.root, KINDS, id, {"region": "Erie"}, [])
        paths = dispatch_record(self.root, KINDS, id, self.out)
        self.assertIn("-r1", paths[0].name)

    # ---- expected_rev guard
    def test_expected_rev_blocks_stale_changes(self):
        id = self.mk()
        apply_set(self.root, KINDS, id, {"region": "A"}, [], expected_rev=0)      # rev 0 -> 1
        with self.assertRaises(ChangeError) as e:
            apply_set(self.root, KINDS, id, {"region": "B"}, [], expected_rev=0)
        self.assertIn("changed since", e.exception.errors[0])
        self.assertEqual(load(self.root, id, KINDS)["fields"]["region"], "A")
        with self.assertRaises(ChangeError):
            retire(self.root, KINDS, id, "x", expected_rev=0)
        with self.assertRaises(ChangeError):
            dispatch_record(self.root, KINDS, id, self.out, expected_rev=0)
        retire(self.root, KINDS, id, "x", expected_rev=1)
        other = self.mk()
        with self.assertRaises(ChangeError):
            supersede(self.root, KINDS, other, self.mk(), expected_rev=5)

    def test_no_expected_rev_keeps_old_behaviour(self):
        id = self.mk()
        apply_set(self.root, KINDS, id, {"region": "A"}, [])
        apply_set(self.root, KINDS, id, {"region": "B"}, [])
        self.assertEqual(load(self.root, id, KINDS)["rev"], 2)
