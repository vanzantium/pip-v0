# Pip DOX Contract

## Purpose

- Keep coding agents aware of Pip's architecture, safety boundaries, and local verification before they edit.
- Use the nearest applicable `AGENTS.md` as the path-specific contract, with this root file providing repository-wide rules.

## Ownership

- The root contract owns project-wide safety, workflow, verification, and the Child DOX Index.
- Child contracts own durable rules for their specific folders.
- `pip_system_manifest.py` remains Pip's runtime self-map; this DOX tree is the builder-facing context map.

## Local Contracts

- Pip is local-first, supervised, draft-first, and approval-gated for higher-risk actions.
- Do not weaken permission gates, dashboard POST-token checks, path confinement, Prompt Guard, tool-memory boundaries, or task receipts.
- Do not add direct email writes, app control, dependency installation, repository modification, or external messaging without an explicit reviewed milestone.
- Keep Nightwatch inward-facing and Weekly Update outward-facing; neither may silently broaden the other's permissions.
- Runtime/private data belongs under configured Pip memory or ignored paths, not tracked source files.
- Prefer small reversible modules and explicit skill metadata over hidden cross-module behavior.
- `pip_task_monitor.py` may terminate ONLY Pip's own research child (the PID in `imports/_research_status.json`); all other process findings are draft-first reports, never actions.

## Work Guidance

- Before editing, read this file and every child `AGENTS.md` on the route to each target.
- Inspect existing code and tests before introducing a new subsystem.
- Update the nearest owning `AGENTS.md` when a meaningful change alters local purpose, contracts, workflow, inputs, outputs, permissions, or verification.
- Update this file when project-wide architecture or the Child DOX Index changes.
- Keep DOX operational and concise; stable contracts belong here, change history belongs in Git.

## Verification

- Run `python pip_doctor.py`.
- Run `python test_scenarios.py --scenarios scenarios` when engine, memory, proposal, or scenario behavior may change.
- Run a dashboard render smoke check when dashboard code or templates change:
  `python -c "import pip_control_panel; print(len(pip_control_panel.page({})))"`
- Run `git diff --check` before publishing.

## Child DOX Index

- `dashboard_ui/AGENTS.md` - dashboard template structure, safety, and rendering checks.
- `imports/AGENTS.md` - tracked templates versus private/runtime import data.
- `scenarios/AGENTS.md` - regression scenario and expected-memory contracts.
- `skills/AGENTS.md` - portable skill package structure, trust, and permissions.
