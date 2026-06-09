# Scenario Contract

## Purpose

- Own deterministic regression inputs and expected memory behavior for Pip's proposal engine.

## Ownership

- Scenario JSON files are inputs.
- `*.assert.memory.json` files define expected durable outcomes.
- Generated `*.memory.json` files are supporting fixtures and must remain consistent with their scenario purpose.
- `manifest.json` and `eval_labels.json` describe the scenario pack.

## Local Contracts

- Use synthetic data only.
- Preserve existing scenario names unless a deliberate migration updates all references.
- Behavioral changes must update assertions intentionally, not merely silence failures.
- New scenarios should target a distinct ranking, memory, feedback, or safety behavior.

## Work Guidance

- Keep fixtures readable enough to explain why a proposal should win.
- Prefer adding a narrow scenario over overloading an existing one with unrelated behavior.

## Verification

- Run `python test_scenarios.py --scenarios scenarios`.
- Run `python pip_doctor.py`.

## Child DOX Index
