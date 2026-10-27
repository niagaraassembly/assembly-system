import unittest
from pathlib import Path

from assembly.kinds import load_kinds, validate_fields

KINDS_DIR = Path(__file__).resolve().parent.parent / "kinds"


class KindsTest(unittest.TestCase):
    def setUp(self):
        self.kinds = load_kinds(KINDS_DIR)

    def test_all_seven_kinds_load_with_unique_prefixes(self):
        self.assertEqual(sorted(self.kinds), ["bay", "dataset", "goal", "question", "repo", "service", "unit"])
        prefixes = sorted(k.prefix for k in self.kinds.values())
        self.assertEqual(prefixes, ["B", "D", "G", "Q", "R", "S", "U"])
        self.assertEqual(len(set(prefixes)), 7)

    def test_question_fields_inferred_from_design(self):
        names = {f.name for f in self.kinds["question"].fields}
        wanted = {"text", "goal", "service", "lens", "region", "horizon", "raised_by", "origin", "trust",
                  "sensitivity", "intake", "cadence", "bay", "store", "reviews", "checks", "due",
                  "procedure", "writes", "machine", "path", "status_note", "supersedes"}
        self.assertEqual(wanted - names, set())

    def test_missing_required_names_field(self):
        errs = validate_fields(self.kinds["question"], {"text": "What zoning applies?"})
        self.assertTrue(any("lens" in e for e in errs), errs)

    def test_bad_enum_names_field_and_allowed_values(self):
        errs = validate_fields(self.kinds["question"], {"text": "x", "lens": "weather", "trust": "owner", "sensitivity": "private", "intake": "scan"})
        joined = " ".join(errs)
        self.assertIn("lens", joined)
        self.assertIn("law", joined)

    def test_unknown_field_rejected(self):
        errs = validate_fields(self.kinds["question"], {"text": "x", "lens": "law", "trust": "owner", "sensitivity": "private", "intake": "scan", "colour": "red"})
        self.assertTrue(any("colour" in e for e in errs), errs)

    def test_link_field_must_look_like_id_of_target_prefix(self):
        base = {"text": "x", "lens": "law", "trust": "owner", "sensitivity": "private", "intake": "scan"}
        self.assertEqual(validate_fields(self.kinds["question"], dict(base, goal="G-0001")), [])
        errs = validate_fields(self.kinds["question"], dict(base, goal="Q-0001"))
        self.assertTrue(any("goal" in e for e in errs), errs)


if __name__ == "__main__":
    unittest.main()
