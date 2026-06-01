#!/usr/bin/env python3
"""Pip eval harness — reads the trace/decision spine back as a quality scorecard.

The harness never mutates behaviour. It produces a report a human reads (and,
in a later phase, *proposes* parameter diffs through the permission queue). This
file implements P1: Mode A, the deterministic scenario quality layer.

Mode A runs ``PipEngine.run()`` over each labelled scenario and compares the
chosen proposal to ``scenarios/eval_labels.json`` ground truth:

- ``top1_correct``      — chosen source_kind (and app, when labelled) matches.
- ``expected_in_top3``  — any ranked candidate matches the expected kind+app.
- ``margin_when_correct`` — the decision margin on correct picks (calibration).

A small Mode B helper (``evaluate_feedback``) is included for outcome metrics
over accumulated ``proposal_history``; the scenario layer is the CI floor.
"""
from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path
from typing import Any


def _load_labels(scenarios_dir: Path) -> dict[str, dict]:
    labels_path = scenarios_dir / "eval_labels.json"
    if not labels_path.exists():
        return {}
    with open(labels_path, "r", encoding="utf-8") as handle:
        raw = json.load(handle)
    return {k: v for k, v in raw.items() if not k.startswith("_")}


def evaluate_scenarios(scenarios_dir: str) -> dict[str, Any]:
    """Mode A — deterministic scenario quality layer. No model, CI-safe."""
    from pip_engine import PipEngine

    base = Path(scenarios_dir)
    labels = _load_labels(base)
    rows: list[dict[str, Any]] = []

    for scenario_name, label in labels.items():
        scenario_file = base / f"{scenario_name}.json"
        if not scenario_file.exists():
            rows.append({"scenario": scenario_name, "error": "missing_scenario_file"})
            continue

        expected_kind = label.get("kind", "none")
        expected_apps = set(label.get("apps", []))

        # Run on a throwaway memory so eval never touches real state.
        tmp_memory = tempfile.mktemp(prefix=f"pip-eval-{scenario_name}-", suffix=".json")
        engine = PipEngine(memory_path=tmp_memory)
        result = engine.run(str(scenario_file))
        Path(tmp_memory).unlink(missing_ok=True)

        proposal = result["proposal_card"]
        candidates = result.get("proposal_candidates", [])
        margin = result.get("decision_trace", {}).get("top_margin", 0.0)

        chosen_kind = proposal["source_kind"]
        chosen_app = candidates[0]["app_name"] if candidates else None

        def _matches(kind: str, app: str | None) -> bool:
            if kind != expected_kind:
                return False
            if expected_kind == "none":
                return True
            if not expected_apps:
                return True
            return app in expected_apps

        top1_correct = _matches(chosen_kind, chosen_app)
        expected_in_top3 = any(
            _matches(c.get("kind"), c.get("app_name")) for c in candidates[:3]
        ) or (expected_kind == "none" and not candidates)

        rows.append(
            {
                "scenario": scenario_name,
                "expected_kind": expected_kind,
                "expected_apps": sorted(expected_apps),
                "chosen_kind": chosen_kind,
                "chosen_app": chosen_app,
                "score": round(proposal["score"], 4),
                "margin": round(margin, 4),
                "top1_correct": top1_correct,
                "expected_in_top3": expected_in_top3,
                "margin_when_correct": round(margin, 4) if top1_correct else None,
            }
        )

    scored = [r for r in rows if "error" not in r]
    n = len(scored) or 1
    correct = [r for r in scored if r["top1_correct"]]
    summary = {
        "scenarios_scored": len(scored),
        "top1_accuracy": round(len(correct) / n, 4),
        "top3_accuracy": round(sum(r["expected_in_top3"] for r in scored) / n, 4),
        "mean_margin_when_correct": (
            round(sum(r["margin"] for r in correct) / len(correct), 4) if correct else None
        ),
    }
    return {"mode": "scenario", "summary": summary, "rows": rows}


def evaluate_feedback(memory_path: str) -> dict[str, Any]:
    """Mode B (single memory file) — outcome metrics over proposal_history."""
    path = Path(memory_path)
    if not path.exists():
        return {"mode": "feedback", "error": "memory_not_found", "summary": {}}
    with open(path, "r", encoding="utf-8") as handle:
        memory = json.load(handle)
    return evaluate_history(memory.get("proposal_history", []))


def evaluate_history(history: list[dict]) -> dict[str, Any]:
    """Mode B core — compute outcome metrics from proposal_history entries."""
    accepted = sum(1 for h in history if h.get("status") == "accepted")
    rejected = sum(1 for h in history if h.get("status") == "rejected")
    deferred = sum(1 for h in history if h.get("status") == "deferred")
    resolved = sum(1 for h in history if h.get("status") == "resolved")
    decided = accepted + rejected + deferred
    ever_proposed = len(history)

    # repeat_rejection_rate: rejected keys that later reappear as #1 candidate.
    rejected_keys = [h.get("proposal_key") for h in history if h.get("status") == "rejected"]
    reappeared = 0
    for idx, h in enumerate(history):
        key = h.get("proposal_key")
        if key in rejected_keys and any(
            later.get("top_candidates", [{}])[0:1] and
            later["top_candidates"][0].get("proposal_key") == key
            for later in history[idx + 1:]
        ):
            reappeared += 1
    repeat_rejection_rate = round(reappeared / len(rejected_keys), 4) if rejected_keys else 0.0

    # rank_quality (MRR): reciprocal rank of accepted key within top_candidates.
    rr_terms: list[float] = []
    for h in history:
        if h.get("status") != "accepted":
            continue
        key = h.get("proposal_key")
        cands = h.get("top_candidates", [])
        for rank, c in enumerate(cands, start=1):
            if c.get("proposal_key") == key:
                rr_terms.append(1.0 / rank)
                break
    mrr = round(sum(rr_terms) / len(rr_terms), 4) if rr_terms else None

    summary = {
        "ever_proposed": ever_proposed,
        "acceptance_rate": round(accepted / decided, 4) if decided else None,
        "rejection_rate": round(rejected / decided, 4) if decided else None,
        "resolution_rate": round(resolved / ever_proposed, 4) if ever_proposed else None,
        "rank_quality_mrr": mrr,
        "repeat_rejection_rate": repeat_rejection_rate,
    }
    return {"mode": "feedback", "summary": summary}


def build_eval_report(scenarios_dir: str | None = None, memory_path: str | None = None) -> dict[str, Any]:
    report: dict[str, Any] = {"verdict": "", "scenario": None, "feedback": None}

    if scenarios_dir:
        report["scenario"] = evaluate_scenarios(scenarios_dir)
    if memory_path:
        report["feedback"] = evaluate_feedback(memory_path)

    # Short human-readable verdict.
    parts: list[str] = []
    if report["scenario"]:
        s = report["scenario"]["summary"]
        parts.append(
            f"scenario top1={s['top1_accuracy']} top3={s['top3_accuracy']}"
        )
    if report["feedback"] and "summary" in report["feedback"]:
        f = report["feedback"]["summary"]
        if f.get("acceptance_rate") is not None:
            parts.append(
                f"acceptance={f['acceptance_rate']} repeat_reject={f['repeat_rejection_rate']}"
            )
    report["verdict"] = "; ".join(parts) if parts else "no data evaluated"

    # Make the eval run itself observable.
    try:
        import pip_traces
        pip_traces.record_trace(
            kind="eval_run",
            action="build_eval_report",
            status="ok",
            summary=report["verdict"],
            details={"has_scenario": bool(report["scenario"]), "has_feedback": bool(report["feedback"])},
            source="pip_eval",
            tags=["eval"],
        )
    except Exception:
        pass

    return report


def sweep_parameters(scenarios_dir: str = "scenarios") -> dict[str, Any]:
    import pip_engine
    
    orig_halt_margin = getattr(pip_engine, "HALT_MARGIN", 0.12)
    
    best_top1 = -1.0
    best_margin = -1.0
    best_config = {}
    
    results = []
    
    for margin_test in [0.08, 0.12, 0.16]:
        pip_engine.HALT_MARGIN = margin_test
        
        report = evaluate_scenarios(scenarios_dir)
        summary = report.get("summary", {})
        top1 = summary.get("top1_accuracy", 0)
        mean_margin = summary.get("mean_margin_when_correct") or 0.0
        
        results.append({
            "HALT_MARGIN": margin_test,
            "top1_accuracy": top1,
            "mean_margin": mean_margin
        })
        
        if top1 > best_top1 or (top1 == best_top1 and mean_margin > best_margin):
            best_top1 = top1
            best_margin = mean_margin
            best_config = {"HALT_MARGIN": margin_test}
            
    pip_engine.HALT_MARGIN = orig_halt_margin
    
    proposed = False
    diff = None
    if best_config and best_config["HALT_MARGIN"] != orig_halt_margin:
        proposed = True
        diff = f"- HALT_MARGIN = {orig_halt_margin}\\n+ HALT_MARGIN = {best_config['HALT_MARGIN']}"
        
        try:
            import pip_safety
            pip_safety.request_safety_permission(
                action_type="tuning_change",
                title="Approve Parameter Tuning Sweep",
                rationale=f"Sweep found improved params: {diff}",
                details={"best_config": best_config, "results": results}
            )
        except Exception:
            pass
            
    return {
        "best_config": best_config,
        "best_top1_accuracy": best_top1,
        "proposed_change": proposed,
        "diff": diff,
        "sweep_results": results
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Score Pip proposal quality (Mode A scenarios + optional feedback).")
    parser.add_argument("--scenarios", default="scenarios", help="Scenario directory (Mode A)")
    parser.add_argument("--memory", help="Optional memory JSON file for feedback metrics (Mode B)")
    parser.add_argument("--output", default="eval_report.json", help="Where to write the report")
    args = parser.parse_args()

    report = build_eval_report(scenarios_dir=args.scenarios, memory_path=args.memory)

    with open(args.output, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)

    print(f"Eval verdict: {report['verdict']}")
    if report["scenario"]:
        for row in report["scenario"]["rows"]:
            if "error" in row:
                print(f"  {row['scenario']}: ERROR {row['error']}")
                continue
            flag = "OK " if row["top1_correct"] else "MISS"
            print(
                f"  [{flag}] {row['scenario']}: chose {row['chosen_kind']}/{row['chosen_app']} "
                f"(expected {row['expected_kind']}/{row['expected_apps']}) margin={row['margin']}"
            )
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
