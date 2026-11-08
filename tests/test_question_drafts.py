import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from assembly.cli import main, resolve_root
from assembly.create import CreationError, apply_create, plan_create, resume_create
from assembly.kinds import load_kinds
from assembly.records import load

KINDS = load_kinds(Path(__file__).resolve().parent.parent / "kinds")


class QuestionDraftTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "records"
        self.root.mkdir()
        self.outbox = Path(self.tmp.name) / "outbox"

    def tearDown(self):
        self.tmp.cleanup()

    def cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            status = main(list(args), root=self.root)
        return status, out.getvalue() + err.getvalue()

    def test_preview_is_write_free_and_does_not_require_readiness_fields(self):
        plan = plan_create(self.root, KINDS, "question", {"text": "What can this region make?"}, draft=True)
        self.assertEqual(plan["errors"], [])
        self.assertEqual([s["id"] for s in plan["steps"]], ["write-profile"])
        self.assertEqual(list(self.root.iterdir()), [])

    def test_local_record_root_redirect_keeps_old_checkout_on_one_store(self):
        from unittest.mock import patch
        import os
        store = Path(self.tmp.name) / "stable-store"
        store.mkdir()
        (self.root / ".assembly-record-root").write_text(str(store) + "\n")
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(resolve_root(repo=self.root), store)
            self.assertEqual(resolve_root(self.root, repo=self.root), self.root)
        with patch.dict(os.environ, {"ASSEMBLY_ROOT": str(self.root)}):
            self.assertEqual(resolve_root(repo=self.root), self.root)

    def test_long_original_text_roundtrips_without_an_emitter(self):
        text = "\n\n  Original\tquestion\r\n" + ("café e\u0301 🦊 <script>alert(1)</script> </textarea> &\n" * 7000) + "\n  "
        emitter = Mock()
        c = apply_create(self.root, KINDS, "question", {"text": text, "intake": "scan"}, self.outbox,
                         emit=emitter, draft=True)
        rec = load(self.root, c["id"], KINDS)
        self.assertEqual(rec["fields"]["text"], text)
        self.assertEqual(rec["status"], "draft")
        self.assertTrue(rec["draft"])
        self.assertEqual(c["state"], "complete")
        self.assertEqual([s["id"] for s in c["steps"]], ["write-profile"])
        resume_create(self.root, KINDS, c["id"], self.outbox, emit=emitter)
        emitter.assert_not_called()
        self.assertFalse(self.outbox.exists())
        self.assertEqual(self.cli("dispatch", c["id"], "--apply")[0], 2)

    def test_cli_draft_and_linked_question_share_canonical_ids(self):
        self.assertEqual(self.cli("new", "question", "--draft", "--set", "text=Original", "--apply")[0], 0)
        self.assertEqual(self.cli("new", "question", "--draft", "--set", "text=More general",
                                  "--set", "source_question=Q-0001", "--apply")[0], 0)
        rec = load(self.root, "Q-0002", KINDS)
        self.assertEqual(rec["fields"]["source_question"], "Q-0001")
        self.assertEqual(load(self.root, "Q-0001", KINDS)["fields"]["text"], "Original")
        self.assertEqual(self.cli("lint")[0], 0)

    def test_invalid_or_blank_drafts_never_mint_an_id(self):
        for fields in ({"text": " \n\t "}, {"text": "x", "lens": "weather"}, {"text": "x", "source_question": "Q-9999"},
                       {"text": "bad\ud800"}):
            with self.subTest(fields=repr(fields)):
                with self.assertRaises(CreationError):
                    apply_create(self.root, KINDS, "question", fields, self.outbox, draft=True)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_regular_creation_stays_strict_and_drafts_are_question_only(self):
        self.assertTrue(plan_create(self.root, KINDS, "question", {"text": "x"})["errors"])
        self.assertTrue(plan_create(self.root, KINDS, "goal", {"text": "x"}, draft=True)["errors"])

    def test_metadata_changes_preserve_draft_and_lint_after_retirement(self):
        self.cli("new", "question", "--draft", "--set", "text=Original", "--apply")
        self.assertEqual(self.cli("set", "Q-0001", "--set", "region=Western New York", "--apply")[0], 0)
        self.assertEqual(load(self.root, "Q-0001", KINDS)["status"], "draft")
        self.assertEqual(self.cli("retire", "Q-0001", "--reason", "Replaced later", "--apply")[0], 0)
        self.assertEqual(self.cli("lint")[0], 0)

    def test_original_text_and_source_link_are_immutable(self):
        self.cli("new", "question", "--draft", "--set", "text=Original", "--apply")
        self.cli("new", "question", "--draft", "--set", "text=Derived",
                 "--set", "source_question=Q-0001", "--apply")
        for args in (("--set", "text=Rewritten"), ("--set", "source_question=Q-9999"),
                     ("--set", "source_question=Q-0002"), ("--unset", "source_question")):
            with self.subTest(args=args):
                self.assertEqual(self.cli("set", "Q-0002", *args, "--apply")[0], 2)
        self.assertEqual(self.cli("set", "Q-0001", "--set", "source_question=Q-0002", "--apply")[0], 2)
        rec = load(self.root, "Q-0002", KINDS)
        self.assertEqual(rec["fields"]["text"], "Derived")
        self.assertEqual(rec["fields"]["source_question"], "Q-0001")


if __name__ == "__main__":
    unittest.main()
