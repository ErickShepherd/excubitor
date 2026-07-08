#!/usr/bin/env python3
"""leak_check.py — the deterministic scanner the leak-guard skill runs at a private→public boundary.

A leak is asymmetric: once an artifact is published it is cached and indexed, effectively
irreversible; the scan that prevents it is cheap. So this gates the build — it exits **non-zero on any
finding** (CI-wireable) and **fails closed** (a path it cannot read is treated as not-clean, never
waved through). Stdlib only; it never imports or executes the scanned content.

It finds two things:

  1. **Structured secrets** — a small, curated, HIGH-CONFIDENCE set of built-in patterns (private-key
     blocks, AWS keys, common token shapes, URL credentials). Deliberately NOT an entropy/"looks
     random" heuristic: a noisy guard is a disabled guard, so this errs toward precision and documents
     the gap (see LIMITS) rather than drowning real findings in false positives.
  2. **Your private tokens** — literal strings or regexes YOU supply via --private-tokens, the actual
     leak-guard job: the names/systems/numbers from your private source-of-truth that must never ship.
     The guard cannot know these; you tell it.

Whitelisting is **explicit and reported, never silent** — an allowed match is suppressed AND counted in
the summary, so an intentional exception can never quietly become a blanket hole.

Findings are printed **masked** (`abcd…[n chars]`) — printing the full secret to a log/CI transcript
would re-leak it.

Usage:
  leak_check.py <path>... [--private-tokens FILE] [--allow STR ...] [--allow-file FILE] [--no-builtin]
    <path>            file or directory (dirs scanned recursively, text files only)
    --private-tokens  file of must-never-ship patterns, one per line: a literal, or `re:<regex>`;
                      blank lines and `#`-comments ignored
    --allow           an exact matched-text string to whitelist (repeatable)
    --allow-file      file of whitelist strings, one per line
    --no-builtin      scan only --private-tokens (skip the built-in secret patterns)

Exit codes:  0 clean · 1 finding(s) after whitelist · 2 usage/read error (fail-closed)

LIMITS (honest): pattern/literal matching, not semantic understanding. It will miss a secret whose
shape it has no pattern for, a private token you did not supply, a secret split across lines or
base64-wrapped, or one only present in a binary/rendered asset it skips. It is a deterministic gate for
the known-shape and known-token cases — a seatbelt at the boundary, not a proof of cleanliness.

The `--private-tokens` file is TRUSTED input — you author it, it is as trusted as the code it guards.
A `re:` rule there is run against the (untrusted) scanned content, so a PATHOLOGICAL regex (catastrophic
backtracking, e.g. `re:(a+)+$`) can be driven to hang by crafted content — a self-inflicted ReDoS. The
built-in patterns are all linear and ReDoS-safe; keep your own `re:` rules linear too (avoid nested
quantifiers). A stdlib scanner cannot interrupt a Python regex mid-backtrack without a per-match
subprocess sandbox, which would be out of proportion for owner-authored input — so this is a documented,
accepted residual (see KNOWN-BYPASSES.md), not a silently-hoped-away one.
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

# ── built-in structured-secret patterns (curated for precision, not coverage) ────────────────────────
# Each is a (name, regex). Kept high-confidence on purpose: a false positive that trains the user to
# ignore the guard is worse than a documented miss (see LIMITS).
_BUILTIN: list[tuple[str, "re.Pattern[str]"]] = [
    ("private-key-block", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----")),
    ("aws-access-key-id", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("github-token", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36,}\b")),
    ("github-fine-grained-pat", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{22,}\b")),
    ("openai-key", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b")),
    ("slack-token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    ("google-api-key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("slack-webhook", re.compile(r"https://hooks\.slack\.com/services/[A-Za-z0-9/]+")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")),
    # credentials embedded in a URL: scheme://user:password@host  (skip the common empty-password and
    # placeholder cases to stay high-confidence)
    ("url-credentials", re.compile(r"\b[a-zA-Z][a-zA-Z0-9+.-]*://[^\s:/@]+:[^\s:/@]+@[^\s/]+")),
]

@dataclass(frozen=True)
class Finding:
    location: str   # path:line
    category: str   # pattern name
    masked: str     # redacted matched text


def mask(s: str) -> str:
    """Redact a matched secret for safe printing: keep a 4-char prefix, hide the rest, note length."""
    s = s.strip()
    if len(s) <= 4:
        return f"…[{len(s)} chars]"
    return f"{s[:4]}…[{len(s)} chars]"


def load_private_patterns(path: Path) -> list[tuple[str, "re.Pattern[str]"]]:
    """Parse a --private-tokens file: each non-blank, non-`#` line is a literal, or `re:<regex>`.

    A literal is matched case-insensitively and NOT anchored (a substring match) — that is how a
    private name/number leaks into rendered prose. A bad regex fails LOUD (SystemExit 2), never
    silently skipped, so a typo in the canon can't quietly disable a rule."""
    out: list[tuple[str, "re.Pattern[str]"]] = []
    for i, raw in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        # The category LABEL must be opaque: it is printed beside every finding, and a private token
        # is exactly what "must never ship" — embedding the rule text here would re-leak the secret into
        # the CI transcript, defeating the masking. Label by the rule's LINE in the tokens file so the
        # operator can locate it without the value ever reaching stdout/stderr.
        if line.startswith("re:"):
            expr = line[3:]
            try:
                out.append((f"private-regex@{i}", re.compile(expr)))
            except re.error as e:
                # a malformed rule is a usage error → exit 2 (matches the exit-code table), and it is
                # LOUD (never a silently-skipped rule that would quietly disable a leak check). Point at
                # the line, not the pattern text (which may itself embed the literal being hunted); the
                # re.error message is structural (position/reason), not an echo of the pattern.
                print(f"leak_check: bad private regex at {path}:{i}: {e}", file=sys.stderr)
                raise SystemExit(2)
        else:
            out.append((f"private-literal@{i}", re.compile(re.escape(line), re.IGNORECASE)))
    return out


def scan_text(text: str, patterns: list[tuple[str, "re.Pattern[str]"]], allow: set[str],
              location_prefix: str) -> tuple[list[Finding], int]:
    """Scan text line-by-line against patterns. Returns (findings, suppressed_count).

    A match whose exact text is in `allow` is suppressed but COUNTED (explicit whitelisting is
    reported, never silent)."""
    findings: list[Finding] = []
    suppressed = 0
    for lineno, line in enumerate(text.splitlines(), 1):
        for name, rx in patterns:
            for m in rx.finditer(line):
                matched = m.group(0)
                if matched in allow or matched.strip() in allow:
                    suppressed += 1
                    continue
                findings.append(Finding(f"{location_prefix}:{lineno}", name, mask(matched)))
    return findings, suppressed


def _looks_binary(path: Path) -> bool:
    """True iff the file's CONTENT looks binary (a NUL byte in the first 8 KiB). Keyed on CONTENT, not
    extension: a text file with a binary-ish name (notes.pdf, config.bin, a text foo.so) must still be
    scanned — skipping it by extension would silently miss a secret pasted into it, the dangerous
    fail-open direction for a gate. A genuinely binary file has a NUL early and is skipped (and the skip
    is reported by scan(), never silent)."""
    try:
        with path.open("rb") as f:
            return b"\x00" in f.read(8192)
    except OSError:
        return False  # let the caller's read attempt surface the real error (fail-closed there)


def iter_files(paths: list[Path]) -> "tuple[list[Path], list[str]]":
    """Expand paths to a list of files to scan, plus a list of error strings (missing paths etc.)."""
    files: list[Path] = []
    errors: list[str] = []
    for p in paths:
        if p.is_dir():
            files.extend(sorted(q for q in p.rglob("*") if q.is_file()))
        elif p.is_file():
            files.append(p)
        else:
            errors.append(f"{p}: not a file or directory")
    return files, errors


def scan(paths: list[Path], patterns: list[tuple[str, "re.Pattern[str]"]],
         allow: set[str]) -> tuple[list[Finding], int, list[str], list[str]]:
    """Scan all paths. Returns (findings, suppressed_count, errors, skipped_binary). Unreadable files
    become errors (fail-closed: an un-scannable path is treated as not-verified → non-zero exit);
    content-detected binary files are skipped but REPORTED (a skip is visible, never silent)."""
    files, errors = iter_files(paths)
    findings: list[Finding] = []
    suppressed = 0
    skipped: list[str] = []
    for f in files:
        if _looks_binary(f):
            skipped.append(str(f))
            continue
        try:
            text = f.read_text(encoding="utf-8", errors="strict")
        except (OSError, UnicodeDecodeError) as e:
            errors.append(f"{f}: could not read as text ({e.__class__.__name__}) — treated as not-clean")
            continue
        fnd, sup = scan_text(text, patterns, allow, str(f))
        findings.extend(fnd)
        suppressed += sup
    return findings, suppressed, errors, skipped


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Deterministic private→public leak scanner (leak-guard).")
    ap.add_argument("paths", nargs="+", help="files or directories to scan")
    ap.add_argument("--private-tokens", help="file of must-never-ship patterns (literal or re:<regex>); "
                                             "TRUSTED input — keep re: rules linear (a pathological one "
                                             "can ReDoS on crafted content; see the module LIMITS)")
    ap.add_argument("--allow", action="append", default=[], help="exact matched text to whitelist (repeatable)")
    ap.add_argument("--allow-file", help="file of whitelist strings, one per line")
    ap.add_argument("--no-builtin", action="store_true", help="skip built-in secret patterns")
    args = ap.parse_args(argv)

    patterns: list[tuple[str, "re.Pattern[str]"]] = [] if args.no_builtin else list(_BUILTIN)
    if args.private_tokens:
        pt = Path(args.private_tokens)
        if not pt.is_file():
            print(f"leak_check: --private-tokens file not found: {pt}", file=sys.stderr)
            return 2  # fail-closed: asked to use a canon we can't read
        patterns += load_private_patterns(pt)
    if not patterns:
        print("leak_check: nothing to scan for (built-ins disabled and no --private-tokens)", file=sys.stderr)
        return 2

    allow: set[str] = set(args.allow)
    if args.allow_file:
        af = Path(args.allow_file)
        if not af.is_file():
            print(f"leak_check: --allow-file not found: {af}", file=sys.stderr)
            return 2
        allow |= {ln.strip() for ln in af.read_text(encoding="utf-8", errors="replace").splitlines()
                  if ln.strip() and not ln.startswith("#")}

    findings, suppressed, errors, skipped = scan([Path(p) for p in args.paths], patterns, allow)

    for e in errors:
        print(f"ERROR  {e}", file=sys.stderr)
    for f in findings:
        print(f"LEAK   {f.location} — {f.category}: {f.masked}")
    for s in skipped:
        print(f"note: skipped (binary content, not scanned): {s}", file=sys.stderr)  # a skip is visible
    if suppressed:
        print(f"note: {suppressed} match(es) suppressed by explicit whitelist", file=sys.stderr)

    if findings or errors:
        print(f"leak_check: BLOCK — {len(findings)} finding(s), {len(errors)} error(s)", file=sys.stderr)
        return 1 if findings and not errors else (1 if findings else 2)
    print("leak_check: clean", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
