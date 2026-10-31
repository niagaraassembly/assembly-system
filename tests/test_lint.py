import tempfile
import unittest
from pathlib import Path

from assembly.create import apply_create
from assembly.kinds import load_kinds
from assembly.lint import lint

KINDS = load_kinds(Path(__file__).resolve().parent.parent / "kinds")
Q = {"text": "q", "lens": "law", "trust": "owner", "sensitivity": "private", "intake": "scan"}


class LintTest(unittest.TestCase):
    def test_clean_and_partial_creation_warning(self):
        with tempfile.TemporaryDirectory() as t:
            root, out = Path(t) / "r", Path(t) / "o"
            root.mkdir()
            self.assertEqual(lint(root, KINDS), ([], []))
            blocker = Path(t) / "blocked"
            blocker.write_text("a file, not a folder")
            apply_create(root, KINDS, "question", dict(Q), blocker)      # emit fails -> partial
            errors, warnings = lint(root, KINDS)
            self.assertEqual(errors, [])
            self.assertTrue(any("partial" in w for w in warnings))

    def test_unknown_link_is_an_error(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t) / "r"
            root.mkdir()
            apply_create(root, KINDS, "question", dict(Q), Path(t) / "o", hold_handoffs=True)
            import json
            p = root / "profiles" / "question" / "Q-0001.json"
            rec = json.loads(p.read_text())
            rec["fields"]["goal"] = "G-0099"
            p.write_text(json.dumps(rec))
            errors, _ = lint(root, KINDS)
            self.assertTrue(any("G-0099" in e for e in errors))
