"""Tests for nested config validation and hash-bound ownership receipts (C2.4).

Validation must stop before mutation on any malformed nesting or unknown policy version. Receipts must
bind ownership to exact path+hash and exact registration tuples — never a substring — so upgrade and
uninstall touch only what the receipt records.
"""
from __future__ import annotations

from pathlib import Path

from excubitor.installers import receipts, validate
from excubitor.installers.receipts import OwnedFile, OwnedRegistration, Receipt

# --- settings validation ---------------------------------------------------------------------------

def test_clean_settings_validates() -> None:
    data = {"hooks": {"PreToolUse": [
        {"matcher": "Bash", "hooks": [{"type": "command", "command": "x", "timeout": 10}]}
    ]}}
    assert validate.validate_settings(data).ok


def test_empty_settings_validates() -> None:
    assert validate.validate_settings({}).ok
    assert validate.validate_settings({"hooks": {}}).ok
    assert validate.validate_settings({"hooks": {"PreToolUse": []}}).ok


def test_non_object_root_is_a_problem() -> None:
    assert not validate.validate_settings([]).ok
    assert not validate.validate_settings("nope").ok


def test_malformed_nesting_is_located_precisely() -> None:
    data = {"hooks": {"PreToolUse": [
        {"matcher": 123, "hooks": [{"type": "command", "command": "x", "timeout": "slow"}]},
        "not-an-object",
    ]}}
    result = validate.validate_settings(data)
    assert not result.ok
    joined = " ".join(result.problems)
    assert "hooks.PreToolUse[0].matcher" in joined
    assert "hooks.PreToolUse[0].hooks[0].timeout" in joined
    assert "hooks.PreToolUse[1]" in joined


def test_pretooluse_not_a_list_is_a_problem() -> None:
    assert not validate.validate_settings({"hooks": {"PreToolUse": {}}}).ok
    assert not validate.validate_settings({"hooks": "nope"}).ok


# --- policy validation -----------------------------------------------------------------------------

def test_default_and_v1_policy_validate() -> None:
    assert validate.validate_policy({}).ok  # absent version = v1
    assert validate.validate_policy({"version": 1}).ok


def test_unknown_policy_version_stops_with_guidance() -> None:
    result = validate.validate_policy({"version": 99})
    assert not result.ok
    assert "not supported" in result.problems[0]
    assert "migrate" in result.problems[0].lower()


def test_malformed_policy_nesting_is_caught() -> None:
    result = validate.validate_policy(
        {"one_unit": {"enabled": "yes"}, "self_integrity": {"protected_roots": [1, 2]},
         "default_branch": {"opt_out_marker": 5}}
    )
    assert not result.ok
    joined = " ".join(result.problems)
    assert "one_unit.enabled" in joined
    assert "self_integrity.protected_roots" in joined
    assert "default_branch.opt_out_marker" in joined


# --- receipts: exact, hash-bound ownership ---------------------------------------------------------

def _sample_receipt() -> Receipt:
    return Receipt(
        runtime="claude-code",
        scope="user",
        settings_path="/home/u/.claude/settings.json",
        excubitor_version="0.1.0",
        installed_at="2026-07-21T00:00:00Z",
        files=(OwnedFile("/home/u/.claude/hooks/guard-loop-vc.py", "abc123"),),
        registrations=(OwnedRegistration(matcher="Bash", command="python3 /h/guard-loop-vc.py",
                                         timeout=10),),
    )


def test_receipt_roundtrips_through_json() -> None:
    receipt = _sample_receipt()
    restored = Receipt.from_json(receipt.to_json())
    assert restored == receipt


def test_file_ownership_is_hash_bound() -> None:
    receipt = _sample_receipt()
    # Same path + same hash = ours.
    assert receipt.owns_file_bytes("/home/u/.claude/hooks/guard-loop-vc.py", "abc123")
    # Same path, DIFFERENT hash = drifted, not ours to remove.
    assert not receipt.owns_file_bytes("/home/u/.claude/hooks/guard-loop-vc.py", "deadbeef")
    assert receipt.records_path("/home/u/.claude/hooks/guard-loop-vc.py")  # but recorded → drift, not alien
    # A path we never recorded is never ours, whatever its hash.
    assert not receipt.owns_file_bytes("/home/u/.claude/hooks/user-thing.py", "abc123")
    assert not receipt.records_path("/home/u/.claude/hooks/user-thing.py")


def test_registration_ownership_is_exact_tuple_not_substring() -> None:
    receipt = _sample_receipt()
    assert receipt.owns_registration("PreToolUse", "Bash", "python3 /h/guard-loop-vc.py", 10)
    # Matcher order is semantic (set), so this equals the recorded one for a multi-matcher case:
    multi = Receipt(runtime="c", scope="u", settings_path="s", excubitor_version="0.1.0",
                    installed_at="t",
                    registrations=(OwnedRegistration(matcher="Edit|Write", command="c", timeout=10),))
    assert multi.owns_registration("PreToolUse", "Write|Edit", "c", 10)
    # A different command, timeout, or matcher-set is NOT owned — no substring leniency.
    assert not receipt.owns_registration("PreToolUse", "Bash", "python3 /h/guard-loop-vc.py", 15)
    assert not receipt.owns_registration("PreToolUse", "Bash", "echo guard-loop-vc.py", 10)
    assert not receipt.owns_registration("PreToolUse", "Edit", "python3 /h/guard-loop-vc.py", 10)


def test_unrecognized_receipt_schema_is_rejected() -> None:
    import pytest

    with pytest.raises(ValueError):
        Receipt.from_dict({"schema": "something.else", "runtime": "x", "scope": "y",
                           "settings_path": "s"})


# --- state dir / receipt path resolution -----------------------------------------------------------

def test_state_home_precedence(tmp_path: Path) -> None:
    explicit = receipts.state_home_dir(str(tmp_path / "explicit"))
    assert explicit == tmp_path / "explicit"
    env = receipts.state_home_dir(None, {"EXCUBITOR_STATE_HOME": str(tmp_path / "env")})
    assert env == tmp_path / "env"


def test_receipt_path_shape(tmp_path: Path) -> None:
    path = receipts.receipt_path("claude-code", "user", str(tmp_path))
    assert path == tmp_path / "receipts" / "claude-code-user.json"


def test_hash_file_matches_content(tmp_path: Path) -> None:
    import hashlib

    f = tmp_path / "a.py"
    f.write_bytes(b"print('hi')\n")
    assert Receipt.hash_file(f) == hashlib.sha256(b"print('hi')\n").hexdigest()
