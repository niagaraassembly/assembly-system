import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from assembly.cli import main
from assembly.kinds import load_kinds
from assembly.records import load
from tests.test_handback import make_run

KINDS = load_kinds(Path(__file__).resolve().parent.parent / "kinds")
Q = ["new", "question", "--set", "text=What zoning applies?", "--set", "lens=law", "--set", "trust=owner",
     "--set", "sensitivity=private", "--set", "intake=scan"]


class CliTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name) / "root"
        self.root.mkdir()
        self.outbox = Path(self._tmp.name) / "out"
        self.runs = Path(self._tmp.name) / "runs"

    def tearDown(self):
        self._tmp.cleanup()

    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = main(list(argv), root=self.root)
        return rc, out.getvalue(), err.getvalue()

    def test_kinds_lists_kinds_and_fields(self):
        rc, out, _ = self.run_cli("kinds")
        self.assertEqual(rc, 0)
        self.assertIn("question", out)
        rc, out, _ = self.run_cli("kinds", "question")
        self.assertIn("lens", out)
        self.assertIn("required", out)

    def test_new_without_apply_previews_and_writes_nothing(self):
        rc, out, _ = self.run_cli(*Q, "--outbox", str(self.outbox))
        self.assertEqual(rc, 0)
        self.assertIn("preview only", out)
        self.assertEqual(list(self.root.iterdir()), [])
        self.assertFalse(self.outbox.exists())

    def test_new_apply_creates_question_and_handoff(self):
        rc, out, _ = self.run_cli(*Q, "--outbox", str(self.outbox), "--apply")
        self.assertEqual(rc, 0, out)
        self.assertIn("Q-0001", out)
        self.assertEqual(len(list(self.outbox.glob("*.md"))), 1)
        self.assertEqual(load(self.root, "Q-0001", KINDS)["status"], "dispatched")

    def test_new_invalid_exit_2_names_field(self):
        rc, out, err = self.run_cli("new", "question", "--set", "text=x", "--apply")
        self.assertEqual(rc, 2)
        self.assertIn("lens", out + err)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_repeated_set_builds_list_and_from_file_works(self):
        self.run_cli(*Q, "--set", "procedure=cd ~/na/na-research, then look", "--set", "procedure=npm run news:validate",
                     "--outbox", str(self.outbox), "--apply")
        self.assertEqual(load(self.root, "Q-0001", KINDS)["fields"]["procedure"],
                         ["cd ~/na/na-research, then look", "npm run news:validate"])
        f = Path(self._tmp.name) / "g.json"
        f.write_text(json.dumps({"text": "Map heavy industry", "raised_by": "company"}))
        rc, out, _ = self.run_cli("new", "goal", "--from", str(f), "--apply")
        self.assertEqual(rc, 0, out)
        self.assertIn("G-0001", out)
        self.assertIn("manual-pending", out)

    def test_set_coerces_types(self):
        self.run_cli(*Q, "--set", "reviews=2", "--set", "writes=yes", "--outbox", str(self.outbox), "--apply")
        f = load(self.root, "Q-0001", KINDS)["fields"]
        self.assertEqual((f["reviews"], f["writes"]), (2, True))
        rc, out, err = self.run_cli(*Q, "--set", "reviews=two")
        self.assertEqual(rc, 2)
        self.assertIn("reviews", out + err)

    def test_show_and_list(self):
        self.run_cli(*Q, "--outbox", str(self.outbox), "--apply")
        rc, out, _ = self.run_cli("show", "Q-0001")
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(out)["record"]["id"], "Q-0001")
        rc, out, _ = self.run_cli("list", "question")
        self.assertIn("Q-0001", out)
        self.assertIn("dispatched", out)
        self.assertEqual(self.run_cli("show", "Q-0099")[0], 2)

    def test_lint_flags_broken_link(self):
        self.run_cli(*Q, "--set", "goal=G-0099", "--outbox", str(self.outbox), "--apply")
        rc, out, err = self.run_cli("lint")
        self.assertEqual(rc, 2)
        self.assertIn("G-0099", out + err)

    def test_lint_warns_on_partial_creation(self):
        self.run_cli(*Q, "--outbox", str(self.outbox), "--apply")
        cp = self.root / "creations" / "Q-0001.json"
        c = json.loads(cp.read_text())
        c["steps"][1]["status"] = "failed"
        c["state"] = "partial"
        cp.write_text(json.dumps(c))
        rc, out, err = self.run_cli("lint")
        self.assertEqual(rc, 1)
        self.assertIn("Q-0001", out + err)

    def test_resume_completes_a_partial_creation(self):
        blocker = Path(self._tmp.name) / "not-a-dir"
        blocker.write_text("x")
        rc, out, _ = self.run_cli(*Q, "--outbox", str(blocker), "--apply")
        self.assertEqual(rc, 1)
        self.assertIn("partial", out)
        rc, out, _ = self.run_cli("resume", "Q-0001", "--outbox", str(self.outbox))
        self.assertEqual(rc, 0, out)
        self.assertEqual(len(list(self.outbox.glob("*.md"))), 1)
        self.assertEqual(load(self.root, "Q-0001", KINDS)["status"], "dispatched")
        self.assertEqual(self.run_cli("lint")[0], 0)
        self.assertEqual(self.run_cli("resume", "Q-0099")[0], 2)

    def test_dispatch_preview_then_apply_is_idempotent(self):
        self.run_cli(*Q, "--outbox", str(self.outbox), "--apply")
        other = Path(self._tmp.name) / "other"
        rc, out, _ = self.run_cli("dispatch", "Q-0001", "--outbox", str(other))
        self.assertEqual(rc, 0)
        self.assertIn("preview only", out)
        self.assertFalse(other.exists())
        self.assertEqual(self.run_cli("dispatch", "Q-0001", "--outbox", str(other), "--apply")[0], 0)
        self.assertEqual(self.run_cli("dispatch", "Q-0001", "--outbox", str(other), "--apply")[0], 0)
        self.assertEqual(len(list(other.glob("*.md"))), 1)

    def test_handback_preview_then_apply_then_confirm(self):
        self.run_cli(*Q, "--outbox", str(self.outbox), "--apply")
        make_run(self.runs, "r1", "Q-0001", status="done")
        rc, out, _ = self.run_cli("handback", "--runs", str(self.runs))
        self.assertIn("awaiting-confirmation", out)
        self.assertEqual(load(self.root, "Q-0001", KINDS)["status"], "dispatched")
        self.run_cli("handback", "--runs", str(self.runs), "--apply")
        self.assertEqual(load(self.root, "Q-0001", KINDS)["status"], "awaiting-confirmation")
        self.assertEqual(self.run_cli("confirm", "Q-0001")[0], 0)
        self.assertEqual(load(self.root, "Q-0001", KINDS)["status"], "answered")
        self.assertEqual(self.run_cli("confirm", "Q-0001")[0], 2)

    def test_set_preview_apply_and_revised_dispatch(self):
        self.run_cli(*Q, "--outbox", str(self.outbox), "--apply")
        rc, out, _ = self.run_cli("set", "Q-0001", "--set", "lens=land")
        self.assertEqual(rc, 0)
        self.assertIn("lens: law -> land", out)
        self.assertIn("preview only", out)
        rec = load(self.root, "Q-0001", KINDS)
        self.assertEqual((rec["fields"]["lens"], rec.get("rev", 0)), ("law", 0))
        rc, out, _ = self.run_cli("set", "Q-0001", "--set", "region=Hamilton", "--apply")
        self.assertEqual(rc, 0, out)
        rec = load(self.root, "Q-0001", KINDS)
        self.assertEqual((rec["fields"]["region"], rec["rev"]), ("Hamilton", 1))
        rc, out, _ = self.run_cli("dispatch", "Q-0001", "--outbox", str(self.outbox), "--apply")
        self.assertEqual(rc, 0, out)
        names = sorted(p.name for p in self.outbox.glob("*.md"))
        self.assertEqual(len(names), 2)
        self.assertTrue(any(n.endswith("-dispatch-r1.md") for n in names), names)
        self.assertTrue(any(n.endswith("-dispatch.md") for n in names), names)

    def test_set_invalid_exits_2_and_unset_works(self):
        self.run_cli(*Q, "--outbox", str(self.outbox), "--apply")
        rc, out, err = self.run_cli("set", "Q-0001", "--set", "lens=weather", "--apply")
        self.assertEqual(rc, 2)
        self.assertIn("lens", out + err)
        self.run_cli("set", "Q-0001", "--set", "region=X", "--apply")
        self.run_cli("set", "Q-0001", "--unset", "region", "--apply")
        self.assertNotIn("region", load(self.root, "Q-0001", KINDS)["fields"])

    def test_retire_and_supersede_commands(self):
        for _ in range(2):
            self.run_cli(*Q, "--outbox", str(self.outbox), "--apply")
        rc, out, _ = self.run_cli("supersede", "Q-0001", "--by", "Q-0002")
        self.assertIn("preview only", out)
        self.assertEqual(load(self.root, "Q-0001", KINDS)["status"], "dispatched")
        self.assertEqual(self.run_cli("supersede", "Q-0001", "--by", "Q-0002", "--apply")[0], 0)
        self.assertEqual(load(self.root, "Q-0001", KINDS)["status"], "retired")
        self.assertEqual(self.run_cli("retire", "Q-0002", "--reason", "no longer needed", "--apply")[0], 0)
        self.assertEqual(self.run_cli("retire", "Q-0002", "--reason", "again", "--apply")[0], 2)
        self.assertEqual(self.run_cli("retire", "Q-0001", "--reason", "x")[0], 2)  # already retired, even as a preview

    def test_dispatch_refuses_a_retired_record(self):
        self.run_cli(*Q, "--outbox", str(self.outbox), "--apply")
        self.run_cli("retire", "Q-0001", "--reason", "x", "--apply")
        self.assertEqual(self.run_cli("dispatch", "Q-0001", "--outbox", str(self.outbox), "--apply")[0], 2)

    def test_lint_warns_on_link_to_retired_and_unfinished_supersede(self):
        self.run_cli("new", "goal", "--set", "text=g", "--set", "raised_by=company", "--apply")
        self.run_cli(*Q, "--set", "goal=G-0001", "--outbox", str(self.outbox), "--apply")
        self.run_cli("retire", "G-0001", "--reason", "x", "--apply")
        rc, out, err = self.run_cli("lint")
        self.assertEqual(rc, 1)
        self.assertIn("retired", out + err)

    def test_new_existing_flag_skips_provisioning(self):
        rc, out, _ = self.run_cli("new", "repo", "--set", "name=site", "--set", "remote=niagaraassembly/site", "--existing", "--apply")
        self.assertEqual(rc, 0, out)
        self.assertIn("complete", out)
        rc, out, _ = self.run_cli("new", "repo", "--set", "name=x", "--existing")
        self.assertIn("already exists", out)
        self.assertIn("preview only", out)

    def test_set_only_suggests_dispatch_for_kinds_that_have_a_handoff(self):
        self.run_cli("new", "repo", "--set", "name=crm", "--existing", "--apply")
        rc, out, _ = self.run_cli("set", "R-0001", "--set", "purpose=Helps a website function operate.", "--apply")
        self.assertEqual(rc, 0, out)
        self.assertNotIn("dispatch", out)
        self.run_cli(*Q, "--outbox", str(self.outbox), "--apply")
        rc, out, _ = self.run_cli("set", "Q-0001", "--set", "region=Hamilton", "--apply")
        self.assertIn("dispatch Q-0001", out)

    def test_confirm_refuses_a_record_that_is_not_awaiting(self):
        self.run_cli(*Q, "--outbox", str(self.outbox), "--apply")
        self.assertEqual(self.run_cli("confirm", "Q-0001")[0], 2)


if __name__ == "__main__":
    unittest.main()
