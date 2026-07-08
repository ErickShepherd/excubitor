#!/usr/bin/env python3
"""Tests for telos_check.py — the deterministic spine of the telos conformance audit.

Pins the load-bearing properties: the strict parser's never-silent-pass invariants (stray line / dup key /
missing field / bad state RAISE; absent/empty/malformed record ABORTS), static-AST symbol resolution
(hit/miss/UNMET, no execution), accounted-for transitive closure + candidate-orphan set-difference, anchor
+ staleness → SUSPECT, coverage %, an executable verified-by witness forcing DRIFTED mechanically, and the
round-trip — the emitted ledger parses through the UNMODIFIED audit_accuracy.py with the telos facets.

Run:  python3 skills/audit-telos/tests/test_telos_check.py
   or python3 skills/audit-telos/telos_check.py --self-test
"""
from __future__ import annotations

import sys
import tempfile
import textwrap
import unittest
from datetime import date
from pathlib import Path

_HERE = Path(__file__).resolve()
sys.path.insert(0, str(_HERE.parents[1]))                       # audit-telos/  (telos_check.py)
sys.path.insert(0, str(_HERE.parents[2] / "audit-repo"))        # skills/audit-repo/ (audit_accuracy.py)
import telos_check as tc  # noqa: E402

# audit_accuracy.py is a private sibling (the audit-repo skill) not shipped in this extraction; the
# three ledger round-trip tests that consume emitted ledgers through its parser skip without it.
try:
    import audit_accuracy as aa  # noqa: E402
except ImportError:
    aa = None
_NEEDS_AA = unittest.skipIf(aa is None, "requires the private audit-repo sibling (audit_accuracy.py)")


def _repo(tmp: Path, telos_md: str, sources: dict[str, str] | None = None) -> Path:
    """Build a throwaway repo: docs/telos/app.md + optional source files."""
    (tmp / "docs" / "telos").mkdir(parents=True)
    (tmp / "docs" / "telos" / "app.md").write_text(textwrap.dedent(telos_md), encoding="utf-8")
    for rel, body in (sources or {}).items():
        p = tmp / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(textwrap.dedent(body), encoding="utf-8")
    return tmp


GOOD_RECORD = """\
    # Telos — demo

    ## Motive
    Why this exists: exports must never leak PII.

    ## Telos
    The purpose: no raw PII ever leaves the process.

    ## Claims

    ### TELOS-001 — export redacts PII before write
    - state: DISCHARGED
    - intent: No export leaves with raw PII.
    - discharged-by: export.py::run
    - contract: run() redacts every record before any write
    - last-grilled: 2026-06-15
    - anchor: none
    """

SRC_EXPORT = """\
    def redact(rec):
        return {k: '***' for k in rec}

    def run(records):
        out = []
        for r in records:
            out.append(redact(r))
        return out
    """


class TestStrictParser(unittest.TestCase):
    def _parse(self, md, sources=None):
        with tempfile.TemporaryDirectory() as td:
            return tc.parse_record(_repo(Path(td), md, sources))

    def test_good_record_parses(self):
        rec = self._parse(GOOD_RECORD, {"export.py": SRC_EXPORT})
        self.assertEqual(len(rec.claims), 1)
        self.assertEqual(rec.claims[0].id, "TELOS-001")
        self.assertIn("no raw PII", rec.telos)
        self.assertIn("leak PII", rec.motive)

    def test_stray_line_raises(self):
        bad = GOOD_RECORD + "    this is a stray prose line inside no block? \n"
        # put the stray line *inside* a claim block:
        bad = GOOD_RECORD.replace("- anchor: none\n", "- anchor: none\n    stray unrecognized line\n")
        with self.assertRaises(tc.TelosError):
            self._parse(bad, {"export.py": SRC_EXPORT})

    def test_block_comment_inside_claim_parses(self):
        # F1 regression: a multi-line `<!-- ... -->` block comment inside a claim block is normal Markdown
        # and must parse (the single-line-only skip used to raise at the continuation line).
        block = ("    <!--\n"
                 "    a multi-line note\n"
                 "    spanning several lines\n"
                 "    -->\n")
        md = GOOD_RECORD.replace("- anchor: none\n", "- anchor: none\n" + block)
        rec = self._parse(md, {"export.py": SRC_EXPORT})
        self.assertEqual(rec.claims[0].fields["anchor"], "none")
        self.assertEqual(rec.claims[0].fields["discharged-by"], "export.py::run")

    def test_unterminated_block_comment_raises(self):
        # F1 strictness: a `<!--` the claim block never closes must RAISE, not silently swallow the rest —
        # the whole point of this parser is never-silent-pass.
        block = ("    <!--\n"
                 "    an unterminated note with no closing marker\n")
        md = GOOD_RECORD.replace("- anchor: none\n", "- anchor: none\n" + block)
        with self.assertRaises(tc.TelosError):
            self._parse(md, {"export.py": SRC_EXPORT})

    def test_duplicate_key_raises(self):
        bad = GOOD_RECORD.replace("- anchor: none\n", "- anchor: none\n    - state: UNMET\n")
        with self.assertRaises(tc.TelosError):
            self._parse(bad, {"export.py": SRC_EXPORT})

    def test_missing_required_field_raises(self):
        bad = GOOD_RECORD.replace("    - contract: run() redacts every record before any write\n", "")
        with self.assertRaises(tc.TelosError):
            self._parse(bad, {"export.py": SRC_EXPORT})

    def test_invalid_state_raises(self):
        bad = GOOD_RECORD.replace("- state: DISCHARGED", "- state: PROBABLY_FINE")
        with self.assertRaises(tc.TelosError):
            self._parse(bad, {"export.py": SRC_EXPORT})

    def test_unknown_key_raises(self):
        bad = GOOD_RECORD.replace("- anchor: none\n", "- anchor: none\n    - vibe: good\n")
        with self.assertRaises(tc.TelosError):
            self._parse(bad, {"export.py": SRC_EXPORT})

    def test_bad_discharged_by_shape_raises(self):
        bad = GOOD_RECORD.replace("- discharged-by: export.py::run", "- discharged-by: export.py run")
        with self.assertRaises(tc.TelosError):
            self._parse(bad, {"export.py": SRC_EXPORT})

    def test_empty_anchor_raises(self):
        # finding 3 regression: an empty anchor must not validate (it can never match content_hash →
        # would silently pin the claim to permanent SUSPECT)
        bad = GOOD_RECORD.replace("- anchor: none", "- anchor:")
        with self.assertRaises(tc.TelosError):
            self._parse(bad, {"export.py": SRC_EXPORT})

    def test_wrong_length_anchor_raises(self):
        bad = GOOD_RECORD.replace("- anchor: none", "- anchor: abc")  # too short to ever match
        with self.assertRaises(tc.TelosError):
            self._parse(bad, {"export.py": SRC_EXPORT})

    def test_source_anchor_preserved(self):
        # DEF-1 regression: `source: path#anchor` must keep its #anchor (it is part of the value, not a
        # trailing comment) — the documented provenance format depends on it.
        md = GOOD_RECORD.replace("- anchor: none", "- source: CLAUDE.md#some-anchor\n    - anchor: none")
        rec = self._parse(md, {"export.py": SRC_EXPORT})
        self.assertEqual(rec.claims[0].fields["source"], "CLAUDE.md#some-anchor")

    def test_trailing_comment_still_stripped(self):
        # the ` # comment` strip (whitespace-then-hash) still works for a real trailing comment.
        md = GOOD_RECORD.replace("- discharged-by: export.py::run",
                                 "- discharged-by: export.py::run   # the entry point")
        rec = self._parse(md, {"export.py": SRC_EXPORT})
        self.assertEqual(rec.claims[0].fields["discharged-by"], "export.py::run")

    def test_absent_record_aborts(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(tc.TelosError):
                tc.parse_record(Path(td))

    def test_empty_record_aborts(self):
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "docs" / "telos").mkdir(parents=True)
            with self.assertRaises(tc.TelosError):
                tc.parse_record(Path(td))

    def test_zero_claims_aborts(self):
        md = "# Telos\n\n## Motive\nx\n\n## Telos\ny\n\n## Claims\n"
        with self.assertRaises(tc.TelosError):
            self._parse(md)

    def test_audit_aborts_on_broken_record(self):
        # TELOS-008 witness target: the full audit() (not just parse_record) must ABORT on an absent or
        # empty record rather than manufacture a clean pass. This is the test the seeded verified-by witness
        # in docs/telos/app.md executes — keep it single-purpose and about audit().
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(tc.TelosError):
                tc.audit(Path(td))                          # absent record dir
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "docs" / "telos").mkdir(parents=True)
            with self.assertRaises(tc.TelosError):
                tc.audit(Path(td))                          # present but empty record dir


class TestSupersede(unittest.TestCase):
    def test_superseded_claim_skipped_by_audit(self):
        md = textwrap.dedent(GOOD_RECORD) + textwrap.dedent("""
            ### TELOS-000 — old export name (retired)
            - state: DISCHARGED
            - intent: superseded by TELOS-001 after a rename.
            - discharged-by: export.py::old_run
            - contract: old_run redacts
            - superseded-by: TELOS-001
        """)
        with tempfile.TemporaryDirectory() as td:
            r = tc.audit(_repo(Path(td), md, {"export.py": SRC_EXPORT}), run_witnesses=False)
        ids = {c["id"] for c in r["claims"]}
        self.assertIn("TELOS-001", ids)
        self.assertNotIn("TELOS-000", ids)  # retired → not audited, but still parsed (history preserved)

    def test_fingerprint_folds_in_verified_by(self):
        # Removing/adding the executable witness must BUST the incremental cache key, or a now-unbacked
        # DISCHARGED would carry forward forever as tier=cache without the witness re-running.
        with_witness = tc.claim_fingerprint("code", "contract", "intent", "tests/t.py::x")
        without = tc.claim_fingerprint("code", "contract", "intent", "")
        self.assertNotEqual(with_witness, without)

    def test_witness_tier_prior_without_judged_receipt_does_not_carry(self):
        # The witness-removal hole: a claim DISCHARGED at witness tier last run (empty `judged` date),
        # whose verified-by is now gone, must NOT silently carry forward as tier=cache — it must re-judge.
        with tempfile.TemporaryDirectory() as td:
            repo = _repo(Path(td), GOOD_RECORD, {"export.py": SRC_EXPORT})  # DISCHARGED, no verified-by
            first = tc.audit(repo, run_witnesses=False)
            c0 = first["claims"][0]
            # simulate last run's ledger row: DISCHARGED at witness tier, empty judged receipt, same hash
            prior = {c0["id"]: (c0["source_hash"], "DISCHARGED", "witness", "")}
            c1 = tc.audit(repo, run_witnesses=False, prior=prior)["claims"][0]
        self.assertNotEqual(c1.get("tier"), "cache", "a witness prior with no judged receipt must not carry")
        self.assertTrue(c1["needs_judgment"], "it must be re-judged instead of silently carried forward")

    def test_nul_byte_source_does_not_abort_audit(self):
        # A first-party .py containing an embedded NUL byte makes ast.parse raise ValueError (not
        # SyntaxError); build_graph/resolve_pointer must skip it, not crash the whole audit — the
        # untrusted-repo-safe guarantee. audit() must complete and still see the good claim.
        with tempfile.TemporaryDirectory() as td:
            repo = _repo(Path(td), GOOD_RECORD, {"export.py": SRC_EXPORT, "poison.py": "x = '\x00'\n"})
            r = tc.audit(repo, run_witnesses=False)  # must not raise
        self.assertIn("TELOS-001", {c["id"] for c in r["claims"]})

    def test_dangling_superseded_by_raises(self):
        # DEF-5 regression: superseded-by a well-formed but NONEXISTENT id must abort, not silently retire
        # the live claim (audit() skips any superseded claim, so a typo'd target makes a real purpose vanish).
        md = GOOD_RECORD.replace("- anchor: none", "- superseded-by: TELOS-999\n    - anchor: none")
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(tc.TelosError):
                tc.parse_record(_repo(Path(td), md, {"export.py": SRC_EXPORT}))

    def test_self_superseded_by_raises(self):
        # DEF-5: a claim cannot supersede itself (that would retire itself, leaving nothing).
        md = GOOD_RECORD.replace("- anchor: none", "- superseded-by: TELOS-001\n    - anchor: none")
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(tc.TelosError):
                tc.parse_record(_repo(Path(td), md, {"export.py": SRC_EXPORT}))

    def test_bad_superseded_by_raises(self):
        md = GOOD_RECORD.replace("- anchor: none", "- superseded-by: not-an-id\n    - anchor: none")
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(tc.TelosError):
                tc.parse_record(_repo(Path(td), md, {"export.py": SRC_EXPORT}))


class TestResolver(unittest.TestCase):
    def test_resolve_hit_and_miss(self):
        with tempfile.TemporaryDirectory() as td:
            repo = _repo(Path(td), GOOD_RECORD, {"export.py": SRC_EXPORT})
            ok, node, seg = tc.resolve_pointer(repo, "export.py::run")
            self.assertTrue(ok)
            self.assertIn("def run", seg)
            self.assertFalse(tc.resolve_pointer(repo, "export.py::ghost")[0])
            self.assertFalse(tc.resolve_pointer(repo, "missing.py::run")[0])

    def test_resolve_is_repo_confined(self):
        # A discharged-by pointer must not escape the repo: an absolute path or `..` traversal (which
        # would turn the resolver into a file-exists/valid-Python oracle outside the tree) resolves to
        # not-found, never reading the out-of-repo file.
        with tempfile.TemporaryDirectory() as td:
            repo = _repo(Path(td), GOOD_RECORD, {"export.py": SRC_EXPORT})
            # a real, definitely-existing outside file — must still resolve False (never read)
            self.assertFalse(tc.resolve_pointer(repo, "/etc/hostname::x")[0])
            self.assertFalse(tc.resolve_pointer(repo, "../../../../etc/hostname::x")[0])
            self.assertFalse(tc.resolve_pointer(repo, "../secret.py::y")[0])

    def test_resolver_never_executes(self):
        # a module with an import-time side effect must resolve via AST without triggering it
        boom = "raise RuntimeError('import-time side effect should never fire')\n\ndef run():\n    return 1\n"
        with tempfile.TemporaryDirectory() as td:
            repo = _repo(Path(td), GOOD_RECORD, {"export.py": boom})
            ok, _, _ = tc.resolve_pointer(repo, "export.py::run")
            self.assertTrue(ok)  # no RuntimeError => never imported/executed


class TestStates(unittest.TestCase):
    def test_unmet_when_pointer_none(self):
        md = GOOD_RECORD.replace("- discharged-by: export.py::run", "- discharged-by: none")
        with tempfile.TemporaryDirectory() as td:
            r = tc.audit(_repo(Path(td), md, {"export.py": SRC_EXPORT}), run_witnesses=False)
        c = r["claims"][0]
        self.assertEqual(c["state"], "UNMET")
        self.assertEqual(c["facet"], "telos-unmet")

    def test_unmet_when_symbol_absent(self):
        md = GOOD_RECORD.replace("export.py::run", "export.py::vanished")
        with tempfile.TemporaryDirectory() as td:
            r = tc.audit(_repo(Path(td), md, {"export.py": SRC_EXPORT}), run_witnesses=False)
        self.assertEqual(r["claims"][0]["state"], "UNMET")

    def test_resolved_needs_judgment(self):
        with tempfile.TemporaryDirectory() as td:
            r = tc.audit(_repo(Path(td), GOOD_RECORD, {"export.py": SRC_EXPORT}), run_witnesses=False)
        c = r["claims"][0]
        self.assertTrue(c["needs_judgment"])
        self.assertIsNone(c["state"])

    def test_staleness_suspect(self):
        md = GOOD_RECORD.replace("- last-grilled: 2026-06-15", "- last-grilled: 2020-01-01")
        with tempfile.TemporaryDirectory() as td:
            r = tc.audit(_repo(Path(td), md, {"export.py": SRC_EXPORT}),
                         run_witnesses=False, today=date(2026, 6, 15))
        self.assertEqual(r["claims"][0]["state"], "SUSPECT")

    def test_anchor_mismatch_suspect(self):
        md = GOOD_RECORD.replace("- anchor: none", "- anchor: deadbeefdeadbeef")
        with tempfile.TemporaryDirectory() as td:
            r = tc.audit(_repo(Path(td), md, {"export.py": SRC_EXPORT}), run_witnesses=False)
        self.assertEqual(r["claims"][0]["state"], "SUSPECT")
        self.assertIn("anchor", r["claims"][0]["rationale"])

    def test_anchor_match_not_suspect(self):
        with tempfile.TemporaryDirectory() as td:
            repo = _repo(Path(td), GOOD_RECORD, {"export.py": SRC_EXPORT})
            _, _, seg = tc.resolve_pointer(repo, "export.py::run")
            h = tc.content_hash(seg)
            md = GOOD_RECORD.replace("- anchor: none", f"- anchor: {h}")
            repo2 = _repo(Path(tempfile.mkdtemp()), md, {"export.py": SRC_EXPORT})
            r = tc.audit(repo2, run_witnesses=False)
        self.assertTrue(r["claims"][0]["needs_judgment"])  # matched anchor → falls through to LLM judgment


class TestWitness(unittest.TestCase):
    def test_failing_witness_forces_drifted(self):
        md = GOOD_RECORD.replace(
            "- anchor: none",
            "- verified-by: python3 -c \"raise SystemExit(1)\"\n    - anchor: none")
        with tempfile.TemporaryDirectory() as td:
            r = tc.audit(_repo(Path(td), md, {"export.py": SRC_EXPORT}), run_witnesses=True)
        c = r["claims"][0]
        self.assertEqual(c["state"], "DRIFTED")
        self.assertFalse(c["needs_judgment"])  # mechanical — LLM not consulted

    def test_passing_witness_discharges(self):
        md = GOOD_RECORD.replace(
            "- anchor: none",
            "- verified-by: python3 -c \"raise SystemExit(0)\"\n    - anchor: none")
        with tempfile.TemporaryDirectory() as td:
            r = tc.audit(_repo(Path(td), md, {"export.py": SRC_EXPORT}), run_witnesses=True)
        self.assertEqual(r["claims"][0]["state"], "DISCHARGED")

    def test_malformed_witness_fails_closed(self):
        # follow-up: a witness spec with an unbalanced quote must fail the witness (→ DRIFTED), not crash the
        # audit with an uncaught shlex.split ValueError — fail closed, like a non-zero exit.
        ok, detail = tc.run_witness(Path("."), 'echo "unterminated')
        self.assertFalse(ok)
        self.assertIn("not parseable", detail)
        # and the audit completes (DRIFTED), rather than raising
        md = GOOD_RECORD.replace("- anchor: none",
                                 "- verified-by: echo \"unterminated\n    - anchor: none")
        with tempfile.TemporaryDirectory() as td:
            r = tc.audit(_repo(Path(td), md, {"export.py": SRC_EXPORT}), run_witnesses=True)
        self.assertEqual(r["claims"][0]["state"], "DRIFTED")

    def test_witness_route_discriminator(self):
        # DEF-2 regression: a parametrized pytest node id (whose [param] contains a space) must still route
        # to pytest, not the shell-command branch (which would fail to run → silent false DRIFTED).
        self.assertTrue(tc._witness_is_pytest_nodeid("tests/x.py::TestC::test_thing[a b]"))
        self.assertTrue(tc._witness_is_pytest_nodeid("tests/x.py::test_thing"))
        # genuine command lines must NOT route to pytest
        self.assertFalse(tc._witness_is_pytest_nodeid('python3 -c "raise SystemExit(1)"'))
        self.assertFalse(tc._witness_is_pytest_nodeid("./check.sh a::b"))   # whitespace in the head segment
        self.assertFalse(tc._witness_is_pytest_nodeid("mytool::sub"))       # head is not a .py file


class TestAccountedForAndCoverage(unittest.TestCase):
    SRC = {
        "app.py": """\
            def helper_a():
                return 1
            def helper_b():
                return 2
            def main():
                helper_a()
                helper_b()
                return 0
            def unclaimed_feature():
                rows = []
                rows.append('nobody claims me but I am public')
                return rows
        """,
        "export.py": SRC_EXPORT,
    }
    REC = """\
        # Telos — demo
        ## Motive
        m
        ## Telos
        t
        ## Claims
        ### TELOS-001 — main orchestrates
        - state: DISCHARGED
        - intent: main runs the pipeline
        - discharged-by: app.py::main
        - contract: main calls the helpers
    """

    def test_transitive_callees_accounted(self):
        with tempfile.TemporaryDirectory() as td:
            r = tc.audit(_repo(Path(td), self.REC, self.SRC), run_witnesses=False)
        # main + helper_a + helper_b accounted; unclaimed_feature is a candidate orphan
        cand = {c["target"] for c in r["candidates"]}
        self.assertIn("app.py::unclaimed_feature", cand)
        self.assertNotIn("app.py::main", cand)
        self.assertIsNotNone(r["coverage"])

    METHOD_SRC = {
        "svc.py": """\
            class Exporter:
                def run(self):
                    return self.redact()
                def redact(self):
                    return 'ok'
                def unclaimed_method(self):
                    log = []
                    log.append('public but unclaimed')
                    return log
            def standalone_orphan():
                rows = []
                rows.append(1)
                return rows
        """,
    }
    METHOD_REC = """\
        # Telos — demo
        ## Motive
        m
        ## Telos
        t
        ## Claims
        ### TELOS-001 — exporter run is claimed
        - state: DISCHARGED
        - intent: run drives the export
        - discharged-by: svc.py::Exporter.run
        - contract: run redacts then exports
    """

    def test_method_claim_does_not_orphan_its_class(self):
        # finding 1 regression: claiming Exporter.run must NOT report the class Exporter as an orphan,
        # and must NOT drag sibling methods (unclaimed_method) into accounted-for
        with tempfile.TemporaryDirectory() as td:
            r = tc.audit(_repo(Path(td), self.METHOD_REC, self.METHOD_SRC), run_witnesses=False)
        cand = {c["target"] for c in r["candidates"]}
        self.assertNotIn("svc.py::Exporter", cand)        # class un-orphaned by its claimed method
        self.assertGreater(r["accounted_for"], 0)          # coverage no longer wrongly 0
        self.assertIn("svc.py::Exporter.unclaimed_method", cand)  # sibling NOT covered (no leak)
        self.assertIn("svc.py::standalone_orphan", cand)

    COLLIDE_SRC = {
        "core.py": """\
            def process(x):           # reached by main; trivial one-liner (not significant itself)
                return x + 1
            def main():
                return process(2)
        """,
        "dead.py": """\
            def process(data):        # GENUINE orphan: never called; bare name collides with core.process
                out = []
                out.append(data)
                return out
        """,
    }
    COLLIDE_REC = """\
        # Telos — demo
        ## Motive
        m
        ## Telos
        t
        ## Claims
        ### TELOS-001 — main is claimed
        - state: DISCHARGED
        - intent: main runs the pipeline
        - discharged-by: core.py::main
        - contract: main calls process
    """

    def test_bare_name_collision_does_not_hide_orphan(self):
        # DEF-3 regression: claiming core.py::main (which calls process()) must NOT swallow the unrelated
        # dead.py::process into accounted-for via the shared bare name "process". Over-linking that hides a
        # genuine orphan is the unsafe direction; resolution prefers the same-module callee.
        with tempfile.TemporaryDirectory() as td:
            r = tc.audit(_repo(Path(td), self.COLLIDE_REC, self.COLLIDE_SRC), run_witnesses=False)
        cand = {c["target"] for c in r["candidates"]}
        self.assertIn("dead.py::process", cand)        # the real orphan is surfaced, not hidden
        self.assertNotIn("core.py::main", cand)        # the claimed symbol stays accounted-for

    def test_bootstrap_lists_surface_without_record(self):
        # finding 2 regression: a claimless repo has no record, so audit aborts — bootstrap must still work
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            (repo / "svc.py").write_text(textwrap.dedent(self.METHOD_SRC["svc.py"]), encoding="utf-8")
            with self.assertRaises(tc.TelosError):
                tc.audit(repo)                              # no record → aborts
            surface = tc.bootstrap_surface(repo)            # but bootstrap enumerates anyway
        self.assertTrue(surface["python_repo"])
        self.assertGreater(surface["count"], 0)
        self.assertIn("svc.py::standalone_orphan", surface["significant_surface"])

    def test_tmp_scratch_excluded_from_surface(self):
        # F2 regression: scratch code under tmp/ is the established convention (CLAUDE.md), not product
        # surface — it must not be walked into bootstrap_surface or audited as an orphan candidate.
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            (repo / "svc.py").write_text(textwrap.dedent(self.METHOD_SRC["svc.py"]), encoding="utf-8")
            (repo / "tmp").mkdir()
            (repo / "tmp" / "rt.py").write_text("def rt():\n    return 1\n", encoding="utf-8")
            surface = tc.bootstrap_surface(repo)
        joined = "\n".join(surface["significant_surface"])
        self.assertIn("svc.py::standalone_orphan", surface["significant_surface"])
        self.assertNotIn("tmp/rt.py::rt", surface["significant_surface"])
        self.assertNotIn("tmp", joined)  # nothing from tmp/ leaks into the surface

    def test_non_python_repo_skips_orphan(self):
        with tempfile.TemporaryDirectory() as td:
            repo = _repo(Path(td), self.REC.replace("app.py::main", "app.js::main"))
            # only a non-py source; symbol won't resolve → UNMET, and no python surface
            r = tc.audit(repo, run_witnesses=False)
        self.assertEqual(r["candidates"], [])
        self.assertFalse(r["python_repo"])


class TestNeighborhood(unittest.TestCase):
    """The DRIFTED judge's evidence window: a needs_judgment claim carries its 1-hop resolved callees as
    `neighbors` pointers, so a purpose-bearing distinction pushed into a callee is visible (closing the
    pointer-anchored blind spot). Neighbors reuse build_graph's DEF-3-safe edges."""

    REC = """\
        # Telos — demo
        ## Motive
        m
        ## Telos
        t
        ## Claims
        ### TELOS-001 — run guards before it persists
        - state: DISCHARGED
        - intent: run only persists guarded input
        - discharged-by: app.py::run
        - contract: run guards before it persists
    """

    def _claim(self, repo, run_witnesses=False):
        r = tc.audit(repo, run_witnesses=run_witnesses)
        return next(c for c in r["claims"] if c["id"] == "TELOS-001")

    def test_callees_surfaced_as_neighbors(self):
        src = {"app.py": """\
            def guard(x):
                return x is not None
            def persist(x):
                return ('written', x)
            def run(x):
                if guard(x):
                    return persist(x)
                return None
        """}
        with tempfile.TemporaryDirectory() as td:
            c = self._claim(_repo(Path(td), self.REC, src))
        self.assertTrue(c["needs_judgment"])
        self.assertIn("app.py::guard", c["neighbors"])      # drift into either callee is now in-window
        self.assertIn("app.py::persist", c["neighbors"])
        self.assertFalse(c["neighbors_truncated"])

    def test_cap_honored_and_truncation_flagged(self):
        callees = "".join(f"    def f{i}(): return {i}\n" for i in range(tc.NEIGHBOR_CAP + 3))
        body = "".join(f"        f{i}()\n" for i in range(tc.NEIGHBOR_CAP + 3))
        src = {"app.py": callees + "    def run():\n" + body + "        return 0\n"}
        with tempfile.TemporaryDirectory() as td:
            c = self._claim(_repo(Path(td), self.REC, src))
        self.assertEqual(len(c["neighbors"]), tc.NEIGHBOR_CAP)
        self.assertTrue(c["neighbors_truncated"])

    def test_no_callees_means_empty_neighbors(self):
        # run calls only a builtin (len) — not a repo def → no neighbor, no crash, not truncated.
        src = {"app.py": "def run(x):\n    n = len(x)\n    return n\n"}
        with tempfile.TemporaryDirectory() as td:
            c = self._claim(_repo(Path(td), self.REC, src))
        self.assertEqual(c["neighbors"], [])
        self.assertFalse(c["neighbors_truncated"])

    def test_ambiguous_cross_module_callee_excluded(self):
        # `shared` is defined in two OTHER modules (neither is run's module) → ambiguous cross-module →
        # DEF-3 resolution accounts for NOTHING; a neighbor must never point at a misresolved collider.
        src = {"app.py": "def run():\n    shared()\n    return 1\n",
               "b.py": "def shared():\n    return 2\n",
               "c.py": "def shared():\n    return 3\n"}
        with tempfile.TemporaryDirectory() as td:
            c = self._claim(_repo(Path(td), self.REC, src))
        self.assertEqual(c["neighbors"], [])
        self.assertFalse(any(n.endswith("::shared") for n in c["neighbors"]))

    def test_witness_claim_carries_no_neighbors(self):
        # a claim DISCHARGED via a passing verified-by witness never reaches the needs_judgment branch, so
        # it carries no evidence window (the witness is authoritative).
        src = {"app.py": "def run(x):\n    return guard(x)\ndef guard(x):\n    return x is not None\n"}
        md = self.REC.replace("- contract: run guards before it persists",
                              "- contract: run guards before it persists\n        - verified-by: python3 -c \"raise SystemExit(0)\"")
        with tempfile.TemporaryDirectory() as td:
            c = self._claim(_repo(Path(td), md, src), run_witnesses=True)
        self.assertEqual(c["state"], "DISCHARGED")
        self.assertNotIn("neighbors", c)


class TestRoundTrip(unittest.TestCase):
    """The strongest composition evidence: the emitted ledger parses through the UNMODIFIED scorer."""

    @_NEEDS_AA
    def test_emitted_ledger_parses_through_audit_accuracy(self):
        with tempfile.TemporaryDirectory() as td:
            repo = _repo(Path(td), GOOD_RECORD, {"export.py": SRC_EXPORT})
            result = tc.audit(repo, run_witnesses=False)
            # force one of each finding kind via judgments + a synthetic UNMET/orphan
            result["claims"].append({"id": "TELOS-099", "title": "rate limiting", "state": "UNMET",
                                     "needs_judgment": False, "facet": "telos-unmet", "target": "TELOS-099",
                                     "severity": "HIGH", "rationale": "never discharged",
                                     "contract": "", "intent": "", "discharged_by": "none"})
            result["candidates"].append({"target": "legacy.py::sync_v1", "facet": "telos-orphan",
                                         "severity": "LOW", "needs_judgment": True})
            judgments = {"TELOS-001": {"verdict": "DRIFTED", "rationale": "no longer redacts"},
                         "legacy.py::sync_v1": {"verdict": "orphan", "rationale": "serves no purpose"}}
            md = tc.emit_ledger(result, judgments, "2026-06-15")
            ledger = Path(td) / "docs" / "audits" / "demo-telos-2026-06-15.md"
            ledger.parent.mkdir(parents=True, exist_ok=True)
            ledger.write_text(md, encoding="utf-8")

            records = aa.parse_ledger(ledger)
            facets = {r["facet"] for r in records}
            self.assertIn("telos-drift", facets)
            self.assertIn("telos-unmet", facets)
            self.assertIn("telos-orphan", facets)
            # the unmet row carries the claim-id in the target slot and still parses (severity read)
            unmet = [r for r in records if r["facet"] == "telos-unmet"]
            self.assertTrue(unmet and unmet[0]["severity"] == "HIGH")
            # repo scope strips only the trailing date → distinct `<repo>-telos` classifier
            self.assertEqual(aa.repo_of("demo-telos-2026-06-15"), "demo-telos")

    def test_incremental_cache_skips_unchanged_discharged(self):
        with tempfile.TemporaryDirectory() as td:
            repo = _repo(Path(td), GOOD_RECORD, {"export.py": SRC_EXPORT})
            result = tc.audit(repo, run_witnesses=False)
            self.assertTrue(result["claims"][0]["needs_judgment"])  # first run: LLM must judge
            # emit a ledger judging it DISCHARGED → its verdict table records hash+DISCHARGED
            md = tc.emit_ledger(result, {"TELOS-001": {"verdict": "DISCHARGED"}}, "2026-06-15")
            ledger = Path(td) / "prior.md"
            ledger.write_text(md, encoding="utf-8")
            prior = tc.parse_prior_verdicts(ledger)
            self.assertIn("TELOS-001", prior)
            # second run with the cache: unchanged source → skip judgment, carried forward DISCHARGED.
            # today pinned so the new judged-date staleness gate is deterministic (judged = 2026-06-15).
            result2 = tc.audit(repo, run_witnesses=False, prior=prior, today=date(2026, 6, 16))
            self.assertEqual(result2["claims"][0]["state"], "DISCHARGED")
            self.assertFalse(result2["claims"][0]["needs_judgment"])
            # but if the CLAIMED symbol's own source changes, the cache misses → the LLM must re-judge
            # (an edit elsewhere in the file must NOT bust it — the key is the symbol segment, not the file)
            (repo / "export.py").write_text(textwrap.dedent(
                SRC_EXPORT.replace("out.append(redact(r))", "out.append(r)  # drift! no redact")),
                encoding="utf-8")
            result3 = tc.audit(repo, run_witnesses=False, prior=prior, today=date(2026, 6, 16))
            self.assertTrue(result3["claims"][0]["needs_judgment"])

    def test_contract_edit_busts_cache(self):
        # DEF-4 regression: amending a claim's contract while the pointed code is byte-identical MUST miss the
        # incremental cache — otherwise --prior carries the old DISCHARGED forward and the LLM never judges
        # the new contract (a silent pass in the amend-fork's own path).
        with tempfile.TemporaryDirectory() as td:
            repo = _repo(Path(td), GOOD_RECORD, {"export.py": SRC_EXPORT})
            result = tc.audit(repo, run_witnesses=False)
            md = tc.emit_ledger(result, {"TELOS-001": {"verdict": "DISCHARGED"}}, "2026-06-15")
            prior_path = Path(td) / "prior.md"
            prior_path.write_text(md, encoding="utf-8")
            prior = tc.parse_prior_verdicts(prior_path)
            # control: unchanged record + cache → skip (carried DISCHARGED). today pinned for the judged gate.
            self.assertEqual(tc.audit(repo, run_witnesses=False, prior=prior,
                                      today=date(2026, 6, 16))["claims"][0]["state"], "DISCHARGED")
            # edit ONLY the contract (code untouched) → cache must MISS → LLM must re-judge
            app = repo / "docs" / "telos" / "app.md"
            app.write_text(app.read_text(encoding="utf-8").replace(
                "run() redacts every record before any write",
                "run() does the OPPOSITE and never redacts"), encoding="utf-8")
            result2 = tc.audit(repo, run_witnesses=False, prior=prior, today=date(2026, 6, 16))
        self.assertTrue(result2["claims"][0]["needs_judgment"])
        self.assertIsNone(result2["claims"][0]["state"])

    @_NEEDS_AA
    def test_empty_clean_section_not_counted_as_tn(self):
        # a run with nothing discharged must score 0 TN — the empty-section placeholder must not be a bullet
        with tempfile.TemporaryDirectory() as td:
            repo = _repo(Path(td), GOOD_RECORD, {"export.py": SRC_EXPORT})
            result = tc.audit(repo, run_witnesses=False)
            md = tc.emit_ledger(result, {"TELOS-001": {"verdict": "DRIFTED"}}, "2026-06-15")
            ledger = Path(td) / "demo-telos-2026-06-15.md"
            ledger.write_text(md, encoding="utf-8")
            recs = aa.parse_ledger(ledger)
        self.assertEqual(sum(1 for r in recs if r["class"] == "TN"), 0)

    @_NEEDS_AA
    def test_amended_disp_excluded_from_rates(self):
        # an AMENDED row maps to PENDING in the scorer (disp ∉ {TP,FP}) — excluded from rates
        with tempfile.TemporaryDirectory() as td:
            ledger = Path(td) / "demo-telos-2026-06-15.md"
            ledger.write_text(
                "## Open findings\n"
                "- [ ] **[MED]** export.py:1 — [telos-drift] drift → amend  (disp: AMENDED)\n",
                encoding="utf-8")
            recs = aa.parse_ledger(ledger)
        self.assertEqual(recs[0]["class"], "PENDING")


class TestRepoSlug(unittest.TestCase):
    """A relative repo arg ('.') must still yield the real directory name in the ledger header + filename —
    Path('.').name is '' and would render a blank `<repo>` slug. Surfaced by the live internal-toolkit dogfood."""

    def test_dot_repo_resolves_to_dir_name(self):
        import os
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td) / "myrepo"
            repo.mkdir()
            cwd = os.getcwd()
            try:
                os.chdir(repo)
                self.assertEqual(tc.repo_name(Path(".")), "myrepo")
                self.assertEqual(tc.ledger_filename(Path("."), "2026-06-15"),
                                 "myrepo-telos-2026-06-15.md")
            finally:
                os.chdir(cwd)
        # a normally-named path is unchanged (no resolve side effects)
        self.assertEqual(tc.repo_name(Path("/x/internal-toolkit")), "internal-toolkit")

    def test_dotdot_repo_resolves_to_dir_name(self):
        """Path('..').name is '..' (not empty), so the slug guard must catch it too — else the ledger
        renders a '..-telos-<date>.md' filename and a '..' header slug."""
        import os
        with tempfile.TemporaryDirectory() as td:
            sub = Path(td) / "myrepo" / "sub"
            sub.mkdir(parents=True)
            cwd = os.getcwd()
            try:
                os.chdir(sub)
                self.assertEqual(tc.repo_name(Path("..")), "myrepo")
                self.assertEqual(tc.ledger_filename(Path(".."), "2026-06-15"),
                                 "myrepo-telos-2026-06-15.md")
            finally:
                os.chdir(cwd)


class TestParserDemotion(unittest.TestCase):
    """Evidence-tier B2 (D3): the parser demotes an unbacked `state: DISCHARGED` (no verified-by witness) to
    SUSPECT in the parsed representation — read-time, no record mutation — so the record-as-read never
    overclaims. Witness-backed DISCHARGED is left alone; the demotion does not touch audit()'s recomputation."""

    def _parse(self, md, sources=None):
        with tempfile.TemporaryDirectory() as td:
            return tc.parse_record(_repo(Path(td), md, sources))

    def test_unbacked_discharged_demotes_to_suspect(self):
        rec = self._parse(GOOD_RECORD, {"export.py": SRC_EXPORT})  # DISCHARGED, no verified-by
        c = rec.claims[0]
        self.assertEqual(c.fields["state"], "SUSPECT")
        self.assertTrue(c.demoted_reason)

    def test_witness_backed_discharged_not_demoted(self):
        md = GOOD_RECORD.replace(
            "- anchor: none", "- verified-by: python3 -c \"raise SystemExit(0)\"\n    - anchor: none")
        c = self._parse(md, {"export.py": SRC_EXPORT}).claims[0]
        self.assertEqual(c.fields["state"], "DISCHARGED")  # an executable witness backs it → kept
        self.assertEqual(c.demoted_reason, "")

    def test_non_discharged_state_not_demoted(self):
        md = (GOOD_RECORD.replace("- state: DISCHARGED", "- state: UNMET")
              .replace("- discharged-by: export.py::run", "- discharged-by: none"))
        self.assertEqual(self._parse(md, {"export.py": SRC_EXPORT}).claims[0].fields["state"], "UNMET")

    def test_demotion_is_representation_only_audit_still_needs_judgment(self):
        # the audit ignores author state and recomputes; a witness-free resolving claim still routes to
        # needs_judgment (NOT a SUSPECT finding) — the demotion is purely the parsed representation.
        with tempfile.TemporaryDirectory() as td:
            r = tc.audit(_repo(Path(td), GOOD_RECORD, {"export.py": SRC_EXPORT}), run_witnesses=False)
        c = r["claims"][0]
        self.assertTrue(c["needs_judgment"])
        self.assertIsNone(c["state"])
        self.assertEqual(c["tier"], "unproven")


class TestEvidenceTier(unittest.TestCase):
    """Evidence-tier B1/B3/B4 (D1/D2): each claim carries an audit-computed `tier`; the cache carries a prior
    DISCHARGED forward only for a carry-eligible tier whose tool-written `judged` receipt (in the LEDGER, not
    the record) is fresh — re-keyed off `judged`, so a bumped `last-grilled` can't revive a stale judgment."""

    def _ledger(self, td, result, judgments, audit_date):
        md = tc.emit_ledger(result, judgments, audit_date)
        p = Path(td) / "ledger.md"
        p.write_text(md, encoding="utf-8")
        return md, p

    def test_witness_claim_tier_is_witness(self):
        md = GOOD_RECORD.replace(
            "- anchor: none", "- verified-by: python3 -c \"raise SystemExit(0)\"\n    - anchor: none")
        with tempfile.TemporaryDirectory() as td:
            r = tc.audit(_repo(Path(td), md, {"export.py": SRC_EXPORT}), run_witnesses=True)
        self.assertEqual(r["claims"][0]["state"], "DISCHARGED")
        self.assertEqual(r["claims"][0]["tier"], "witness")

    def test_needs_judgment_tier_is_unproven(self):
        with tempfile.TemporaryDirectory() as td:
            r = tc.audit(_repo(Path(td), GOOD_RECORD, {"export.py": SRC_EXPORT}), run_witnesses=False)
        self.assertEqual(r["claims"][0]["tier"], "unproven")

    def test_llm_discharged_earns_judged_tier_and_ledger_receipt(self):
        with tempfile.TemporaryDirectory() as td:
            repo = _repo(Path(td), GOOD_RECORD, {"export.py": SRC_EXPORT})
            result = tc.audit(repo, run_witnesses=False, today=date(2026, 6, 16))
            md, ledger = self._ledger(td, result, {"TELOS-001": {"verdict": "DISCHARGED"}}, "2026-06-16")
            self.assertIn("discharged [judged].", md)            # Clean section shows the tier
            prior = tc.parse_prior_verdicts(ledger)
        # the verdict table carries the tool-written judged date and the judged tier (in the LEDGER)
        self.assertEqual(prior["TELOS-001"],
                         (result["claims"][0]["source_hash"], "DISCHARGED", "judged", "2026-06-16"))

    def test_cache_carry_tier_is_cache_and_preserves_judged_date(self):
        with tempfile.TemporaryDirectory() as td:
            repo = _repo(Path(td), GOOD_RECORD, {"export.py": SRC_EXPORT})
            result = tc.audit(repo, run_witnesses=False, today=date(2026, 6, 16))
            _, ledger = self._ledger(td, result, {"TELOS-001": {"verdict": "DISCHARGED"}}, "2026-06-16")
            prior = tc.parse_prior_verdicts(ledger)
            r2 = tc.audit(repo, run_witnesses=False, prior=prior, today=date(2026, 6, 20))
        c = r2["claims"][0]
        self.assertEqual(c["state"], "DISCHARGED")
        self.assertEqual(c["tier"], "cache")
        self.assertEqual(c["judged"], "2026-06-16")  # preserved (NOT refreshed to today) so staleness ages it

    def test_bumped_last_grilled_cannot_revive_stale_judgment(self):
        # D2/B3: the cache-staleness gate keys on the tool-written `judged` date, not author-written
        # last-grilled. A judged receipt older than the threshold forces a re-judge even with a fresh
        # last-grilled and byte-identical source — closing the bump-the-date-to-revive hole.
        with tempfile.TemporaryDirectory() as td:
            repo = _repo(Path(td), GOOD_RECORD, {"export.py": SRC_EXPORT})
            result = tc.audit(repo, run_witnesses=False, today=date(2024, 1, 1))
            _, ledger = self._ledger(td, result, {"TELOS-001": {"verdict": "DISCHARGED"}}, "2024-01-01")
            prior = tc.parse_prior_verdicts(ledger)
            # control: a fresh judged date carries forward
            near = tc.audit(repo, run_witnesses=False, prior=prior, today=date(2024, 1, 2))
            self.assertEqual(near["claims"][0]["tier"], "cache")
            # judged receipt now ancient (last-grilled in the record is 2026-06-15, freshly "bumped") → re-judge
            far = tc.audit(repo, run_witnesses=False, prior=prior, today=date(2026, 6, 16))
        self.assertTrue(far["claims"][0]["needs_judgment"])
        self.assertEqual(far["claims"][0]["tier"], "unproven")

    def test_unproven_prior_does_not_carry(self):
        # B4: a PENDING/unproven prior (no LLM verdict last run) must re-judge, never carry.
        with tempfile.TemporaryDirectory() as td:
            repo = _repo(Path(td), GOOD_RECORD, {"export.py": SRC_EXPORT})
            result = tc.audit(repo, run_witnesses=False, today=date(2026, 6, 16))
            _, ledger = self._ledger(td, result, {}, "2026-06-16")  # no verdict → unproven row
            prior = tc.parse_prior_verdicts(ledger)
            r2 = tc.audit(repo, run_witnesses=False, prior=prior, today=date(2026, 6, 16))
        self.assertTrue(r2["claims"][0]["needs_judgment"])

    def test_legacy_3col_table_parses_but_does_not_carry(self):
        # back-compat: a pre-tier (3-column) ledger parses (hash+state) with empty tier, so the carry gate
        # fail-closes to a re-judge rather than crashing or carrying an un-tiered verdict.
        with tempfile.TemporaryDirectory() as td:
            repo = _repo(Path(td), GOOD_RECORD, {"export.py": SRC_EXPORT})
            h = tc.audit(repo, run_witnesses=False, today=date(2026, 6, 16))["claims"][0]["source_hash"]
            old = Path(td) / "old.md"
            old.write_text("## Per-claim verdict\n| claim | hash | state |\n|--|--|--|\n"
                           f"| TELOS-001 | {h} | DISCHARGED |\n", encoding="utf-8")
            prior = tc.parse_prior_verdicts(old)
            self.assertEqual(prior["TELOS-001"], (h, "DISCHARGED", "", ""))   # tier/judged empty
            r2 = tc.audit(repo, run_witnesses=False, prior=prior, today=date(2026, 6, 16))
        self.assertTrue(r2["claims"][0]["needs_judgment"])   # empty tier ∉ carry set → re-judge


if __name__ == "__main__":
    unittest.main(verbosity=2)
