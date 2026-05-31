# Eval Harness Design — Closing the Trace → Eval → Improvement Loop

Status: design, not yet implemented.
Prepared: 2026-05-31.

## Why

Pip already *writes* observability (`pip_traces.jsonl`, `proposal_history`,
Flow Master receipts) but nothing *reads it back to measure quality*. Until
traces feed a scorecard, "regulated, not optimising" is a philosophy rather
than a demonstrable, improvable system.

The data needed to close the loop already exists:

- `MemoryState.proposal_history` entries carry `status`
  (`proposed` / `accepted` / `rejected` / `deferred` / `resolved` / `composted`)
  and `top_candidates` (ranked `proposal_key` + `score`).
- `PipEngine.run()` emits `decision_trace` (`loops_run`, `halted_reason`,
  `top_margin`).
- `pip_traces.read_traces()` exposes `flow_assessment` events with
  `composite_threat_score` and resulting state.

The harness consumes these. It never mutates behaviour on its own — it produces
a report a human reads, and at most *proposes* a parameter diff through the
existing permission queue. This keeps the "learning stays supervised" rule.

## Two eval modes

### Mode A — Scenario eval (offline, deterministic)

Extends the existing `test_scenarios.py` / `scenarios/*.json` +
`*.assert.memory.json` pack. Today that pack is pass/fail. Add a *quality*
layer:

- Run `PipEngine.run()` over each scenario.
- Compare the chosen `proposal_card.source_kind` + `app_name` to a labelled
  `expected_top` field added to each `*.assert.memory.json`.
- Score: `top1_correct` (bool), `expected_in_top3` (bool),
  `margin_when_correct` (calibration signal).

Deterministic, no model, runs in CI. This is the regression floor.

### Mode B — Feedback eval (from real + simulated history)

Reads accumulated `proposal_history` (and `pip_traces.jsonl`) and computes
outcome metrics. This is where real-world quality shows up.

## Metrics (v1)

| Metric | Definition | Good direction |
|--------|-----------|----------------|
| `acceptance_rate` | accepted / (accepted + rejected + deferred) | high |
| `rejection_rate` | rejected / decided | low |
| `resolution_rate` | resolved / ever-proposed | high |
| `rank_quality` (MRR) | mean reciprocal rank of the *accepted* key within `top_candidates` | →1.0 |
| `repeat_rejection_rate` | share of rejected `proposal_key`s that reappear as #1 within N cycles | **low** (tests skin/cooldown) |
| `margin_calibration` | acceptance rate in high-`top_margin` cycles minus low-margin cycles | positive |
| `regulation_alignment` | when Flow Master fired DWELL/SHED, share where user then deferred/rejected | positive |

`repeat_rejection_rate` is the keystone: it directly measures whether the
fur/skin/cooldown machinery in `apply_feedback()` actually suppresses things the
user already said no to. That is the single most important number for a
regulatory system.

## Module shape

New file `pip_eval.py`:

```python
def evaluate_scenarios(scenarios_dir: str) -> dict   # Mode A
def evaluate_feedback(memory_path: str) -> dict       # Mode B, single memory file
def evaluate_history(traces: list[dict]) -> dict      # Mode B, from trace spine
def build_eval_report(...) -> dict                    # merge + summarise
```

Output: `eval_report.json` (gitignored — runtime artifact) with the metric
table, per-scenario rows, and a short `verdict` string. Also append one
`pip_traces.record_trace(kind="eval_run", ...)` so eval runs are themselves
observable.

## Skill registration

Add to `pip_skills.py` (matches existing `SkillSpec` pattern):

```python
SkillSpec(
    name="run_eval",
    description="Score proposal quality over scenarios and feedback history.",
    inputs=["--scenarios scenarios", "--memory optional", "--output optional"],
    outputs=["eval_report.json", "eval metric summary"],
    permissions=["read_memory"],
)
```

Dashboard: an "Eval" card showing the metric table + last `verdict`, mirroring
the existing Trace Spine / System Map cards.

## The supervised improvement step (the actual loop closure)

`pip_eval.py` gains an optional **sweep**:

1. Replay the labelled history under a small grid of parameter sets —
   candidates are the engine constants: `HALT_MARGIN` (0.12), skin decay
   (`* 0.92`), cooldown decay (`* 0.82`), and the per-kind score weights in
   `build_candidates()`.
2. Report which set would have produced higher `acceptance_rate` and lower
   `repeat_rejection_rate` on the existing history.
3. **Do not apply it.** Emit a `ProposalCard`-shaped diff and file a
   `pip_safety.request_safety_permission("tuning_change", ...)`. The user
   approves before any constant changes. Behaviour only shifts behind a review
   gate.

This is the full trace → eval → improvement loop, with the human as the commit
step — consistent with the project's "Pip proposes, user approves" doctrine.

## Test plan

- `test_eval.py`: synthetic history with a known-good and known-bad ranking;
  assert `acceptance_rate` and `repeat_rejection_rate` move in the expected
  direction.
- Extend `pip_doctor.py` with an `eval` category: warn if `eval_report.json` is
  stale or `repeat_rejection_rate` exceeds a threshold.

## Phasing

1. **P1 — Mode A quality layer** on top of existing scenario tests (cheap, CI-safe).
2. **P2 — Mode B metrics** + `run_eval` skill + dashboard card.
3. **P3 — Supervised sweep** with permission-gated parameter proposals.

P1 is the right first commit: small, deterministic, and it makes the rest
measurable.
