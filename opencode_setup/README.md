# Pip's Free Local Coding System - OpenCode + Ollama

Goal: a completely free, offline, agentic coding agent Pip can call - opencode
CLI driving your local Ollama. Zero API cost. Verified against opencode.ai/docs.

## The one blocker we hit
The DESKTOP app (@opencode-aidesktop\OpenCode.exe) is an Electron GUI - passing
it `run` args just opens a window. The headless `opencode run` mode is real but
lives in the CLI BINARY, which is a separate install.

## Setup (once)

1. Install the opencode CLI binary (pick one):
   - Bun/curl:  `curl -fsSL https://opencode.ai/install | bash`  (run in Git Bash on Windows)
   - npm:       `npm install -g opencode-ai`
   Then confirm:  `opencode --version`   (this is the CLI, NOT OpenCode.exe)

2. Point it at Ollama (free/local). Copy this folder's `opencode.json` to:
       %USERPROFILE%\.config\opencode\opencode.json
   Pull a tool-capable model first:  `ollama pull qwen2.5-coder:7b`
   (any tool-calling model works: qwen2.5-coder, llama3.1, mistral-nemo).
   The baseURL MUST be http://localhost:11434/v1 (Ollama's OpenAI-compatible
   endpoint) - the native API won't work.

3. Install the permission-scoped agents. Copy this folder's `.opencode/agent/`
   into your project (or global config dir). pip-readonly DENIES edit+bash, so
   even with --auto it physically cannot write or run - that's the safe default.
   pip-build allows edits but only inside the --dir Pip gives it.

4. Verify headless output actually works (the test Antigravity's earlier run
   missed because it hit the GUI exe):
       opencode run --format json --agent pip-readonly --dir . "list the files here"
   You should get JSON on stdout and NO new window. If you do -> it works.

5. Enable in Pip: set `cmd_bin` in ../personas/opencode.json to the CLI's path
   (just "opencode" if it's on PATH), then do the execute_opencode dispatch
   from brief 2026-07-08_pip_opencode_dispatch.md.

## What Pip gets
- Free, offline coding agent (Ollama local, no API keys).
- Read-only planning by default (captured JSON she summarizes to your phone).
- Scoped build mode behind approval + a confined --dir.

## Flag reference (corrected)
- JSON output:  --format json   (NOT -f json; -f/--file attaches files)
- No --mode flag on `run`; safety = a permission-scoped --agent.
- --auto auto-approves permissions (build only); --dir confines the workspace.
