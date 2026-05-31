# Local Model Integration — Borrowed Brain, Heuristic Floor

Status: design, not yet implemented.
Prepared: 2026-05-31.

## Principle

Pip should *borrow* intelligence, not depend on it. Every model call must:

1. Be **advisory** — the deterministic heuristic is always the floor and runs
   if the model is absent, slow, or refused.
2. **Preserve invariants** — a model may polish wording; it must never change
   the routing-relevant facts (score, `source_kind`, `app_name`,
   `rationale_tags`). This is the OpenMythos lesson: keep the raw signal as an
   invariant while the model only reshapes the surface.
3. Pass the **governors** — `pip_token_guard` (budget) and `pip_flow_master`
   (pressure) gate the call, exactly as the `/goal` path already does.
4. Be **traced** — every call records a `pip_traces` event so the eval harness
   can later measure whether model output actually improved outcomes.

## Current state (the gap)

`PipEngine.generate_chat_response()` (pip_engine.py ~line 649) **already** calls
Ollama at `localhost:11434` with RAG injection and a dynamic system prompt. But:

- It selects the model from `hardware.json`, **bypassing
  `pip_model_registry.route_task()`**.
- It is **not** wrapped in `assess_interaction()` / `assess_flow_pressure()` —
  only the `/goal` branch in the same method is gated.
- It is the *broad chat* path — the largest, least-bounded surface — which the
  comparison docs explicitly said should **not** be the first real integration.

So the work is two parts: fix the ungated path, then add one clean narrow job as
the reference pattern.

## Part A — Gate the existing chat path (safety fix)

Wrap the Ollama call in the same gate the `/goal` path uses:

```python
flow = pip_flow_master.assess_flow_pressure(message, intent="chat")
gov  = pip_token_guard.assess_interaction(message, intent="chat",
                                          source_type="first_hand",
                                          source_name="Pip chat")
if flow["flow_state"] in {"DWELL", "SHED"} or not gov["allowed"]:
    pip_token_guard.record_event("chat", estimated_tokens=gov["estimated_tokens"],
                                 actual_tokens=0, saved_tokens=gov["estimated_tokens"],
                                 note="deferred by governor/flow")
    return gov.get("nudge") or flow["recommended_response"]
# ... existing Ollama call ...
pip_token_guard.record_event("chat", estimated_tokens=gov["estimated_tokens"],
                             actual_tokens=<measured>, saved_tokens=0)
```

Under high pressure Pip compresses or defers rather than expanding — the whole
point of the regulatory layer. This is a bug fix, not a feature.

Also route the model through the registry instead of only `hardware.json`:
prefer `route_task("chat")`, fall back to the hardware recommendation, fall back
to the lightest model. Keep the existing graceful "Ollama isn't running"
messages.

## Part B — The clean narrow job: `propose_reword`

The reference integration. Takes a heuristic `ProposalCard` (always available,
deterministic) and *optionally* asks a small local model to make the
`proposal` + `evidence` text gentler and clearer — **without touching any
invariant**.

```python
def propose_reword(card: dict, thermal: ThermalState) -> dict:
    # 1. Invariants captured up front — never sent for the model to decide.
    invariants = {k: card[k] for k in ("score", "source_kind", "rationale_tags")}

    # 2. Governors. If pressure is high or budget refused -> return card as-is.
    flow = pip_flow_master.assess_flow_pressure(card["proposal"], intent="reword")
    gov  = pip_token_guard.assess_interaction(card["proposal"], intent="reword",
                                              source_type="first_hand",
                                              source_name="Pip reword")
    if flow["flow_state"] in {"DWELL", "SHED"} or not gov["allowed"]:
        return {**card, "reworded": False, "reason": "deferred_by_governor"}

    # 3. Route to the formatting-tier model (qwen2.5:0.5b per registry).
    model = pip_model_registry.route_task("formatting")

    # 4. Call Ollama; on ANY failure return the heuristic card unchanged.
    new_text = _ollama_reword(model, card["proposal"], card["evidence"])
    if not new_text:
        return {**card, "reworded": False, "reason": "model_unavailable"}

    # 5. Reattach invariants. The model only ever produced surface text.
    out = {**card, **invariants,
           "proposal": new_text["proposal"], "evidence": new_text["evidence"],
           "reworded": True, "model": model}

    pip_traces.record_trace(kind="model_reword", action="propose_reword",
                            status="ok", summary=f"reworded via {model}",
                            details={"invariants_preserved": True},
                            source="pip_model", tags=["model", "reword"])
    return out
```

Why this job first:

- **Bounded** — fixed input (one card), fixed output shape, no open-ended
  autonomy.
- **Safe to fail** — heuristic text is always the fallback; offline-clean.
- **Invariant-preserving** — score/kind/tags are reattached *after* the model,
  so the LLM can never change what Pip decided, only how it's phrased.
- **Measurable** — pairs directly with the eval harness: A/B whether reworded
  proposals get accepted more than raw heuristic text (`reworded` flag lands in
  `proposal_history`).

## Skill registration

```python
SkillSpec(
    name="reword_proposal",
    description="Optionally soften/clarify a proposal card via a local model, "
                "preserving score, kind, and tags. Falls back to heuristic text.",
    inputs=["--result sample_result.json"],
    outputs=["reworded proposal card (or original if model unavailable)"],
    permissions=["read_memory", "local_model"],
)
```

Add a new `local_model` permission string to the capability vocabulary so model
access is explicitly declared and reviewable (same gating philosophy as
`shell_execute` / `ui_automation`).

## What stays out

- No model in the decision path (ranking stays deterministic in `pip_engine`).
- No model write access to memory, files, or original project artifacts.
- No remote/cloud models — `localhost:11434` only, fails gracefully.
- No streaming autonomy or multi-turn agent loops from this job.

## Test plan

- `test_model_integration.py`: mock Ollama. Assert (a) invariants identical
  before/after, (b) DWELL/SHED → card returned unchanged, (c) model timeout →
  heuristic fallback, (d) a `model_reword` trace is written on success.
- `pip_doctor.py`: add a `local_model` readiness check (Ollama reachable?
  registry model present?) — advisory, never a hard failure.

## Phasing

1. **P1 — Part A**: gate the existing chat path + route via registry. Safety fix.
2. **P2 — Part B**: `propose_reword` + `reword_proposal` skill + traces.
3. **P3**: feed the `reworded` flag into the eval harness and report the A/B.

Part A first — it closes a real gating hole that already ships.
