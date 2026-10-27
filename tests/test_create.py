import json
import tempfile
import unittest
from pathlib import Path

from assembly.create import CreationError, apply_create, plan_create, resume_create
from assembly.ids import mint
from assembly.kinds import load_kinds
from assembly.records import load

KINDS = load_kinds(Path(__file__).resolve().parent.parent / "kinds")
GOOD = {"text": "What zoning applies to 676 King St W?", "lens": "law", "trust": "owner",
        "sensitivity": "private", "intake": "scan"}


class Recorder:
    """Fake handoff emitter: records calls, can fail the first N times."""
    def __init__(self, fail_first=0):
        self.calls, self.fail_first = [], fail_first

    def __call__(self, root, rec, kind, step, outbox):
        self.calls.append((rec["id"], step["id"]))
        if len(self.calls) <= self.fail_first:
            raise OSError("outbox unavailable")
        return Path(outbox) / (rec["id"] + ".md")


class CreateTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name) / "root"
        self.root.mkdir()
        self.outbox = Path(self._tmp.name) / "outbox"

    def tearDown(self):
        self._tmp.cleanup()

    def test_plan_writes_nothing(self):
        plan = plan_create(self.root, KINDS, "question", GOOD)
        self.assertEqual(plan["errors"], [])
        self.assertEqual([s["id"] for s in plan["steps"]], ["write-profile", "dispatch"])
        self.assertEqual(list(self.root.iterdir()), [])

    def test_apply_mints_writes_profile_and_records_steps(self):
        emit = Recorder()
        c = apply_create(self.root, KINDS, "question", GOOD, self.outbox, emit=emit)
        self.assertEqual(c["id"], "Q-0001")
        self.assertEqual(c["state"], "complete")
        self.assertEqual([s["status"] for s in c["steps"]], ["done", "done"])
        self.assertEqual(load(self.root, "Q-0001", KINDS)["fields"]["lens"], "law")
        saved = json.loads((self.root / "creations" / "Q-0001.json").read_text())
        self.assertEqual(saved["state"], "complete")

    def test_invalid_values_write_nothing_and_no_id_burned(self):
        with self.assertRaises(CreationError) as cm:
            apply_create(self.root, KINDS, "question", {"text": "x"}, self.outbox, emit=Recorder())
        self.assertTrue(any("lens" in e for e in cm.exception.errors))
        self.assertEqual(list(self.root.iterdir()), [])
        self.assertEqual(mint(self.root, "Q"), "Q-0001")

    def test_default_emitter_writes_a_valid_task_document(self):
        c = apply_create(self.root, KINDS, "question", GOOD, self.outbox)  # real emitter, no fake
        self.assertEqual(c["state"], "complete", c)
        files = list(self.outbox.glob("*.md"))
        self.assertEqual(len(files), 1)
        self.assertIn("as:Q-0001", files[0].read_text(encoding="utf-8"))

    def test_successful_handoff_marks_record_dispatched(self):
        apply_create(self.root, KINDS, "question", GOOD, self.outbox, emit=Recorder())
        self.assertEqual(load(self.root, "Q-0001", KINDS)["status"], "dispatched")
        apply_create(self.root, KINDS, "question", dict(GOOD, intake="file"), self.outbox, emit=Recorder())
        self.assertEqual(load(self.root, "Q-0002", KINDS)["status"], "new")

    def test_resume_after_failed_handoff_does_not_remint(self):
        emit = Recorder(fail_first=1)
        c = apply_create(self.root, KINDS, "question", GOOD, self.outbox, emit=emit)
        self.assertEqual(c["state"], "partial")
        self.assertEqual(c["steps"][1]["status"], "failed")
        c2 = resume_create(self.root, KINDS, "Q-0001", self.outbox, emit=emit)
        self.assertEqual(c2["state"], "complete")
        self.assertEqual(emit.calls, [("Q-0001", "dispatch"), ("Q-0001", "dispatch")])
        self.assertEqual(mint(self.root, "Q"), "Q-0002")

    def test_existing_things_get_a_profile_and_no_provisioning_steps(self):
        plan = plan_create(self.root, KINDS, "repo", {"name": "site", "remote": "niagaraassembly/site"}, existing=True)
        self.assertEqual([s["id"] for s in plan["steps"]], ["write-profile"])
        c = apply_create(self.root, KINDS, "repo", {"name": "site", "remote": "niagaraassembly/site"}, self.outbox, emit=Recorder(), existing=True)
        self.assertEqual((c["id"], c["state"]), ("R-0001", "complete"))
        rec = load(self.root, "R-0001", KINDS)
        self.assertEqual(rec["history"][0]["event"], "created")
        self.assertIn("already exists", rec["history"][0]["detail"])
        # without the flag the same repo would carry the manual provisioning step
        c2 = apply_create(self.root, KINDS, "repo", {"name": "other"}, self.outbox, emit=Recorder())
        self.assertEqual(c2["state"], "manual-pending")

    def test_existing_question_does_not_dispatch(self):
        emit = Recorder()
        c = apply_create(self.root, KINDS, "question", GOOD, self.outbox, emit=emit, existing=True)
        self.assertEqual((emit.calls, c["state"]), ([], "complete"))
        self.assertEqual(load(self.root, c["id"], KINDS)["status"], "new")

    def test_resume_does_not_repeat_done_steps(self):
        emit = Recorder()
        apply_create(self.root, KINDS, "question", GOOD, self.outbox, emit=emit)
        resume_create(self.root, KINDS, "Q-0001", self.outbox, emit=emit)
        self.assertEqual(len(emit.calls), 1)

    def test_manual_steps_leave_state_manual_pending(self):
        c = apply_create(self.root, KINDS, "goal", {"text": "Map ownership of heavy industry", "raised_by": "company"}, self.outbox, emit=Recorder())
        self.assertEqual(c["id"], "G-0001")
        self.assertEqual(c["state"], "manual-pending")
        self.assertEqual(c["steps"][1]["status"], "manual")

    def test_file_intake_gets_manual_step_not_handoff(self):
        emit = Recorder()
        c = apply_create(self.root, KINDS, "question", dict(GOOD, intake="file"), self.outbox, emit=emit)
        self.assertEqual(emit.calls, [])
        self.assertEqual(c["state"], "manual-pending")

    def test_apply_twice_same_draft_makes_two_things(self):
        emit = Recorder()
        a = apply_create(self.root, KINDS, "question", GOOD, self.outbox, emit=emit)
        b = apply_create(self.root, KINDS, "question", GOOD, self.outbox, emit=emit)
        self.assertEqual((a["id"], b["id"]), ("Q-0001", "Q-0002"))


if __name__ == "__main__":
    unittest.main()
