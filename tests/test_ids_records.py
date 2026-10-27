import tempfile
import threading
import unittest
from pathlib import Path

from assembly.ids import mint, parse_id
from assembly.kinds import load_kinds
from assembly.records import add_event, list_ids, load, new_record, save

KINDS = load_kinds(Path(__file__).resolve().parent.parent / "kinds")


class IdsTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_mint_sequential_and_padded(self):
        self.assertEqual(mint(self.root, "Q"), "Q-0001")
        self.assertEqual(mint(self.root, "Q"), "Q-0002")
        self.assertEqual(mint(self.root, "G"), "G-0001")

    def test_mint_never_reuses_after_record_deleted(self):
        i = mint(self.root, "Q")
        rec = new_record(KINDS["question"], i, {"text": "x"})
        p = save(self.root, rec)
        p.unlink()
        self.assertEqual(mint(self.root, "Q"), "Q-0002")

    def test_mint_respects_existing_profiles_when_counter_is_missing(self):
        save(self.root, new_record(KINDS["question"], "Q-0007", {"text": "x"}))
        self.assertEqual(mint(self.root, "Q"), "Q-0008")

    def test_mint_unique_under_threads(self):
        out, lock = [], threading.Lock()

        def work():
            i = mint(self.root, "Q")
            with lock:
                out.append(i)

        ts = [threading.Thread(target=work) for _ in range(20)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        self.assertEqual(len(set(out)), 20)

    def test_parse_id_rejects_garbage(self):
        self.assertEqual(parse_id("Q-0012"), ("Q", 12))
        for bad in ("", "q-1", "Q0001", "Q-", "Q-12a", "../Q-0001"):
            with self.assertRaises(ValueError):
                parse_id(bad)


class RecordsTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_save_load_roundtrip(self):
        rec = new_record(KINDS["question"], "Q-0001", {"text": "What zoning applies?", "lens": "law"})
        add_event(rec, "created", "test")
        save(self.root, rec)
        back = load(self.root, "Q-0001", KINDS)
        self.assertEqual(back["fields"]["lens"], "law")
        self.assertEqual(back["status"], "new")
        self.assertEqual(back["history"][0]["event"], "created")
        self.assertEqual(list_ids(self.root, "question"), ["Q-0001"])

    def test_save_is_atomic_no_tmp_left(self):
        save(self.root, new_record(KINDS["goal"], "G-0001", {"text": "g"}))
        names = [p.name for p in (self.root / "profiles" / "goal").iterdir()]
        self.assertEqual(names, ["G-0001.json"])

    def test_load_rejects_path_tricks(self):
        with self.assertRaises(ValueError):
            load(self.root, "../etc/passwd", KINDS)


if __name__ == "__main__":
    unittest.main()
