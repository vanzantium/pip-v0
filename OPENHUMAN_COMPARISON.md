# OpenHuman Comparison

Reviewed source: https://github.com/tinyhumansai/openhuman at commit `89380db`.

## Useful Patterns To Borrow

- Prompt-injection preflight guard: OpenHuman screens risky prompt patterns before chat/tool work. Pip now adapts this as `pip_prompt_guard.py` and wires it into the Token Governor.
- Tool-scoped memory rules: OpenHuman keeps durable instructions such as "never email Sarah" tied to specific tools. Pip now adapts this as `pip_tool_memory.py`, stored under the configured Pip memory folder.
- Tool policy boundary snapshots: OpenHuman renders a prompt-visible contract for allowed, denied, hidden, and approval-required tools. Pip should add a compact policy boundary next.
- Capped web-scraper/native tools: OpenHuman's native tools use timeouts, URL guards, and output caps. Pip can borrow this for a future draft-only web fetch skill.
- Token compression overlays: OpenHuman's TokenJuice has built-in, user, and project rule overlays. Pip should evolve the Token Governor toward similar command/tool-specific compression rules.
- Scheduler signals: OpenHuman samples power and CPU before background work. Pip can use the same idea for Nightwatch and ambient cycles.

## What Not To Pull In Yet

- Do not copy the hosted OAuth/Composio integration layer yet. Pip's first useful shape is still local, supervised, and approval-gated.
- Do not add broad external messaging or app-control integrations before the policy boundary and tool receipts are stronger.
- Do not depend on OS sandbox features as the main safety boundary. They are useful later, but Pip's current boundary should remain manifest permissions plus explicit approval.

## Applied In This Pass

- `pip_prompt_guard.py` blocks or reviews prompt-injection patterns before the Token Governor admits work.
- `pip_tool_memory.py` stores per-tool/app safety rules and can render critical/high rules as a compact boundary block.
- CLI skills expose prompt guard checks and tool-rule inspection/update.
- Dashboard surfaces the latest prompt-guard verdict and stored tool-memory rules.
