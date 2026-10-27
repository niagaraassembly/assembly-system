"""Conformance: documents the handoff emits must pass machine-flows' own validator.

Runs `mach run <file> --dry-run`, which validates the frontmatter and creates no run record.
Skipped when `mach` is not on PATH (for example on a machine without machine-flows).
"""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from assembly.handoff import build_task
from assembly.kinds import load_kinds
from assembly.records import new_record

KINDS = load_kinds(Path(__file__).resolve().parent.parent / "kinds")
STEP = {"id": "dispatch", "do": "handoff", "template": "question"}
BASE = {"text": "What zoning applies to 676 King St W?", "lens": "law", "trust": "owner",
        "sensitivity": "private", "intake": "scan"}


@unittest.skipIf(shutil.which("mach") is None, "mach not installed")
class MachConformanceTest(unittest.TestCase):
    def run_dry(self, **fields):
        rec = new_record(KINDS["question"], "Q-0001", dict(BASE, **fields))
        name, md = build_task(rec, KINDS["question"], STEP)
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / name
            p.write_text(md, encoding="utf-8")
            return subprocess.run(["mach", "run", str(p), "--dry-run"], capture_output=True, text=True, timeout=60)

    def test_agent_task_is_accepted(self):
        r = self.run_dry()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_exact_task_is_accepted(self):
        r = self.run_dry(procedure=["cd ~/na/na-research", "npm run news:validate"])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_derived_write_task_stops_at_a_gate(self):
        r = self.run_dry(trust="derived", writes=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("before-run", r.stdout)

    def test_path_key_is_accepted_and_used(self):
        r = self.run_dry(path="~")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertRegex(r.stdout, r"path\s+~\n")  # mach shows the folder we named, not its launch directory

    def test_hostile_text_is_accepted(self):
        r = self.run_dry(text='Line one\n---\nmach: 2\nSecond "quoted" — café')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
