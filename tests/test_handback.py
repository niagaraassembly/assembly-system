import tempfile
import unittest
from pathlib import Path

from assembly.handback import STATUS_MAP, apply_handback, find_runs
from assembly.kinds import load_kinds
from assembly.records import load, new_record, save

KINDS = load_kinds(Path(__file__).resolve().parent.parent / "kinds")


def make_run(runs_root, run_id, ref, status="running", month="10", machine="deb", with_input=True, broken=False):
    d = Path(runs_root) / "2026" / month / run_id
    d.mkdir(parents=True)
    if broken:
        (d / "run.md").write_bytes(b"\xff\xfe not frontmatter")
    else:
        (d / "run.md").write_text(
            '---\nid: %s\ncreated: "2026-10-27 10:00:00"\nupdated: "2026-10-27 10:05:00"\nmachine: %s\ntool: auto\n'
            'status: %s\nactual_tool: claude\n---\n\n# Run\n' % (run_id, machine, status), encoding="utf-8")
    if with_input:
        (d / "input.md").write_text('---\nmach: 1\ntype: task\ntitle: "t"\ngoal: "g"\ntool: auto\noutput: stdout\n'
                                    'tags: [assembly, as:%s, as-v0]\n---\nbody\n' % ref, encoding="utf-8")
    return d


class HandbackTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name) / "root"
        self.runs = Path(self._tmp.name) / "runs"
        self.root.mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def dispatched_question(self, status="dispatched"):
        r = new_record(KINDS["question"], "Q-0001", {"text": "x", "lens": "law", "trust": "owner", "sensitivity": "private", "intake": "scan"})
        r["status"] = status
        save(self.root, r)

    def test_find_runs_by_tag(self):
        make_run(self.runs, "r1", "Q-0001")
        make_run(self.runs, "r2", "Q-0002")
        runs, skipped = find_runs(self.runs, "Q-0001")
        self.assertEqual([r["run_id"] for r in runs], ["r1"])
        self.assertEqual((runs[0]["status"], runs[0]["machine"], runs[0]["actual_tool"]), ("running", "deb", "claude"))
        self.assertEqual(skipped, 0)

    def test_unreadable_run_skipped_not_crash(self):
        make_run(self.runs, "bad", "Q-0001", broken=True)
        make_run(self.runs, "noinput", "Q-0001", with_input=False)
        make_run(self.runs, "good", "Q-0001")
        runs, skipped = find_runs(self.runs, "Q-0001")
        self.assertEqual([r["run_id"] for r in runs], ["good"])
        self.assertEqual(skipped, 2)

    def test_missing_runs_root_returns_empty(self):
        self.assertEqual(find_runs(self.runs / "nope", "Q-0001"), ([], 0))

    def test_apply_updates_status_and_history_once(self):
        self.dispatched_question()
        make_run(self.runs, "r1", "Q-0001", status="running")
        log = apply_handback(self.root, KINDS, self.runs)
        self.assertEqual(len(log), 1)
        self.assertEqual(apply_handback(self.root, KINDS, self.runs), [])
        rec = load(self.root, "Q-0001", KINDS)
        self.assertEqual(rec["status"], "running")
        self.assertEqual([e["event"] for e in rec["history"]].count("handback"), 1)
        self.assertEqual(rec["last_run"]["run_id"], "r1")

    def test_done_goes_to_awaiting_confirmation_not_answered(self):
        self.dispatched_question("running")
        make_run(self.runs, "r1", "Q-0001", status="done")
        apply_handback(self.root, KINDS, self.runs)
        self.assertEqual(load(self.root, "Q-0001", KINDS)["status"], "awaiting-confirmation")
        self.assertNotIn("answered", STATUS_MAP.values())

    def test_new_and_answered_records_are_not_touched(self):
        self.dispatched_question("new")
        make_run(self.runs, "r1", "Q-0001", status="done")
        self.assertEqual(apply_handback(self.root, KINDS, self.runs), [])
        self.assertEqual(load(self.root, "Q-0001", KINDS)["status"], "new")

    def test_dry_run_reports_but_changes_nothing(self):
        self.dispatched_question()
        make_run(self.runs, "r1", "Q-0001", status="done")
        log = apply_handback(self.root, KINDS, self.runs, dry_run=True)
        self.assertEqual(len(log), 1)
        self.assertEqual(load(self.root, "Q-0001", KINDS)["status"], "dispatched")

    def test_latest_run_wins(self):
        self.dispatched_question()
        make_run(self.runs, "r1", "Q-0001", status="failed")
        d = make_run(self.runs, "r2", "Q-0001", status="done")
        (d / "run.md").write_text((d / "run.md").read_text().replace("10:00:00", "11:00:00"), encoding="utf-8")
        apply_handback(self.root, KINDS, self.runs)
        self.assertEqual(load(self.root, "Q-0001", KINDS)["status"], "awaiting-confirmation")


if __name__ == "__main__":
    unittest.main()


class RunResultTest(HandbackTest):
    def test_run_result_reads_latest_run_files_read_only(self):
        from assembly.handback import run_result
        d = make_run(self.runs, "r1", "Q-0001", status="done")
        (d / "output.md").write_text("Found 3 permits\n", encoding="utf-8")
        (d / "big.bin").write_bytes(b"\x00" * 10)
        make_run(self.runs, "r0", "Q-0001", status="failed", month="09")
        res = run_result(self.runs, "Q-0001")
        self.assertEqual(res["run_id"], "r1")
        self.assertEqual(res["status"], "done")
        self.assertEqual(res["files"]["output.md"], "Found 3 permits\n")
        self.assertIn("run.md", res["files"])
        self.assertNotIn("big.bin", res["files"])           # binary files are named, not read
        self.assertIn("big.bin", res["skipped"])
        self.assertEqual(res["older_runs"], 1)

    def test_run_result_truncates_and_handles_absent(self):
        from assembly.handback import run_result
        self.assertIsNone(run_result(self.runs, "Q-0001"))
        d = make_run(self.runs, "r1", "Q-0001", status="done")
        (d / "output.md").write_text("x" * 50000, encoding="utf-8")
        res = run_result(self.runs, "Q-0001", max_bytes=1000)
        self.assertEqual(len(res["files"]["output.md"]), 1000)
        self.assertIn("output.md", res["truncated"])
