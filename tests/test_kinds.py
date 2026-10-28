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

    def test_machine_must_be_a_plain_name(self):
        base = {"text": "x", "lens": "law", "trust": "owner", "sensitivity": "private", "intake": "scan"}
        self.assertEqual(validate_fields(self.kinds["question"], dict(base, machine="thinkpad1")), [])
        for bad in ("any\napproval: none", "a b", "-x", "a/b", ""):
            errs = validate_fields(self.kinds["question"], dict(base, machine=bad))
            if bad != "":  # empty means unset
                self.assertTrue(any("machine" in e for e in errs), (bad, errs))

    def test_unit_carries_what_the_manifest_recorded(self):
        names = {f.name for f in self.kinds["unit"].fields}
        self.assertEqual({"parent", "folder", "verified", "repo", "unit_kind"} - names, set())
        base = {"name": "Newslines", "unit_kind": "pipeline"}
        self.assertEqual(validate_fields(self.kinds["unit"], dict(base, parent="U-0020", repo="R-0011", folder="research/news", verified=False)), [])
        self.assertTrue(any("parent" in e for e in validate_fields(self.kinds["unit"], dict(base, parent="R-0001"))))
        self.assertTrue(any("verified" in e for e in validate_fields(self.kinds["unit"], dict(base, verified="no"))))

    def test_repo_carries_visibility(self):
        base = {"name": "site", "remote": "niagaraassembly/site"}
        self.assertEqual(validate_fields(self.kinds["repo"], dict(base, visibility="public")), [])
        self.assertTrue(any("visibility" in e for e in validate_fields(self.kinds["repo"], dict(base, visibility="secret"))))

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
