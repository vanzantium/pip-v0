# Security Notes

Pip v0 is a local, supervised assistant prototype. Treat it like a trusted local tool, not a hardened internet service.

## Safe Operating Assumptions

- Run the dashboard on `127.0.0.1` or a trusted home LAN only.
- Do not expose the control panel directly to the public internet.
- Keep Pip in draft-only mode unless a specific action is approved.
- Review portable skills before enabling broader permissions.
- Keep phone usage exports, memory files, traces, and scheduler receipts out of Git.

## Approval Boundaries

Pip should require approval before:

- editing original project files
- running arbitrary Python
- starting autonomous long-running goals
- controlling apps or UI
- recording keyboard or mouse macros
- sending messages or touching external services

Safe default work is limited to approved reads, Pip memory writes, draft-folder outputs, local dashboard rendering, and append-only receipts.

## Local Network Dashboard

The dashboard is designed for the user's laptop and phone on the same Wi-Fi. It does not currently provide production-grade authentication, rate limiting, or transport encryption.

Mutating dashboard requests use a per-server token injected into Pip-rendered pages. This blocks casual cross-site POSTs and stale external forms, but it is not a substitute for real authentication if the port is exposed beyond a trusted LAN.

If you need remote access later, put it behind a reviewed authenticated tunnel or reverse proxy instead of opening the port directly.

## Portable Skills

Portable skills are listed from JSON manifests first. Trusted built-in packages are lazy-loaded only when the selected skill runs, so `pip_skills.py list` should not execute arbitrary skill code. New third-party skill packages should stay untrusted until reviewed.

## Secrets And Personal Data

Before publishing or handing off a review bundle, check that generated/private artifacts are ignored:

```powershell
git status --short
git check-ignore -v config.json imports/s25_usage_last_7_days.json page_output.html temp.txt pip_task_runs.jsonl pip_traces.jsonl
```

Avoid committing:

- `config.json`
- `PipMemory/`
- `imports/s25_*.json`
- `imports/phone_upload_*.json`
- `pip_traces.jsonl`
- `pip_task_runs.jsonl`
- screenshots, dashboard dumps, and local review logs

## Review Focus

Reviewers should pay special attention to permission-gate bypasses, dashboard routes that launch work, portable skill loading, local path leaks, and any change that expands from "draft and propose" into "act directly."
