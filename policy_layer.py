"""
policy_layer.py

"Policies are code, not prose" -- the actual test of that claim is
whether a policy can be violated and CAUGHT, not just stated. A prose
rule ("always write receipt") is unenforceable by construction; nothing
checks it. This makes each policy a predicate over an event dict that
either passes or raises, so a violation is a concrete, catchable thing.
"""

from dataclasses import dataclass
from typing import Callable, Any, Dict, List


class PolicyViolation(Exception):
    def __init__(self, policy_name: str, detail: str):
        self.policy_name = policy_name
        self.detail = detail
        super().__init__(f"[{policy_name}] {detail}")


@dataclass
class Policy:
    name: str
    check: Callable[[Dict[str, Any]], bool]
    on_fail_message: str

    def enforce(self, event: Dict[str, Any]):
        if not self.check(event):
            raise PolicyViolation(self.name, self.on_fail_message)


# --- the actual policies from the ShellOS proposal, made checkable ----

def _has_receipt(event: dict) -> bool:
    return "receipt_id" in event and event["receipt_id"] is not None


def _no_history_overwrite(event: dict) -> bool:
    return event.get("write_mode") != "overwrite" or event.get("target") == "consolidation"
    # consolidation is the one sanctioned exception, and it's exempt
    # because it writes originals to receipts first -- see waking_loop.


def _main_requires_review(event: dict) -> bool:
    if event.get("ledger") != "main":
        return True
    return event.get("reviewed") is True


def _skeptic_pass_for_high_stakes(event: dict) -> bool:
    if event.get("stakes") != "high":
        return True
    return event.get("skeptic_pass_applied") is True


MAX_BLAST_RADIUS = 25  # records a single automated op may touch unattended


def _blast_radius_capped(event: dict) -> bool:
    """The 'fail small' half of 'fail small and open.' Receipts already
    make every operation visible (fail open, unconditional). This is
    the missing other half: no single automated operation may silently
    touch more than MAX_BLAST_RADIUS records. A bug in consolidation or
    pruning should corrupt a bounded slice, not the whole ledger in one
    pass -- graduated damage, not all-or-nothing."""
    affected = event.get("records_affected", 0)
    if affected <= MAX_BLAST_RADIUS:
        return True
    return event.get("manual_override") is True


POLICIES: List[Policy] = [
    Policy("always_write_receipt", _has_receipt,
           "Event has no receipt_id -- nothing may be filed without one."),
    Policy("never_overwrite_history", _no_history_overwrite,
           "write_mode=overwrite on a non-consolidation target -- history must be append-only "
           "except the one sanctioned consolidation path."),
    Policy("main_requires_review", _main_requires_review,
           "Entry targets MAIN ledger without reviewed=True."),
    Policy("skeptic_pass_for_high_stakes", _skeptic_pass_for_high_stakes,
           "stakes=high but skeptic_pass_applied is not True."),
    Policy("blast_radius_capped", _blast_radius_capped,
           f"records_affected exceeds {MAX_BLAST_RADIUS} with no manual_override -- "
           f"a single automated operation may not touch this many records unattended."),
]


class PolicyEngine:
    def __init__(self, policies: List[Policy] = None):
        self.policies = policies if policies is not None else POLICIES

    def check_all(self, event: Dict[str, Any]) -> List[PolicyViolation]:
        """Returns every violation rather than raising on the first --
        useful for reporting all problems with an event at once."""
        violations = []
        for p in self.policies:
            try:
                p.enforce(event)
            except PolicyViolation as v:
                violations.append(v)
        return violations

    def enforce_all(self, event: Dict[str, Any]):
        """Raises on the first violation -- use this at the actual
        write boundary, where you want a hard stop, not a report."""
        for p in self.policies:
            p.enforce(event)


if __name__ == "__main__":
    engine = PolicyEngine()

    print("=== A compliant event: passes all policies ===")
    good_event = {
        "receipt_id": "r_001",
        "write_mode": "append",
        "ledger": "main",
        "reviewed": True,
        "stakes": "low",
    }
    violations = engine.check_all(good_event)
    print(f"violations: {len(violations)}")
    assert violations == []

    print("\n=== A MAIN write with no review: should be caught ===")
    bad_event = {
        "receipt_id": "r_002",
        "write_mode": "append",
        "ledger": "main",
        "reviewed": False,
        "stakes": "low",
    }
    violations = engine.check_all(bad_event)
    for v in violations:
        print(f"  CAUGHT: {v}")
    assert len(violations) == 1 and violations[0].policy_name == "main_requires_review"

    print("\n=== A destructive overwrite outside consolidation: should be caught ===")
    overwrite_event = {
        "receipt_id": "r_003",
        "write_mode": "overwrite",
        "target": "main_ledger_direct_edit",
        "ledger": "side",
        "stakes": "low",
    }
    violations = engine.check_all(overwrite_event)
    for v in violations:
        print(f"  CAUGHT: {v}")
    assert any(v.policy_name == "never_overwrite_history" for v in violations)

    print("\n=== High stakes without skeptic pass: should be caught ===")
    high_stakes_event = {
        "receipt_id": "r_004",
        "write_mode": "append",
        "ledger": "side",
        "stakes": "high",
        "skeptic_pass_applied": False,
    }
    violations = engine.check_all(high_stakes_event)
    for v in violations:
        print(f"  CAUGHT: {v}")
    assert any(v.policy_name == "skeptic_pass_for_high_stakes" for v in violations)

    print("\n=== Consolidation touching 40 records with no override: should be caught ===")
    big_consolidation = {
        "receipt_id": "r_005",
        "write_mode": "overwrite",
        "target": "consolidation",
        "records_affected": 40,
    }
    violations = engine.check_all(big_consolidation)
    for v in violations:
        print(f"  CAUGHT: {v}")
    assert any(v.policy_name == "blast_radius_capped" for v in violations)

    print("\n=== Same 40-record consolidation WITH manual_override: should pass ===")
    overridden = dict(big_consolidation, manual_override=True)
    violations = engine.check_all(overridden)
    print(f"violations: {len(violations)}")
    assert violations == []

    print("\n=== A normal-sized consolidation (10 records): passes without override ===")
    small_consolidation = {
        "receipt_id": "r_006",
        "write_mode": "overwrite",
        "target": "consolidation",
        "records_affected": 10,
    }
    violations = engine.check_all(small_consolidation)
    print(f"violations: {len(violations)}")
    assert violations == []

    print("\n=== enforce_all() raises on first violation (hard stop at write boundary) ===")
    try:
        engine.enforce_all(bad_event)
    except PolicyViolation as v:
        print(f"Correctly raised: {v}")

    print("\nALL POLICY CHECKS CONFIRMED CATCHABLE, NOT JUST STATED")
