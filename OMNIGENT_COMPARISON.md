# Omnigent vs. Pip Architecture Comparison

Omnigent is an open-source meta-harness designed to orchestrate AI agents across devices, with strong built-in sandboxing and policy engines. Many of its features map directly to the goals in Pip's `S25_ROADMAP.md`.

## Key Omnigent Capabilities

1. **Cross-Device Session Sync:** Omnigent syncs sub-agents, terminals, and files seamlessly between phone, web UI, and terminal.
2. **Native Windows Sandboxing:** It runs natively on Windows using Job Objects for process-tree containment.
3. **YAML Custom Agents:** It defines custom sub-agents via YAML and orchestrates them (e.g., Claude Code, Cursor, Pi).
4. **Policy Engine:** It governs agents, pauses for approval before risky actions, and caps spend.

## What Pip Borrows (Option A Implementation)

### 1. Windows Job Objects for Sandboxing
- **Omnigent's Approach:** Wraps spawned terminal wrappers in Windows Job Objects so that any subprocesses (like agents executing arbitrary code) are contained and can be killed cleanly, respecting resource limits.
- **Pip's Implementation:** We are integrating Windows Job Object APIs into `policy_layer.py`. Whenever Pip spawns a potentially risky process (e.g., shell automation, developer shells), it should run inside a Job Object. This natively prevents escape on Windows, aligning with Pip's goal of strict local containment.

### 2. Formalizing "Passes" (Future Roadmap)
- Pip's `waking_loop` relies on distinct scripts (`SKEPTIC_PASS_SPEC`, reviewer pass, etc.). Taking a cue from Omnigent's YAML manifests, we can restructure these passes into declarative YAML files in the future, allowing dynamic hot-swapping.

### 3. Cross-Device Sync (Future Roadmap)
- Pip's Phase 1 requires bridging the Android S25 app to the PC. Omnigent's session state-sync protocol provides a perfect reference architecture for `pip_control_panel.py` and the future Android telemetry sync.

## Verdict
Omnigent proves that a robust, multi-agent meta-harness can be built natively without cloud reliance. Pip will remain a specialized personal compression engine, but will adopt Omnigent's infrastructure patterns for OS-level safety (Job Objects) and cross-device state management.
