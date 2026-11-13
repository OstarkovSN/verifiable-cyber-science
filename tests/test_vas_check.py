"""Checker controls: bodies under tests/vas_controls/<task>/ named accept_* must pass, reject_* must fail,
conditional_* (an added axiom or a sorry) must not pass but come back "proved_if" with every used addition listed by
its statement, and noverdict_* must come back "no_verdict". EXPECT_LISTED adds a statement each listing must contain.

They are the negative controls and soundness probes reported in docs/preprint/framework.md. Each one runs a real Lean
call (about 10-40 s), into a temporary trail so the committed trail is not touched.

Run: python3 -m unittest tests.test_vas_check -v
"""
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import vas_check  # noqa: E402

CONTROLS = ROOT / "tests/vas_controls"
EXPECT_LISTED = {"conditional_fourth_gap": "⊢ False", "conditional_gap_type": "⊢ False",
                 "conditional_poly": "(α : Sort", "conditional_inline_axiom": "False",
                 "conditional_axiom_contradicts_card": "mCO2 = 0", "conditional_axiom": "6 * mCO2",
                 "accept_unused_axiom_listed": "False", "conditional_gap_in_axiom_type": "⊢ False",
                 "conditional_let_gap": ":= 1", "conditional_long_axiom": "True ∧ True ∧ False"}


class CheckerControls(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.saved = vas_check.TRAIL
        vas_check.TRAIL = Path(self.tmp.name)

    def tearDown(self):
        vas_check.TRAIL = self.saved
        self.tmp.cleanup()

    def test_controls(self):
        bodies = sorted(CONTROLS.glob("*/*.lean"))
        self.assertTrue(bodies, "no control bodies found")
        for body in bodies:
            task, name = body.parent.name, body.stem
            with self.subTest(task=task, control=name):
                rec = vas_check.check(task, body.read_text(), "controls", name.replace("_", "-"))
                self.assertEqual(rec["ok"], name.startswith("accept_"), rec.get("error") or rec.get("errors"))
                listing = rec.get("added_assumptions", [])
                if name.startswith("conditional_"):
                    self.assertEqual(rec["verdict"], "proved_if")
                    used = {a for c in rec["conditional_on"].values() for a in c}
                    listed = {a["name"] for a in listing if a["kind"] == "axiom" and a["used"] and a["statement"]}
                    gaps = [a for a in listing if a["kind"] == "gap" and a["used"] and a["statement"]]
                    self.assertEqual(listed, used - {"sorryAx"})
                    self.assertEqual(bool(gaps), "sorryAx" in used)
                if name.startswith("noverdict_"):
                    self.assertEqual(rec["verdict"], "no_verdict")
                self.assertFalse(any("⋯" in a["statement"] for a in listing if a["used"]) and rec["ok"])
                if name in EXPECT_LISTED:
                    self.assertTrue(any(EXPECT_LISTED[name] in a["statement"] for a in listing), listing)

    def test_kernel_recheck(self):
        """OT-1861: with the contract bypassed, the forged body compiles (Lean exit 0) and only leanchecker stops it."""
        body = (CONTROLS / "photosynthesis/reject_kernel_skip.lean").read_text()
        with self.assertRaises(ValueError):
            vas_check.validate(body, ["balanced_example"])
        saved, vas_check.validate = vas_check.validate, lambda src, req: list(req)
        try:
            rec = vas_check.check("photosynthesis", body, "controls", "kernel-skip")
        finally:
            vas_check.validate = saved
        self.assertEqual(rec["exit_code"], 0)
        self.assertNotEqual(rec["kernel_recheck"], 0)
        self.assertEqual(rec["verdict"], "not_proved")

    def test_listed_marker_is_a_line(self):
        self.assertIsNone(vas_check.listed("NOT_VAS_LISTED_YET\n"))
        self.assertEqual(vas_check.listed("x\nVAS_LISTED\n"), [])

if __name__ == "__main__":
    unittest.main()
