#!/usr/bin/env python3
"""telos_check.py — the deterministic spine of the telos purpose-conformance audit.

Sibling of `audit-repo/audit_accuracy.py`. Stdlib only. Computes everything the conformance audit can
decide *mechanically*, leaving exactly two judgments to the LLM tier in `audit-telos/SKILL.md`:
DISCHARGED-vs-DRIFTED (for claims with no executable witness) and is-this-orphan-meaningful.

What it does:
  * **Strict parse** of the intent record `docs/telos/*.md` — the never-silent-pass guarantee. Inside a
    `### TELOS-NNN — <title>` block it accepts ONLY whitelisted `- key: value` lines + blanks and RAISES
    on anything else (the no-skip-branch invariant); a malformed block / absent / empty record ABORTS the
    audit (loud) rather than passing clean.
  * **Static-AST symbol resolution** of each `discharged-by: path::symbol` — never imports or executes the
    target (untrusted-repo safe).
  * **Significant surface · accounted-for · candidate orphans** (reverse set-diff): the deterministic
    pre-filter that hands the LLM only a small pre-screened candidate list.
  * **Anchor (content-hash) + staleness → SUSPECT**, **coverage %** (advisory), and **executable
    `verified-by:` witnesses** (run them; exit code is authoritative, trusted over the LLM).
  * **Evidence tier + honesty rules** — each claim carries an audit-computed `tier`
    (`witness`/`judged`/`cache`/`unproven`, never author-written → unforgeable); the incremental cache carries
    a prior DISCHARGED forward only for a witness/judged/cache tier whose tool-written `judged` receipt is
    fresh (staleness re-keyed off `judged`, not the bump-able author-written `last-grilled`); and the strict
    parser demotes an unbacked `state: DISCHARGED` (no `verified-by`) to SUSPECT so the record-as-read can
    never overclaim. The `judged` receipt lives in the ledger, never the record (the record stays
    `telos`-owned and audit-read-only).
  * **Ledger emission** in the exact `audit-repo` worklist format so rows parse through the UNMODIFIED
    `audit_accuracy.py` (facets `[telos-drift] [telos-unmet] [telos-orphan]`).

Usage:
  telos_check.py parse  <repo>                 # strict-parse the record; print claims JSON or ABORT
  telos_check.py audit  <repo> [--no-witnesses] # full deterministic pass → result JSON on stdout
  telos_check.py emit-ledger --result R.json [--judgments J.json] [--date YYYY-MM-DD]  # ledger markdown
  telos_check.py --self-test                   # run the bundled invariant checks
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import shlex
import subprocess
import sys
import textwrap
from dataclasses import dataclass, field, asdict
from datetime import date, datetime
from pathlib import Path

# ── record grammar ──────────────────────────────────────────────────────────────────────────────────
CLAIM_KEYS = {"state", "intent", "discharged-by", "contract", "verified-by", "source",
              "last-grilled", "anchor", "covers", "superseded-by"}
REQUIRED_KEYS = {"state", "intent", "discharged-by", "contract"}
STATES = {"DISCHARGED", "UNMET", "DRIFTED", "SUSPECT"}
UNMET_POINTERS = {"none", "todo", ""}            # discharged-by values that mean "not pointed yet"
STALE_DAYS_DEFAULT = 180                          # last-grilled / judged older than this → re-grill (tunable)
_ANCHOR_HEX_LEN = 16                              # content_hash width; an anchor must match it exactly
# Audit-computed evidence tiers (NEVER author-written → unforgeable). A claim's DISCHARGED is only as good as
# its tier: `witness` (verified-by passed, re-run every audit — the strongest), `judged` (an LLM DISCHARGED
# with a fresh tool-written `judged` receipt), `cache` (a prior witness/judged verdict carried forward on an
# unchanged fingerprint + fresh receipt), `unproven` (needs an LLM judgment). The cache carries a prior
# DISCHARGED forward only for these tiers — an `asserted` author-DISCHARGED with nothing behind it never does
# (and the strict parser demotes it to SUSPECT before it can reach the verdict table anyway).
_CARRY_TIERS = {"witness", "judged", "cache"}


class TelosError(Exception):
    """A loud failure: a malformed record, an unparseable claim, or an aborted audit. Never swallowed —
    the whole point of the strict parser is that a bad record stops the audit instead of passing clean."""


@dataclass
class Claim:
    id: str
    title: str
    fields: dict[str, str] = field(default_factory=dict)
    line: int = 0
    demoted_reason: str = ""   # set by the parser when an unbacked `state: DISCHARGED` is demoted to SUSPECT

    @property
    def discharged_by(self) -> str:
        return self.fields.get("discharged-by", "").strip()

    @property
    def is_pointed(self) -> bool:
        return self.discharged_by.lower() not in UNMET_POINTERS


@dataclass
class Record:
    motive: str
    telos: str
    claims: list[Claim]
    source_files: list[str]


# ── strict parser (the never-silent-pass guarantee) ─────────────────────────────────────────────────
_HEADER_PREFIX = "### "
_SECTION_PREFIX = "## "


def _strip_inline_comment(value: str) -> str:
    """Strip a trailing ` # comment` (whitespace immediately before the `#`). A `#` with no leading
    whitespace is part of the value (e.g. a `source: path#anchor` fragment) and is preserved (DEF-1)."""
    m = re.search(r"\s#", value)
    return value[:m.start()] if m else value


def _parse_claim_block(claim_id: str, title: str, body: list[tuple[int, str]]) -> Claim:
    """Parse one claim's `- key: value` lines. RAISES on any unrecognized line (no-skip-branch),
    duplicate key, or unknown key. Semantic validation of values happens in validate_record()."""
    fields: dict[str, str] = {}
    in_block_comment = False
    block_comment_start = 0  # lineno of the unterminated `<!--`, for the error message
    for lineno, raw in body:
        line = raw.rstrip()
        if in_block_comment:
            if "-->" in line:
                in_block_comment = False
            continue  # swallow continuation lines until the comment closes
        if not line.strip():
            continue
        stripped = line.strip()
        if stripped.startswith("<!--"):
            # a single-line `<!-- ... -->` is consumed here; a `<!--` with no closing `-->` on the same
            # line opens a multi-line block whose continuation lines are skipped until one carries `-->`.
            if "-->" not in stripped:
                in_block_comment, block_comment_start = True, lineno
            continue  # comment line inside a block is allowed (never carries a key)
        if stripped.startswith("#"):
            continue
        if not stripped.startswith("- "):
            raise TelosError(f"{claim_id}: line {lineno}: not a `- key: value` line: {line!r} "
                             f"(strict parser refuses to skip unrecognized lines)")
        kv = stripped[2:]
        if ":" not in kv:
            raise TelosError(f"{claim_id}: line {lineno}: missing ':' in claim field: {line!r}")
        key, _, value = kv.partition(":")
        key = key.strip()
        # strip a trailing ` # comment` (whitespace-then-hash) only; a '#' with no leading space is part of
        # the value — e.g. `source: CLAUDE.md#anchor` — and must survive (DEF-1). intent/contract are prose
        # and keep their full text untouched.
        value = value.strip() if key in ("intent", "contract") else _strip_inline_comment(value).strip()
        if key not in CLAIM_KEYS:
            raise TelosError(f"{claim_id}: line {lineno}: unknown claim key {key!r} "
                             f"(allowed: {sorted(CLAIM_KEYS)})")
        if key in fields:
            raise TelosError(f"{claim_id}: line {lineno}: duplicate key {key!r}")
        fields[key] = value
    if in_block_comment:
        # never-silent-pass: a `<!--` that the block ends without closing must NOT silently swallow the
        # rest of the claim — raise instead of letting unterminated markup hide fields.
        raise TelosError(f"{claim_id}: line {block_comment_start}: unterminated `<!--` block comment "
                         f"(strict parser refuses to silently swallow the rest of the block)")
    return Claim(id=claim_id, title=title.strip(), fields=fields)


def _validate_claim(c: Claim) -> None:
    missing = REQUIRED_KEYS - set(c.fields)
    if missing:
        raise TelosError(f"{c.id}: missing required field(s): {sorted(missing)}")
    state = c.fields["state"].strip().upper()
    if state not in STATES:
        raise TelosError(f"{c.id}: invalid state {c.fields['state']!r} (must be one of {sorted(STATES)})")
    db = c.discharged_by
    if c.is_pointed and "::" not in db:
        raise TelosError(f"{c.id}: discharged-by {db!r} is neither `none`/`TODO` nor a `path::symbol`")
    anchor = c.fields.get("anchor", "none").strip().lower()
    # `none`, or a non-empty hex string of exactly the content_hash width — an empty/short/long value can
    # never match content_hash() and would silently pin the claim to permanent SUSPECT.
    if anchor != "none" and not re.fullmatch(r"[0-9a-f]{%d}" % _ANCHOR_HEX_LEN, anchor):
        raise TelosError(f"{c.id}: anchor must be `none` or a {_ANCHOR_HEX_LEN}-char hex content-hash "
                         f"(from `telos`), got {c.fields['anchor']!r}")
    lg = c.fields.get("last-grilled", "").strip()
    if lg and not _parse_date(lg):
        raise TelosError(f"{c.id}: last-grilled {lg!r} is not an ISO date (YYYY-MM-DD)")
    sup = c.fields.get("superseded-by", "").strip()
    if sup and not _is_claim_id(sup):
        raise TelosError(f"{c.id}: superseded-by {sup!r} must be a TELOS-NNN id")


def _is_claim_id(s: str) -> bool:
    """A claim id is `TELOS-` followed by digits (the opaque, mint-once join key)."""
    return s.startswith("TELOS-") and s[6:].isdigit()


def parse_record(repo: Path) -> Record:
    """Strict-parse `docs/telos/*.md`. ABORTS (TelosError) on an absent/empty record or any malformed
    block — never returns a partial/clean result for a broken record."""
    telos_dir = repo / "docs" / "telos"
    if not telos_dir.is_dir():
        raise TelosError(f"no telos record: {telos_dir} does not exist (bootstrap with the `telos` skill)")
    files = sorted(telos_dir.glob("*.md"))
    if not files:
        raise TelosError(f"no telos record: {telos_dir} is empty")
    section_prose: dict[str, list[str]] = {"motive": [], "telos": []}
    claims: list[Claim] = []
    seen_ids: set[str] = set()
    for f in files:
        lines = f.read_text(encoding="utf-8", errors="replace").splitlines()
        section = ""
        cur_id: str | None = None
        cur_title = ""
        cur_body: list[tuple[int, str]] = []

        def flush():
            nonlocal cur_id, cur_title
            if cur_id is not None:
                c = _parse_claim_block(cur_id, cur_title, cur_body)
                _validate_claim(c)
                claims.append(c)
                cur_id, cur_body[:] = None, []

        for i, raw in enumerate(lines, 1):
            if raw.startswith(_HEADER_PREFIX):
                flush()
                header = raw[len(_HEADER_PREFIX):].strip()
                cid, _, title = header.partition("—")
                cid = cid.strip()
                if not _is_claim_id(cid):
                    raise TelosError(f"{f.name}: line {i}: claim header must be "
                                     f"`### TELOS-NNN — <title>`, got {raw.strip()!r}")
                if cid in seen_ids:
                    raise TelosError(f"{f.name}: line {i}: duplicate claim id {cid}")
                seen_ids.add(cid)
                cur_id, cur_title, cur_body = cid, title, []
                continue
            if raw.startswith(_SECTION_PREFIX) or raw.startswith("# "):
                flush()
                section = raw.lstrip("#").strip().lower()
                continue
            if cur_id is not None:
                cur_body.append((i, raw))
            elif section in section_prose:
                section_prose[section].append(raw)
        flush()
    # DEF-5: now that every id in the record is known, validate supersede targets. audit() skips any claim
    # carrying `superseded-by`, so a dangling (typo'd/nonexistent) or self-referential target would silently
    # retire a LIVE purpose claim with no error — make it fail loud at parse time instead.
    for c in claims:
        sup = c.fields.get("superseded-by", "").strip()
        if not sup:
            continue
        if sup == c.id:
            raise TelosError(f"{c.id}: superseded-by points at itself")
        if sup not in seen_ids:
            raise TelosError(f"{c.id}: superseded-by {sup} names no claim in the record "
                             f"(a dangling supersede would silently retire this live claim)")
    # evidence-tier B2 (read-time, no record mutation): the author-written `state` is honest only when backed.
    # A `state: DISCHARGED` with no executable `verified-by` witness is an assertion the record cannot prove on
    # its own — an LLM judgment lives in the audit ledger, never here — so demote it to SUSPECT in the PARSED
    # representation. Every consumer routed through the parser (`parse` CLI, `audit()`, any importer) then reads
    # the honest state, not a free DISCHARGED. This strengthens never-silent-pass; it does not weaken it, and it
    # touches only the in-memory Claim (the file on disk is owned by the `telos` skill and left untouched).
    for c in claims:
        if c.fields.get("superseded-by", "").strip():
            continue
        if c.fields["state"].strip().upper() != "DISCHARGED":
            continue
        if c.fields.get("verified-by", "").strip():
            continue  # an executable witness is the only in-record, un-fakeable backing for DISCHARGED
        c.fields["state"] = "SUSPECT"
        c.demoted_reason = ("unbacked DISCHARGED demoted to SUSPECT: no verified-by witness backs it "
                            "(an LLM DISCHARGED is recorded in the audit ledger, not the record)")
    motive = "\n".join(section_prose["motive"]).strip()
    telos = "\n".join(section_prose["telos"]).strip()
    if not claims:
        raise TelosError("telos record has a motive/telos but zero claims — nothing to audit "
                         "(add claims or treat as a bootstrap candidate)")
    return Record(motive=motive, telos=telos, claims=claims,
                  source_files=[str(f.relative_to(repo)) for f in files])


def _parse_date(s: str) -> date | None:
    try:
        return datetime.strptime(s.strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


# ── static-AST resolver (never imports/executes the target) ──────────────────────────────────────────
SKIP_DIRS = {".git", ".venv", "venv", "env", "__pycache__", "node_modules", "build", "dist",
             "site-packages", ".tox", ".mypy_cache", ".pytest_cache", "vendor", "third_party",
             "migrations", ".eggs", "_vendor", "tmp"}


def _is_first_party(rel: Path) -> bool:
    parts = set(rel.parts)
    if parts & SKIP_DIRS:
        return False
    name = rel.name
    if not name.endswith(".py"):
        return False
    if name.startswith("test_") or name.endswith("_test.py") or name == "conftest.py":
        return False
    if "tests" in rel.parts or "test" in rel.parts:
        return False
    if name.endswith(("_pb2.py", "_pb2_grpc.py")):
        return False
    return True


def _iter_py(repo: Path):
    for p in repo.rglob("*.py"):
        if _is_first_party(p.relative_to(repo)):
            yield p


def _find_symbol_node(tree: ast.AST, symbol: str) -> ast.AST | None:
    """Find a top-level `func`/`Class` or `Class.method` node by qualname (no execution)."""
    parts = symbol.split(".")
    container = tree
    for depth, part in enumerate(parts):
        found = None
        for node in ast.iter_child_nodes(container):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name == part:
                found = node
                break
        if found is None:
            return None
        container = found
    return container


def resolve_pointer(repo: Path, pointer: str) -> tuple[bool, ast.AST | None, str | None]:
    """Resolve `path::symbol` statically. Returns (exists, node, source_segment). Never imports/runs."""
    path_str, _, symbol = pointer.partition("::")
    # Confine resolution to the repo: an absolute `path_str` makes `repo / path_str` discard `repo`
    # (pathlib), and `..` components walk out of the tree — a crafted `discharged-by: /etc/shadow::x`
    # or `../../secret.py::y` would turn this into a file-exists / valid-Python oracle outside the repo.
    # The resolver never executes, so the impact is only that oracle, but it still breaches the stated
    # "untrusted-repo safe, repo-confined" boundary — reject anything that escapes.
    if Path(path_str).is_absolute() or ".." in Path(path_str).parts:
        return False, None, None
    f = repo / path_str
    try:
        if not f.resolve().is_relative_to(repo.resolve()):
            return False, None, None  # symlink or normalization that lands outside the repo
    except (OSError, ValueError, RuntimeError):
        return False, None, None
    if not f.is_file():
        return False, None, None
    try:
        src = f.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(src, filename=str(f))
    except (OSError, SyntaxError, ValueError):
        # ValueError: ast.parse raises it (not SyntaxError) on a source with an embedded NUL byte —
        # a valid Unicode char that errors="replace" does not strip. Catch it so one such file in an
        # untrusted repo is skipped (not-found) rather than aborting the whole audit (untrusted-repo safe).
        return False, None, None
    node = _find_symbol_node(tree, symbol)
    if node is None:
        return False, None, None
    return True, node, ast.get_source_segment(src, node)


# ── significant surface · call edges · accounted-for · candidate orphans ──────────────────────────────
def _is_trivial(node: ast.AST) -> bool:
    """Drop sub-threshold one-liners and pure-dataclass value carriers from significant surface
    (spike refinement: these leaked as low-signal orphan candidates)."""
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        body = [s for s in node.body
                if not (isinstance(s, ast.Expr) and isinstance(getattr(s, "value", None), ast.Constant))]
        return len(body) <= 1
    if isinstance(node, ast.ClassDef):
        has_logic = any(isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef)) and not s.name.startswith("__")
                        for s in node.body)
        return not has_logic  # a class with no public methods is a value carrier
    return False


def build_graph(repo: Path):
    """Return (significant_surface set, call edges dict, all_defs set, bare_index, module set,
    class_methods dict mapping class qualname -> its method qualnames)."""
    significant: set[str] = set()
    all_defs: set[str] = set()
    bare_index: dict[str, set[str]] = {}
    calls: dict[str, list[str]] = {}      # owner qualname -> callee bare names
    modules: set[str] = set()
    class_methods: dict[str, set[str]] = {}   # class qualname -> its method qualnames (for containment)

    def add_def(q):
        all_defs.add(q)
        bare = q.split("::")[1].split(".")[-1]
        bare_index.setdefault(bare, set()).add(q)

    for p in _iter_py(repo):
        rel = p.relative_to(repo)
        mod = str(rel)
        modules.add(mod)
        try:
            tree = ast.parse(p.read_text(encoding="utf-8", errors="replace"), filename=str(p))
        except (SyntaxError, ValueError):
            continue  # ValueError: embedded NUL byte in the source — skip the file, don't abort the audit
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                q = f"{mod}::{node.name}"
                add_def(q)
                calls[q] = _callee_names(node)
                if not node.name.startswith("_") and not _is_trivial(node):
                    significant.add(q)
            elif isinstance(node, ast.ClassDef):
                cq = f"{mod}::{node.name}"
                add_def(cq)
                class_methods[cq] = set()
                if not node.name.startswith("_") and not _is_trivial(node):
                    significant.add(cq)
                for m in node.body:
                    if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        mq = f"{mod}::{node.name}.{m.name}"
                        add_def(mq)
                        calls[mq] = _callee_names(m)
                        class_methods[cq].add(mq)
                        if (not node.name.startswith("_") and not m.name.startswith("_")
                                and not _is_trivial(m)):
                            significant.add(mq)
    # resolve call edges by bare callee name (best-effort; no real scope/import resolution). A bare name can
    # match several defs across the repo. Linking ALL of them INFLATES accounted-for and can SILENTLY HIDE a
    # real orphan whose name merely collides with a reached symbol (DEF-3) — accounted-for grows, candidates
    # shrink, the orphan is swallowed. So resolve toward over-surfacing, never hiding: prefer a same-module
    # def (the overwhelmingly common true call); else link a repo-unique match; else an ambiguous
    # cross-module name accounts for NOTHING — leave every collider in the candidate set for the LLM. (Over-
    # flagging a reached symbol as a candidate is recoverable; hiding a genuine orphan is not.)
    edges: dict[str, set[str]] = {}
    for owner, names in calls.items():
        owner_mod = owner.split("::", 1)[0]
        tgt: set[str] = set()
        for n in names:
            cands = bare_index.get(n, set())
            if not cands:
                continue
            same_mod = {q for q in cands if q.split("::", 1)[0] == owner_mod}
            if same_mod:
                tgt |= same_mod   # RESIDUAL (known): if a same-module leaf name is itself ambiguous — e.g. a
                                  # dead free `helper` and a reached method `C.helper` — BOTH link and the dead
                                  # one is still over-accounted (hidden). Narrow (same module, same leaf, one
                                  # dead/one reached) and left as-is: disambiguating bare Name- vs Attribute-
                                  # calls would trade this rare hidden-orphan for frequent over-surfacing of
                                  # genuinely-reached `self.method()` calls. Documented in the design doc.
            elif len(cands) == 1:
                tgt |= cands
            # else: ambiguous cross-module bare name → non-accounting (surface the colliders, don't hide)
        edges[owner] = tgt
    return significant, edges, all_defs, bare_index, modules, class_methods


def _callee_names(fn: ast.AST) -> list[str]:
    out: list[str] = []
    for n in ast.walk(fn):
        if isinstance(n, ast.Call):
            f = n.func
            if isinstance(f, ast.Name):
                out.append(f.id)
            elif isinstance(f, ast.Attribute):
                out.append(f.attr)
    return out


def reconcile_containment(raw_accounted: set[str], significant: set[str],
                          class_methods: dict[str, set[str]]) -> set[str]:
    """Account-for the class↔method containment the call graph can't express, returning the accounted-for
    SIGNIFICANT units.

    `raw_accounted` is the full call-closure (NOT yet filtered to significant) — so a claimed method that
    is itself a trivial one-liner (and thus not in `significant`) still un-orphans its class. A claim on a
    method (`mod::Cls.method`) discharges that method, but the *class* node `mod::Cls` is a distinct
    significant unit with no call edge to/from its methods — without this it is a false orphan. Two
    directions, both tested against the immutable `raw_accounted` so sibling methods don't leak coverage:
      * a claimed/accounted class covers all its own methods;
      * an accounted method un-orphans its enclosing class (NOT its siblings).
    """
    out = raw_accounted & significant
    for cls, methods in class_methods.items():
        if cls in raw_accounted:              # whole class claimed → covers its methods
            out |= methods & significant
        if raw_accounted & methods and cls in significant:  # a method claimed → class not an orphan
            out.add(cls)                                    # (siblings untouched)
    return out


def bootstrap_surface(repo: Path) -> dict:
    """Enumerate the significant surface of a CLAIMLESS repo (no record required) — the bootstrap entry
    point. `audit()` aborts before reaching the orphan pass when there is no record, so this is the
    separate, record-free path the `telos` skill uses to propose a first batch of claims."""
    significant, _, _, _, modules, _ = build_graph(repo)
    return {"repo": str(repo), "python_repo": bool(modules),
            "significant_surface": sorted(significant), "count": len(significant)}


def closure(seeds: set[str], edges: dict[str, set[str]]) -> set[str]:
    seen, stack = set(seeds), list(seeds)
    while stack:
        for nxt in edges.get(stack.pop(), ()):
            if nxt not in seen:
                seen.add(nxt)
                stack.append(nxt)
    return seen


NEIGHBOR_CAP = 12  # max 1-hop callees handed to the DRIFTED judge as evidence; a claim with more direct
                   # callees than this is the signal to pin it with a verified-by witness, not to flood the
                   # judgment window — so the surplus is dropped and the truncation flagged.


def claim_neighbors(owner_qualname: str, edges: dict[str, set[str]]) -> tuple[list[str], bool]:
    """The 1-hop resolved callees of a claimed symbol, as `path::symbol` pointers, capped at NEIGHBOR_CAP.

    Widens the DISCHARGED-vs-DRIFTED judge's evidence window past the single discharged-by symbol so a
    purpose-bearing distinction pushed into a callee is visible (the claimed symbol can be locally correct
    while a delegate erased the guarantee). Reuses build_graph's DEF-3-safe edges (same-module-preferring,
    else repo-unique, else ambiguous-cross-module dropped) — so a neighbor never points at a misresolved
    collider. 1-hop only: deeper drift stays the witness's job. Returns (neighbors, truncated)."""
    callees = sorted(edges.get(owner_qualname, set()))
    return callees[:NEIGHBOR_CAP], len(callees) > NEIGHBOR_CAP


def pointer_qualname(repo: Path, pointer: str) -> str:
    """Map a `path::symbol` pointer to the qualname shape build_graph() uses (`relpath::symbol`)."""
    path_str, _, symbol = pointer.partition("::")
    return f"{path_str}::{symbol}"


# ── anchor + staleness ────────────────────────────────────────────────────────────────────────────────
def content_hash(source_segment: str | None) -> str:
    if source_segment is None:
        return ""
    return hashlib.sha256(source_segment.encode("utf-8")).hexdigest()[:_ANCHOR_HEX_LEN]


def claim_fingerprint(source_segment: str | None, contract: str, intent: str,
                      verified_by: str = "") -> str:
    """The incremental-cache key for `--prior`: the discharged-by symbol's source PLUS the claim's
    contract+intent+verified-by. Folding the prose in is load-bearing — a claim can be AMENDED (its
    contract re-grilled) while the pointed code stays byte-identical; keying on the code alone would carry
    the old DISCHARGED forward and the LLM would never judge the NEW contract against the unchanged code — a
    silent pass in the amend-fork's own path. Folding in `verified-by` closes the witness-removal hole:
    deleting the executable witness (leaving code/contract/intent identical) must BUST the cache, or a
    now-unbacked DISCHARGED would carry forward forever as tier=cache without the witness ever re-running.
    Changing the contract OR the intent OR the code OR the witness now busts the cache."""
    h = hashlib.sha256()
    h.update((source_segment or "").encode("utf-8"))
    h.update(b"\x00"); h.update(contract.encode("utf-8"))
    h.update(b"\x00"); h.update(intent.encode("utf-8"))
    h.update(b"\x00"); h.update(verified_by.encode("utf-8"))
    return h.hexdigest()[:_ANCHOR_HEX_LEN]


def is_stale(last_grilled: str, today: date, threshold_days: int = STALE_DAYS_DEFAULT) -> bool:
    d = _parse_date(last_grilled)
    if d is None:
        return False  # absent timestamp is handled as its own signal, not staleness
    return (today - d).days > threshold_days


# ── executable witnesses (verified-by) ──────────────────────────────────────────────────────────────
def _witness_is_pytest_nodeid(spec: str) -> bool:
    """True iff `spec` is a bare pytest node id (`path.py::...`) to run via `-m pytest`. The path segment
    before the first `::` must be a `.py` file with no internal whitespace; a parametrized id's `[param]`
    MAY contain spaces (DEF-2 — the old `" " not in spec` guard misrouted those to the shell-command branch,
    where the witness failed to run and forced a silent false DRIFTED)."""
    if "::" not in spec:
        return False
    head = spec.split("::", 1)[0]
    return head.endswith(".py") and " " not in head


def run_witness(repo: Path, verified_by: str) -> tuple[bool, str]:
    """Run a `verified-by:` witness. Exit 0 == pass; non-zero == fail (authoritative, trusted over LLM).

    A `path.py::node` form is run as a pytest node id; anything else is run as a command line (no shell).
    This DOES execute target code — it is the author's explicit opt-in, distinct from the resolver, which
    never executes anything."""
    spec = verified_by.strip()
    if _witness_is_pytest_nodeid(spec):
        argv = [sys.executable, "-m", "pytest", "-q", spec]
    else:
        # shlex.split raises ValueError on an unbalanced quote; a malformed witness from an (untrusted) repo
        # must FAIL the witness (→ DRIFTED), never crash the whole audit. Fail closed, like a non-zero exit.
        try:
            argv = shlex.split(spec)
        except ValueError as e:
            return False, f"witness spec is not parseable: {e}"
    if not argv:
        return False, "witness spec is empty"
    try:
        proc = subprocess.run(argv, cwd=repo, capture_output=True, text=True, timeout=300)
    except (OSError, subprocess.TimeoutExpired) as e:
        return False, f"witness did not run: {e}"
    tail = (proc.stdout + proc.stderr).strip().splitlines()[-1:] or [""]
    return proc.returncode == 0, tail[0]


# ── deterministic state computation ──────────────────────────────────────────────────────────────────
def audit(repo: Path, run_witnesses: bool = True, today: date | None = None,
          prior: dict[str, tuple[str, str, str, str]] | None = None) -> dict:
    """Full deterministic pass. Returns a JSON-able result the LLM tier consumes and emit-ledger renders.

    `prior` is the incremental cache from a previous ledger ({claim-id: (source_hash, state, tier, judged)}):
    a claim that resolved, is not SUSPECT, has no witness, was DISCHARGED last run with a carry-eligible tier
    (witness/judged/cache), whose discharged-by fingerprint is byte-identical, AND whose tool-written `judged`
    receipt is not stale, skips the LLM judgment (carried forward DISCHARGED, tier `cache`). Re-keying the
    cache-staleness gate on the tool-written `judged` date — not the author-written `last-grilled`, which a
    human can bump without re-grilling — closes the bump-the-date-to-revive-a-stale-judgment hole."""
    today = today or date.today()
    prior = prior or {}
    record = parse_record(repo)              # ABORTS loudly on a bad/absent record
    significant, edges, _, _, modules, class_methods = build_graph(repo)
    python_repo = bool(modules)

    accounted_seed: set[str] = set()
    claim_results: list[dict] = []
    for c in record.claims:
        if c.fields.get("superseded-by", "").strip():
            continue  # retired claim — preserved for history (git + the record), not audited
        res = {"id": c.id, "title": c.title, "contract": c.fields.get("contract", ""),
               "intent": c.fields.get("intent", ""), "discharged_by": c.discharged_by,
               "state": None, "needs_judgment": False, "rationale": "", "facet": None,
               "target": c.discharged_by or c.id, "severity": "MED", "tier": None, "judged": ""}
        if not c.is_pointed:
            res.update(state="UNMET", facet="telos-unmet", target=c.id, severity="HIGH",
                       rationale="pointer is none/TODO/unset")
            claim_results.append(res)
            continue
        exists, node, segment = resolve_pointer(repo, c.discharged_by)
        if not exists:
            res.update(state="UNMET", facet="telos-unmet", target=c.id, severity="HIGH",
                       rationale=f"symbol {c.discharged_by} not found (renamed/deleted) — fails loud")
            claim_results.append(res)
            continue
        accounted_seed.add(pointer_qualname(repo, c.discharged_by))
        res["source_hash"] = claim_fingerprint(segment, c.fields.get("contract", ""),
                                                c.fields.get("intent", ""),
                                                c.fields.get("verified-by", ""))  # ledger cache key for --prior
        # anchor / staleness → SUSPECT (mechanical; never auto-DRIFTED)
        anchor = c.fields.get("anchor", "none").strip().lower()
        suspect_reasons = []
        if anchor != "none" and content_hash(segment) != anchor:
            suspect_reasons.append("anchor content-hash mismatch — re-judge")
        if is_stale(c.fields.get("last-grilled", ""), today):
            suspect_reasons.append("last-grilled stale past threshold — re-grill")
        # executable witness, if present, is authoritative
        witness = c.fields.get("verified-by", "").strip()
        if witness and run_witnesses:
            ok, detail = run_witness(repo, witness)
            if not ok:
                res.update(state="DRIFTED", facet="telos-drift", severity="MED",
                           rationale=f"verified-by witness failed: {detail}")
                claim_results.append(res)
                continue
            res["rationale"] = f"verified-by witness passed ({detail})"
            res.update(state="DISCHARGED", tier="witness")
            if suspect_reasons:
                res.update(state="SUSPECT", tier=None, facet="telos-drift",
                           rationale="; ".join(suspect_reasons))
            claim_results.append(res)
            continue
        if suspect_reasons:
            res.update(state="SUSPECT", facet="telos-drift", rationale="; ".join(suspect_reasons))
            claim_results.append(res)
            continue
        # resolves, no witness, not suspect → tier-gated + judged-keyed incremental cache, else the LLM call.
        # B4: carry a prior DISCHARGED forward ONLY for a carry-eligible tier on a byte-identical fingerprint
        # whose tool-written `judged` receipt is fresh — never an unbacked `asserted`, never a stale judgment.
        pr = prior.get(c.id)
        if (pr and pr[0] == res["source_hash"] and pr[1] == "DISCHARGED"
                and pr[2] in _CARRY_TIERS and pr[3] and not is_stale(pr[3], today)):
            # `pr[3]` (a non-empty tool-written `judged` date) is REQUIRED: a `witness`-tier prior emits an
            # empty judged (`is_stale("")` is False, which would otherwise read as "fresh") — so without this
            # a claim whose witness was removed would carry forward forever as tier=cache, never re-run. A
            # real judged/cache verdict always carries a date; a witness prior with no receipt re-judges.
            res.update(state="DISCHARGED", tier="cache", judged=pr[3],
                       rationale=f"unchanged since prior DISCHARGED (fresh {pr[2]} receipt"
                                 f"{' ' + pr[3] if pr[3] else ''}; incremental skip)")
        else:
            neighbors, truncated = claim_neighbors(pointer_qualname(repo, c.discharged_by), edges)
            res.update(needs_judgment=True, tier="unproven", facet="telos-drift",
                       neighbors=neighbors, neighbors_truncated=truncated,
                       rationale="pointer resolves; LLM must judge contract fulfillment (DISCHARGED vs "
                                 "DRIFTED) over the discharged-by symbol AND its 1-hop callees (neighbors)")
        claim_results.append(res)

    # accounted-for = closure of discharged-by symbols over call edges, then class↔method containment
    # reconciliation; candidate orphans = significant surface − accounted-for.
    if python_repo:
        raw_accounted = closure(accounted_seed, edges)   # full closure; filtered + reconciled below
        accounted = reconcile_containment(raw_accounted, significant, class_methods)
    else:
        accounted = set()
    candidates = sorted(significant - accounted) if python_repo else []
    coverage = (len(accounted) / len(significant)) if significant else None

    return {
        "repo": str(repo), "python_repo": python_repo,
        "motive": record.motive, "telos": record.telos, "source_files": record.source_files,
        "claims": claim_results,
        "candidates": [{"target": q, "facet": "telos-orphan", "severity": "LOW",
                        "needs_judgment": True} for q in candidates],
        "significant_surface": len(significant), "accounted_for": len(accounted),
        "coverage": coverage,
        "coverage_note": ("orphan/coverage skipped — non-Python repo (degraded grep mode)"
                          if not python_repo else None),
    }


# ── ledger emission (rows parse through the UNMODIFIED audit_accuracy.py) ─────────────────────────────
_FACET_FIX = {
    "telos-unmet": "implement or retire the claim",
    "telos-drift": "restore the behavior or amend the claim",
    "telos-orphan": "claim it or remove it",
}


def _row(severity: str, target: str, facet: str, problem: str, disp: str = "pending") -> str:
    fix = _FACET_FIX.get(facet, "resolve")
    return f"- [ ] **[{severity}]** {target} — [{facet}] {problem} → {fix}  (disp: {disp})"


def emit_ledger(result: dict, judgments: dict | None, audit_date: str) -> str:
    """Render the result + LLM judgments into the audit-repo worklist ledger format.

    `judgments` maps claim-id / candidate-target → {"verdict": DISCHARGED|DRIFTED|orphan|plumbing|claim,
    "rationale": str}. Anything left unjudged is emitted as `(disp: pending)` so the accuracy store
    excludes it from the rates (never a silent clean pass)."""
    judgments = judgments or {}
    repo = repo_name(Path(result["repo"]))
    rows: list[str] = []
    # (claim-id, source_hash, final state, evidence tier, tool-written judged date) for next run's --prior
    verdict_table: list[tuple[str, str, str, str, str]] = []
    discharged: list[tuple[dict, "str | None"]] = []
    for c in result["claims"]:
        state = c["state"]
        rationale = c["rationale"]
        tier = c.get("tier")
        judged = c.get("judged", "")
        if c["needs_judgment"]:
            verdict = judgments.get(c["id"], {}).get("verdict")
            if verdict == "DISCHARGED":
                # a fresh LLM DISCHARGED earns the `judged` tier and a tool-written receipt dated this run; the
                # receipt — not the author-written last-grilled — is what the next run's staleness gate keys on.
                state, tier, judged = "DISCHARGED", "judged", audit_date
                rationale = judgments.get(c["id"], {}).get("rationale", rationale)
            elif verdict == "DRIFTED":
                state, tier = "DRIFTED", None
                rationale = judgments.get(c["id"], {}).get("rationale", rationale)
            else:
                rows.append(_row("MED", c["id"], "telos-drift",
                                 f'"{c["title"]}" needs DISCHARGED/DRIFTED judgment'))
                verdict_table.append((c["id"], c.get("source_hash", ""), "PENDING", "unproven", ""))
                continue
        verdict_table.append((c["id"], c.get("source_hash", ""), state or "PENDING", tier or "-", judged or ""))
        if state == "DISCHARGED":
            discharged.append((c, tier))
        elif state == "UNMET":
            rows.append(_row(c["severity"], c["target"], "telos-unmet",
                             f'"{c["title"]}" {rationale}'))
        elif state == "DRIFTED":
            rows.append(_row(c["severity"], c["target"], "telos-drift",
                             f'{c["target"]} {rationale} per {c["id"]}'))
        elif state == "SUSPECT":
            rows.append(_row(c["severity"], c["id"], "telos-drift",
                             f'"{c["title"]}" SUSPECT: {rationale}'))

    orphan_rows: list[str] = []
    for cand in result["candidates"]:
        j = judgments.get(cand["target"], {})
        verdict = j.get("verdict")
        if verdict in ("plumbing", "claim"):
            continue  # dropped (legit plumbing) or routed to `telos` as a proposed claim — not a finding
        if verdict == "orphan":
            orphan_rows.append(_row("LOW", cand["target"], "telos-orphan",
                                    j.get("rationale", "serves no stated purpose")))
        else:
            orphan_rows.append(_row("LOW", cand["target"], "telos-orphan",
                                    "candidate — needs orphan-meaningfulness judgment"))

    cov = result["coverage"]
    cov_str = f"{cov*100:.0f}%" if cov is not None else "n/a (non-Python)"
    low_cov = cov is not None and cov < 0.5 and result["significant_surface"] >= 20
    verdict = ("SUSPECT (whole record): coverage implausibly low — under-claiming likely"
               if low_cov else f"{len(rows)+len(orphan_rows)} telos finding(s)")

    L = [f"# audit-telos — {repo} — {audit_date}", "",
         f"**Verdict:** {verdict}  ·  **Coverage:** {cov_str} "
         f"({result['accounted_for']}/{result['significant_surface']} significant surface accounted-for) "
         f"·  **Claims:** {len(result['claims'])}  ·  "
         f"**Telos:** {textwrap.shorten(result['telos'], width=80, placeholder=' …')}", ""]
    if low_cov:
        L += ["> ⚠ Coverage is advisory in v1, but this is low enough to refuse a clean verdict: the record "
              "likely under-claims (a Goodhart trap). Add claims for the unclaimed significant surface.", ""]
    # NB: placeholders for empty sections must NOT be bullets — a bullet under `## Clean` would be
    # miscounted as a target-level TN by audit_accuracy.py (it credits every bullet in that section).
    L += ["## Open findings — worklist (ranked; work top-down, one isolated change each)",
          "<!-- each item ends with (disp: pending); triage flips it to (disp: TP)/(disp: FP)/(disp: AMENDED) -->"]
    L += rows or ["_no claim drift/unmet findings_"]
    L += ["", "## Orphans (code with no stated purpose)"]
    L += orphan_rows or ["_no candidate orphans_"]
    L += ["", "## Clean (credited)  — each discharged claim is a target-level TN (a clean bill)"]
    L += [f"- {c['id']} — {c['title']}: discharged [{tier or '?'}]." for c, tier in discharged] or \
         ["_none discharged this run_"]
    L += ["", "## Per-claim verdict  (hash = claim fingerprint: symbol source + contract + intent; "
          "tier = audit-computed evidence tier; judged = tool-written LLM-verdict date — all for --prior)",
          "| claim | hash | state | tier | judged |", "|-------|------|-------|------|--------|"]
    L += [f"| {cid} | {h or '-'} | {st} | {ti or '-'} | {jd or '-'} |"
          for cid, h, st, ti, jd in verdict_table]
    L += ["", "## False negatives (misses — fill when a re-audit/human/incident finds a missed drift)", ""]
    return "\n".join(L) + "\n"


_VERDICT_ROW_RE = re.compile(
    r"^\|\s*(TELOS-\d+)\s*\|\s*([0-9a-f-]+)\s*\|\s*([A-Z]+)\s*\|"   # id | hash | state
    r"(?:\s*([a-z?-]*)\s*\|\s*([0-9-]*)\s*\|)?")                    # optional: tier | judged (back-compat)


def parse_prior_verdicts(ledger: Path) -> dict[str, tuple[str, str, str, str]]:
    """Read a prior ledger's `## Per-claim verdict` table → {claim-id: (source_hash, state, tier, judged)} for
    the incremental cache. Tolerant: a missing/garbled table just yields an empty cache (no skip, never crash);
    a pre-tier (3-column) ledger parses with tier/judged empty, so the carry gate fail-closes to a re-judge
    rather than carrying an un-tiered verdict forward."""
    out: dict[str, tuple[str, str, str, str]] = {}
    if not ledger.is_file():
        return out
    for line in ledger.read_text(encoding="utf-8", errors="replace").splitlines():
        m = _VERDICT_ROW_RE.match(line)
        if m:
            tier = (m.group(4) or "").strip()
            tier = "" if tier in ("-", "?") else tier
            judged = (m.group(5) or "").strip()
            judged = "" if judged == "-" else judged
            out[m.group(1)] = (m.group(2), m.group(3), tier, judged)
    return out


_DATE_SUFFIX = "-telos"


def repo_name(repo: Path) -> str:
    # A relative repo arg has a degenerate .name that would render a blank/garbage slug in the ledger
    # header and filename: "." -> "" and ".." -> ".." (both via pathlib). For those, resolve to the
    # real directory name instead; a normally-named path keeps its name (no resolve side effects).
    name = repo.name
    return name if name not in ("", "..") else repo.resolve().name


def ledger_filename(repo: Path, audit_date: str) -> str:
    """`docs/audits/<repo>-telos-<date>.md` → scores under repo-scope `<repo>-telos` (distinct classifier)."""
    return f"{repo_name(repo)}{_DATE_SUFFIX}-{audit_date}.md"


# ── CLI ───────────────────────────────────────────────────────────────────────────────────────────────
def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Deterministic spine of the telos conformance audit.")
    sub = ap.add_subparsers(dest="cmd")

    p_parse = sub.add_parser("parse", help="strict-parse docs/telos/*.md; print claims JSON or ABORT")
    p_parse.add_argument("repo")

    p_audit = sub.add_parser("audit", help="full deterministic pass → result JSON on stdout")
    p_audit.add_argument("repo")
    p_audit.add_argument("--no-witnesses", action="store_true",
                         help="do NOT run verified-by witnesses (use against untrusted repos)")
    p_audit.add_argument("--prior", help="a previous ledger to use as the incremental cache "
                                         "(carry forward unchanged DISCHARGED claims, skipping LLM judgment)")
    p_audit.add_argument("--date", help="audit date YYYY-MM-DD (default: today)")

    p_boot = sub.add_parser("bootstrap", help="list a claimless repo's significant surface (no record "
                                              "required) → proposed-claim candidates JSON")
    p_boot.add_argument("repo")

    p_emit = sub.add_parser("emit-ledger", help="render result(+judgments) JSON into a ledger")
    p_emit.add_argument("--result", required=True)
    p_emit.add_argument("--judgments")
    p_emit.add_argument("--date", default=date.today().isoformat())

    ap.add_argument("--self-test", action="store_true", help="run bundled invariant checks and exit")
    args = ap.parse_args(argv)

    if args.self_test:
        return _self_test()

    if args.cmd == "parse":
        try:
            rec = parse_record(Path(args.repo).expanduser())
        except TelosError as e:
            print(f"ABORT: {e}", file=sys.stderr)
            return 2
        print(json.dumps({"motive": rec.motive, "telos": rec.telos,
                          "claims": [asdict(c) for c in rec.claims]}, indent=2))
        return 0

    if args.cmd == "audit":
        prior = parse_prior_verdicts(Path(args.prior).expanduser()) if args.prior else None
        try:
            result = audit(Path(args.repo).expanduser(), run_witnesses=not args.no_witnesses,
                           today=_parse_date(args.date) if args.date else None, prior=prior)
        except TelosError as e:
            print(f"ABORT: {e}", file=sys.stderr)
            return 2
        print(json.dumps(result, indent=2))
        return 0

    if args.cmd == "bootstrap":
        print(json.dumps(bootstrap_surface(Path(args.repo).expanduser()), indent=2))
        return 0

    if args.cmd == "emit-ledger":
        result = json.loads(Path(args.result).read_text(encoding="utf-8"))
        judgments = json.loads(Path(args.judgments).read_text(encoding="utf-8")) if args.judgments else None
        sys.stdout.write(emit_ledger(result, judgments, args.date))
        return 0

    ap.print_help()
    return 1


# ── bundled self-test (stdlib; mirrors audit-repo/tests style) ───────────────────────────────────────
def _self_test() -> int:
    import unittest
    here = Path(__file__).resolve().parent
    suite = unittest.defaultTestLoader.discover(str(here / "tests"), pattern="test_*.py")
    runner = unittest.TextTestRunner(verbosity=2)
    return 0 if runner.run(suite).wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
