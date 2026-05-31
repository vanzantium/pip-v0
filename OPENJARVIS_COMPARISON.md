# OpenJarvis Comparison

Reviewed: 2026-05-30

Implementation status:

- Phase 1 trace spine: implemented in `pip_traces.py`, `inspect_traces`, dashboard Trace Spine card, and Flow Master/dashboard/CLI trace writes.
- Phase 2 system manifest: implemented in `pip_system_manifest.py`, `inspect_system_manifest`, `refresh_system_manifest`, dashboard System Map card, and doctor checks.
- Phases 3-5 remain planned: portable Pip skill packages, supervised scheduler, and model registry.

Sources:

- https://github.com/open-jarvis/OpenJarvis
- https://open-jarvis.github.io/OpenJarvis/
- https://arxiv.org/abs/2605.17172
- temporary local clone at `%TEMP%/OpenJarvis-review`

## High-Level Read

OpenJarvis is a local-first personal AI framework. Pip is a personal local assistant with a phone/laptop control loop, permission queue, memory compression, Flow Master pressure checks, and app-specific learning.

The overlap is strong, but the systems have different centers of gravity:

- OpenJarvis is a general framework/runtime for local agents.
- Pip is a safety-shaped personal organism/control loop.

So the right move is not to copy OpenJarvis wholesale. Pip should borrow its clean primitives, observability, scheduler shape, and skill ecosystem ideas while keeping Pip's draft-only approvals, phone control surface, and memory metaphors.

## What OpenJarvis Does Especially Well

### Five-Primitives Architecture

OpenJarvis names its main layers clearly:

- Intelligence: model catalog and model identity
- Engine: inference runtime such as Ollama, vLLM, llama.cpp, cloud
- Agents: simple, orchestrator, ReAct, CodeAct, persistent operators
- Tools and Memory: retrieval, file tools, web tools, persistent state
- Learning: traces, feedback, optimization, routing improvement

Pip already has fragments of this, but not a single manifest that names them.

Recommended Pip adaptation:

- Add a `pip_system_manifest.py` or JSON manifest that describes Pip's current primitives:
  - `governor`
  - `memory`
  - `skills`
  - `workspaces`
  - `agents/shells`
  - `control_surfaces`
  - `learning/evaluation`

### Trace and Telemetry Discipline

OpenJarvis records interactions as traces and inference calls as telemetry. This is one of the biggest lessons for Pip.

Pip currently has:

- token governor events
- jobs logs
- Flow Master receipts
- phone proposal history
- app skill XP evidence

But these are spread across separate files.

Recommended Pip adaptation:

- Add a lightweight `pip_traces.py`.
- Record every meaningful action as a trace:
  - skill run
  - dashboard action
  - permission request/decision
  - Flow Master assessment
  - autonomous job cycle
  - app skill XP event
- Store traces in SQLite or JSONL first.
- Add `python pip_skills.py run inspect_traces`.

This gives Pip a nervous system audit trail before any stronger autonomy.

### Skill Format and Skill Lifecycle

OpenJarvis treats skills as reusable packages with metadata, capability declarations, install/import sources, and optional optimization overlays.

Pip already has a Python skill registry and Codex/Claude/Antigravity shell profiles, but it lacks a portable skill package format.

Recommended Pip adaptation:

- Add a `skills/` folder in `pip-v0`.
- Use a simple Pip skill package:
  - `SKILL.md`
  - `skill.json`
  - optional `templates/`
  - optional `references/`
- Add capability declarations:
  - `read_memory`
  - `write_memory`
  - `read_workspace`
  - `write_draft`
  - `ui_automation`
  - `shell_execute`
- Keep dangerous skills approval-gated.

This fits Pip better than importing huge skill libraries immediately.

### Scheduled Operators

OpenJarvis has scheduled and continuous agents. Pip wants this too, but Pip needs tighter supervision.

Pip already has:

- ambient cycle
- jobs
- permission queue
- wake scheduling

Recommended Pip adaptation:

- Add a visible scheduler table:
  - task id
  - goal
  - schedule type: once, interval, daily
  - scope/workspace
  - allowed skills
  - next run
  - last result
  - status
- Default every scheduled task to draft-only.
- Require approval for:
  - code edits
  - UI automation
  - shell execution
  - sending messages

This borrows OpenJarvis's operator shape without giving Pip unbounded autonomy.

### Hardware-Aware Local Model Routing

OpenJarvis treats model choice, engine, cost, latency, and energy as first-class concerns.

Pip already has:

- hardware scan
- token governor
- local model recommendation

Recommended Pip adaptation:

- Add a local model registry:
  - model name
  - engine
  - RAM/VRAM fit
  - preferred task types
  - max context
  - privacy/cost notes
- Add a `route_model_for_task` skill.
- Keep it advisory at first.

This is a clean next step toward Pip actually choosing between local models later.

### Doctor Surfaces

OpenJarvis has strong `doctor` style surfaces for system health. Pip already has `pip_doctor.py`, which has been a very good pattern.

Recommended Pip adaptation:

- Expand doctor into categories:
  - memory
  - control panel
  - Flow Master
  - developer shells
  - scheduler/jobs
  - phone bridge
  - local model readiness
  - safety gates
- Add `python pip_skills.py run inspect_system_health` for dashboard/API use.

## What Not To Copy Yet

### Full Agent Runtime

OpenJarvis has many agent styles: orchestrator, ReAct, CodeAct, OpenHands, Claude Code, long-running operators.

Pip should not absorb all of this now. It would make Pip large before Pip's own safety loop is mature.

Better:

- Keep Codex/Claude/Antigravity as external developer shells.
- Add internal orchestration only for narrow draft-only loops.

### Huge Channel Integrations

OpenJarvis supports many channels, including WhatsApp-style messaging bridges.

Pip should not jump straight to this. The local S25 dashboard is safer and already working.

Better:

- Add one clean phone control protocol first.
- Treat WhatsApp/Telegram/Discord as later optional connectors.

### Automatic Skill Import From Massive Libraries

OpenJarvis can import large skill libraries from Hermes and OpenClaw.

Pip should not bulk import thousands of skills. That would swamp the memory/personality and increase risk.

Better:

- Import hand-picked skills into Pip's own format.
- Require capability review.
- Track which skills Pip actually uses.

### Learning That Mutates Behavior Automatically

OpenJarvis has trace-driven optimization and spec search.

For Pip, this should remain supervised:

- Pip can propose prompt/skill changes.
- Pip can write optimized overlays.
- User approves before behavior changes become active.

## Pip-Sized Build Plan

### Phase 1: Trace Spine

Add a single append-only trace layer. This unifies jobs, skill runs, Flow Master assessments, permission decisions, and dashboard actions.

Deliverables:

- `pip_traces.py`
- `pip_traces.jsonl` or `pip_traces.db`
- `record_trace(...)`
- `inspect_traces`
- dashboard recent trace card

### Phase 2: System Manifest

Define Pip's own primitive map.

Deliverables:

- `pip_system_manifest.py`
- `pip_system_manifest.json`
- dashboard system map card
- doctor check for required primitives

### Phase 3: Pip Skill Packages

Create a small portable skill format before importing external skills.

Deliverables:

- `skills/`
- `skill.json`
- `SKILL.md`
- `pip_skill_packages.py`
- `list_skill_packages`
- `inspect_skill_package`

### Phase 4: Supervised Scheduler

Upgrade ambient jobs into a visible scheduler inspired by OpenJarvis operators.

Deliverables:

- `pip_scheduler.py`
- schedule table in memory
- run logs
- pause/resume/cancel
- dashboard controls
- permission requirements per task

### Phase 5: Model Registry

Turn hardware recommendations into actual routing metadata.

Deliverables:

- `pip_model_registry.py`
- local model fit cards
- `inspect_models`
- `route_model_for_task`

## Priority Recommendation

Build the trace spine first.

Reason: OpenJarvis's best long-term advantage is not one specific agent. It is that the system can observe itself, learn from runs, and compare choices. Pip already has strong safety and memory concepts; a unified trace spine would let those concepts become measurable.

The clean next task:

`pip_traces.py` with JSONL append-only traces, plus dashboard visibility.

That unlocks later skill learning, scheduler reliability, app-skill progress, and safer autonomy.
