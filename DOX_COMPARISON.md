# DOX Comparison

Reviewed source: https://github.com/agent0ai/dox at commit `5cb5ba55bd1c0f7c1b31fe655fe36e2febb760d2`.

## What DOX Contributes

DOX is a small `AGENTS.md` hierarchy rather than an agent runtime. Its useful contract is:

- read root and path-local instructions before editing;
- let the nearest document own local details without weakening global rules;
- update affected context documents after meaningful structural or behavioral changes;
- keep a parent-to-child index so agents can discover the correct local contract;
- document stable operating rules instead of change-history diary entries.

## Fit For Pip

Pip already has a runtime self-map, permission system, traces, doctor checks, and developer shells. DOX fills a different gap: builder-facing context for Codex, Claude Code, Antigravity, and similar coding agents.

The initial Pip tree stays intentionally shallow:

- root project contract;
- dashboard UI contract;
- imports/privacy contract;
- scenario regression contract;
- portable skill contract.

This provides useful path-level guidance without creating documentation moss across every folder.

## Safety Adaptation

- `pip_system_manifest.py` remains the runtime machine-readable architecture map.
- `AGENTS.md` files guide coding agents but do not grant permissions.
- Child contracts may specialize local work but may not weaken Pip's root safety contract.
- `pip_doctor.py` validates the tree and required indexes.
