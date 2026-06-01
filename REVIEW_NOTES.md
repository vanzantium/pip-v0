# Pip v0 Review Notes

Prepared for cautious external review before publishing/updating GitHub.

## Current Positioning

Pip v0 is a local, supervised assistant prototype. The strongest current claim is not "full autonomy"; it is that Pip now has a safer scaffold for local work:

- approved workspace boundaries
- draft-only project outputs
- a phone-friendly local dashboard
- explicit permission queues for risky actions
- traceable skill/dashboard activity
- early memory, model-routing, and self-reflection experiments

The fair framing is: Pip can inspect, condense, propose, queue, and learn from local artifacts. She should not be described as able to freely edit originals, automate apps, send messages, or run background work without approval.

## Recently Added

- `pip_traces.py` adds an append-only trace spine for skill runs, Flow Master checks, dashboard actions, and future handoffs.
- `pip_task_runs.py` adds append-only receipts for scheduler events, Nightwatch launches, and background script runs.
- `pip_system_manifest.py` gives Pip a compact self-map of roots, primitives, safety contract, and control surfaces.
- `pip_skill_registry.py` adds portable local skill packages from `skills/`.
- Portable skills are now manifest-listed and lazy-loaded so listing skills does not execute package code.
- `skills/brain_io/` moves brain file search/read/write and macro recording into a declared portable skill bundle.
- `pip_model_registry.py` adds early local model routing metadata and lightweight fit scoring for Ollama-style models.
- `pip_scheduler.py` adds a simple supervised scheduler state file.
- `pip_background_tasks.py` adds controlled background script launching helpers.
- `pip_self_model.py`, `pip_self_reflection.py`, `pip_dynamic_prompt.py`, `pip_embeddings.py`, and `pip_finetune_curator.py` add early self-model/RAG/fine-tune curation scaffolding.
- `pip_flow_master.py` adds safe text-pressure assessment. It does not block apps or monitor device input.
- `SECURITY.md` documents cautious local/LAN operation, approval boundaries, and publishing hygiene.

## Safety Notes

- Nightwatch and efficiency scripts now request permission before starting from the dashboard.
- Dashboard POST routes now require a per-server token injected into Pip-rendered pages.
- Enabling Windows startup now goes through the permission queue instead of writing directly from the button press.
- High-risk skills such as arbitrary Python, UI automation, and macro recording remain approval-gated.
- Original project files should still be treated as protected. Pip's default useful mode is draft-only.
- Portable skills must declare permissions and should be reviewed before trust is expanded.
- Self-reflection and RAG memory are experimental. User pruning/correction is part of the design, not an afterthought.

## Suggested Review Focus

- Verify permission boundaries before any background execution or UI automation.
- Inspect whether portable skill loading should eventually require signatures or an allowlist.
- Verify dashboard token protection is sufficient for trusted-LAN use, and do not treat it as internet-grade auth.
- Review local model routing assumptions against the user's real installed models and hardware.
- Confirm memory files do not leak personal paths or private usage data into GitHub.
- Check dashboard wording so it communicates capability without overstating autonomy.
- Confirm task-run receipts are useful for auditing without storing sensitive content.

## Smoke Test Commands

```powershell
python pip_doctor.py
python test_scenarios.py --scenarios scenarios
python pip_skills.py run list_skill_packages
python pip_skills.py run inspect_model_registry
python pip_skills.py run route_model_task --task-type coding
python pip_skills.py run inspect_task_runs --limit 10
python pip_skills.py run refresh_system_manifest
```

## Known Limits

- No native Android app yet.
- No WhatsApp/Telegram/Discord bridge yet.
- No unsupervised app automation.
- No guaranteed local LLM availability; Ollama/model calls should fail gracefully.
- Nightwatch is a supervised experiment, not a daemon to leave running without review.
