# Odysseus Comparison Notes

Reference: <https://github.com/pewdiepie-archdaemon/odysseus>

## What Pip Should Borrow

- **Security-first public posture.** Keep a visible `SECURITY.md`, local-only defaults, and clear warnings against exposing the dashboard directly.
- **Operational receipts.** Preserve durable records of task launches and status changes so background behavior can be reviewed after the fact.
- **Tool/model fit awareness.** Route heavier work through explicit scoring instead of assuming one local model is always appropriate.
- **Small, inspectable modules.** Prefer simple files with clear boundaries over a large opaque agent core.

## What Pip Should Not Borrow Yet

- **Broad autonomy claims.** Pip's safest v0 lane remains inspect, condense, propose, draft, and wait for approval.
- **External account/app integration as a foundation.** Phone/browser/local dashboard control should mature before Pip touches messaging, email, calendars, or app automation.
- **Security theater.** Receipts, docs, and checks should be honest about current limits rather than implying hardened production controls.

## Applied In This Build

- Added `SECURITY.md` for LAN/local safety boundaries and publishing hygiene.
- Added `pip_task_runs.py` for append-only task-run receipts.
- Exposed task-run receipts through `python pip_skills.py run inspect_task_runs` and `/task-runs`.
- Added dashboard rendering for "Task Run Receipts."
- Expanded `pip_model_registry.py` with lightweight model-fit scoring and candidate rankings.
- Expanded `pip_doctor.py` so these pieces are checked before GitHub updates.
