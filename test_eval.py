#!/usr/bin/env python3
"""Tests for pip_eval — scenario quality (Mode A) and feedback metrics (Mode B)."""
from __future__ import annotations

import pip_eval


def test_scenarios_all_pass() -> list[str]:
    failures: list[str] = []
    result = pip_eval.evaluate_scenarios("scenarios")
    summary = result["summary"]
    if summary["top1_accuracy"] < 1.0:
        failures.append(f"expected top1_accuracy 1.0, got {summary['top1_accuracy']}")
    if summary["top3_accuracy"] < 1.0:
        failures.append(f"expected top3_accuracy 1.0, got {summary['top3_accuracy']}")
    return failures


def test_feedback_directions() -> list[str]:
    failures: list[str] = []

    # Good history: the accepted proposal was ranked #1, nothing repeats after rejection.
    good = [
        {"status": "accepted", "proposal_key": "attention_drain::TikTok",
         "top_candidates": [{"proposal_key": "attention_drain::TikTok"}]},
        {"status": "resolved", "proposal_key": "attention_drain::TikTok",
         "top_candidates": [{"proposal_key": "attention_drain::TikTok"}]},
    ]
    g = pip_eval.evaluate_history(good)["summary"]
    if g["repeat_rejection_rate"] != 0.0:
        failures.append(f"good history repeat_rejection_rate should be 0.0, got {g['repeat_rejection_rate']}")
    if g["rank_quality_mrr"] != 1.0:
        failures.append(f"good history MRR should be 1.0, got {g['rank_quality_mrr']}")

    # Bad history: a rejected key reappears as #1 later — repeat_rejection_rate should be high.
    bad = [
        {"status": "rejected", "proposal_key": "notification_drag::Gmail",
         "top_candidates": [{"proposal_key": "notification_drag::Gmail"}]},
        {"status": "proposed", "proposal_key": "notification_drag::Gmail",
         "top_candidates": [{"proposal_key": "notification_drag::Gmail"}]},
    ]
    b = pip_eval.evaluate_history(bad)["summary"]
    if b["repeat_rejection_rate"] <= 0.0:
        failures.append(f"bad history repeat_rejection_rate should be > 0, got {b['repeat_rejection_rate']}")

    return failures


def main() -> None:
    failures: list[str] = []
    failures += test_scenarios_all_pass()
    failures += test_feedback_directions()

    if failures:
        print("Eval tests failed:")
        for f in failures:
            print(f"- {f}")
        raise SystemExit(1)
    print("Eval tests passed.")


if __name__ == "__main__":
    main()
