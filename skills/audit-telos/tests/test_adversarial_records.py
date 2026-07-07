#!/usr/bin/env python3
"""Adversarial telos records — what happens when the record itself is the attack.

The telos evidence tier exists so a completion claim is only as good as its backing. These tests
feed telos_check.py records crafted the way a lazy or adversarial author (human or loop) would
craft them, and pin the outcome — including the outcomes where the attack SUCCEEDS. A residual
that silently starts being caught is an undocumented behavior change, so the successful attacks
are pinned bidirectionally (the pin fails if the state changes in EITHER direction).

The honest boundary these tests draw:
  * telos_check verifies claim↔witness LINKAGE and the witness's EXIT CODE — it does not judge
    witness QUALITY. A witness that always passes (`true`, an assert-nothing test) yields a
    DISCHARGED at the witness tier. Catching that requires an out-of-loop reviewer or a frozen
    oracle (skills/ralph-loop/scripts/check_suite_frozen.py) — by design, not omission: the same
    two-axis split as the guards (an in-record check the author controls could never be trusted
    to grade the author's witness anyway).

Run:  python3 skills/audit-telos/tests/test_adversarial_records.py
"""
from __future__ import annotations

import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve()
sys.path.insert(0, str(_HERE.parents[1]))  # audit-telos/ (telos_check.py)
import telos_check as tc  # noqa: E402


def _repo(tmp: Path, telos_md: str, sources: dict[str, str] | None = None) -> Path:
    (tmp / "docs" / "telos").mkdir(parents=True)
    (tmp / "docs" / "telos" / "app.md").write_text(textwrap.dedent(telos_md), encoding="utf-8")
    for rel, body in (sources or {}).items():
        p = tmp / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(textwrap.dedent(body), encoding="utf-8")
    return tmp


SRC = """\
    def run(records):
        out = []
        for r in records:
            out.append(r)
        return out
    """


def _record(state: str = "DISCHARGED", discharged_by: str = "export.py::run",
            verified_by: "str | None" = None) -> str:
    lines = [
        "# Telos — adversarial fixture", "",
        "## Motive", "Exists to be attacked.", "",
        "## Telos", "Survive its author.", "",
        "## Claims", "",
        "### TELOS-001 — the claim under attack",
        f"- state: {state}",
        "- intent: pin the adversarial outcome",
        f"- discharged-by: {discharged_by}",
        "- contract: run() returns its input",
    ]
    if verified_by is not None:
        lines.append(f"- verified-by: {verified_by}")
    lines += ["- last-grilled: 2026-07-07", "- anchor: none"]
    return "\n".join(lines) + "\n"


class TestForgedBacking(unittest.TestCase):
    """Attacks on the DISCHARGED state's backing."""

    def _audit(self, md: str, sources: "dict | None" = None) -> dict:
        with tempfile.TemporaryDirectory() as td:
            return tc.audit(_repo(Path(td), md, sources if sources is not None else {"export.py": SRC}))

    def test_blank_witness_discharged_demotes_to_suspect(self):
        # `verified-by:` present but whitespace-only is the same forgery as absent — an author
        # asserting DISCHARGED with nothing behind it. The demotion is READ-time (in the parsed
        # representation every consumer routes through), so no downstream check can see the forged
        # DISCHARGED at all.
        with tempfile.TemporaryDirectory() as td:
            rec = tc.parse_record(_repo(Path(td), _record(verified_by=" "), {"export.py": SRC}))
        self.assertEqual(rec.claims[0].fields["state"], "SUSPECT",
                         "a whitespace-only witness must not back a DISCHARGED")
        self.assertTrue(rec.claims[0].demoted_reason)

    def test_always_pass_witness_is_NOT_caught(self):
        # THE PINNED RESIDUAL: a witness of `true` exits 0, so the claim lands DISCHARGED at the
        # witness tier. telos_check trusts the exit code; it does not judge witness quality. If this
        # test ever fails because the state is no longer DISCHARGED, telos_check has started
        # catching it — update this pin AND this module's boundary docstring together.
        result = self._audit(_record(verified_by="true"))
        c = result["claims"][0]
        self.assertEqual((c["state"], c["tier"]), ("DISCHARGED", "witness"),
                         "pinned residual changed: an always-pass witness used to sail through — "
                         "if telos_check now catches it, update this module's boundary docstring")

    def test_witness_naming_a_nonexistent_test_fails_the_claim(self):
        # A witness pointing at a test that does not exist must fail (pytest exits non-zero on an
        # unresolvable node id) → DRIFTED, never a silent pass.
        result = self._audit(_record(verified_by="export.py::test_that_does_not_exist"))
        self.assertEqual(result["claims"][0]["state"], "DRIFTED")

    def test_witness_cannot_smuggle_shell(self):
        # The command form is run WITHOUT a shell; `true; rm -rf x` is a single (nonexistent)
        # executable named `true;`, so the witness fails closed → DRIFTED, and nothing executes.
        result = self._audit(_record(verified_by="true; rm -rf x"))
        self.assertEqual(result["claims"][0]["state"], "DRIFTED",
                         "a shell-metacharacter witness must fail closed, not spawn a shell")

    def test_nonexistent_symbol_fails_loud_as_unmet(self):
        # Pointing the claim at a symbol that is not in the tree must be UNMET (HIGH), not a pass.
        result = self._audit(_record(discharged_by="export.py::vanished"))
        c = result["claims"][0]
        self.assertEqual((c["state"], c["severity"]), ("UNMET", "HIGH"))


class TestPoisonedRecord(unittest.TestCase):
    """Attacks on the record text itself — the strict parser must refuse, never skip."""

    def _parse(self, md: str):
        with tempfile.TemporaryDirectory() as td:
            return tc.parse_record(_repo(Path(td), md, {"export.py": SRC}))

    def test_homoglyph_state_raises(self):
        # "DISСHARGED" with a Cyrillic Es looks identical to DISCHARGED in most fonts but is a
        # different string; the whitelist must reject it loudly rather than treat it as any state.
        with self.assertRaises(tc.TelosError):
            self._parse(_record(state="DISСHARGED", verified_by="true"))

    def test_homoglyph_key_raises(self):
        # A look-alike KEY (`ѕtate:` with a Cyrillic dze) must hit the unknown-key branch, not
        # silently coexist with a missing real `state`.
        md = _record(verified_by="true").replace("- state:", "- ѕtate:")
        with self.assertRaises(tc.TelosError):
            self._parse(md)


if __name__ == "__main__":
    unittest.main(verbosity=2)
