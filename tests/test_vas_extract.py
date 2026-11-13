"""The extractor on a drafted-style file: the agent wrote the definitions, a helper used only in a proof, an added
axiom. Expect: the statement's dependencies extracted (not the helper), the axiom listed with its statement, the
extract compiling alone with an identical conclusion.

Run: python3 -m unittest tests.test_vas_extract -v
"""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class Extract(unittest.TestCase):
    def test_drafted(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "x"
            r = subprocess.run(["python3", "src/vas_extract.py", "tests/vas_extract/drafted.lean",
                                "--theorem", "summer_catch", "--out", str(out)], cwd=ROOT, capture_output=True,
                               text=True, timeout=900)
            rep = json.loads(r.stdout)
            self.assertTrue(rep["ok"], rep)
            self.assertEqual(rep["assumption_declarations"],
                             ["Lake.catchRate", "Lake.Season", "Lake.summer", "totalCatch"])
            self.assertEqual([(a["kind"], a["name"]) for a in rep["added_assumptions"]], [("axiom", "onlyCarp")])
            self.assertIn("s.days > 0", rep["added_assumptions"][0]["statement"])
            text = out.with_suffix(".lean").read_text()
            self.assertNotIn("helper", text)
            self.assertEqual(text.count("structure Season"), 1)


if __name__ == "__main__":
    unittest.main()
