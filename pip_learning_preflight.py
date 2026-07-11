#!/usr/bin/env python3
"""
pip_learning_preflight.py - one-shot health check for Pip's automated learning path.

Answers "is she actually wired to start digesting the brain?" by checking every
link in the chain and printing GREEN/RED per item. Read-only: it inspects, it
never changes anything. Run it on the machine where Pip lives (the opencode
check needs her PATH).

    python pip_learning_preflight.py

Chain checked:
  nightwatch -> Night School -> reads_codex build -> mastery.next
  -> opencode(pip-readonly, local model) -> notes -> ingest
  -> @CLAUDE handoff -> Claude's 8am/6pm shift ; plus GitHub scout.
"""
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
try:
    import pip_platform
    BRAIN = pip_platform.BRAIN_ROOT
except Exception:
    BRAIN = HERE.parent.parent.parent.parent

READS = BRAIN / "08_reads_pdfs"
HANDOFFS = BRAIN / "01_agent_context" / "handoffs"
MASTERY_DIR = BRAIN / "02_pip_and_system_architecture" / "builds" / "reads_mastery"

RED, GREEN, YEL, RST = "\033[91m", "\033[92m", "\033[93m", "\033[0m"
rows = []


def check(name, ok, detail="", warn=False):
    tag = f"{YEL}WARN{RST}" if warn else (f"{GREEN} OK {RST}" if ok else f"{RED}FAIL{RST}")
    rows.append((ok or warn, warn))
    print(f"[{tag}] {name}" + (f" - {detail}" if detail else ""))


def main():
    print("=== Pip learning-path preflight ===\n")

    # 1. opencode CLI resolvable
    oc = shutil.which("opencode.cmd")
    if not oc and sys.platform != "win32":
        oc = shutil.which("opencode")
    check("opencode CLI on PATH", bool(oc), oc or "not found - Night School notes will be empty")

    # 2. opencode agents installed where opencode looks
    agent_locs = [HERE / ".opencode" / "agent",
                  Path.home() / ".config" / "opencode" / "agent",
                  HERE / "opencode_setup" / ".opencode" / "agent"]
    ro = next((p / "pip-readonly.md" for p in agent_locs if (p / "pip-readonly.md").exists()), None)
    installed = ro is not None and ro.parent != (HERE / "opencode_setup" / ".opencode" / "agent")
    check("pip-readonly agent installed", installed,
          str(ro) if ro else "only the template copy exists - copy .opencode/agent into the run dir or ~/.config/opencode",
          warn=(ro is not None and not installed))

    # 3. live ollama native engine smoke
    if True:
        try:
            import urllib.request
            import json
            req = urllib.request.Request("http://127.0.0.1:11434/api/generate", headers={'Content-Type': 'application/json'}, method="POST")
            data = json.dumps({"model": "qwen2.5-coder:7b", "prompt": "say READY", "stream": False}).encode("utf-8")
            with urllib.request.urlopen(req, data=data, timeout=30) as response:
                resp_data = json.loads(response.read().decode("utf-8"))
                ok = bool(resp_data.get("response"))
                check("ollama native engine run", ok, "returned output" if ok else "empty/failed")
        except Exception as e:
            check("ollama native engine run", False, str(e)[:120])

    # 4. learning scripts import
    sys.path.insert(0, str(MASTERY_DIR))
    try:
        import reads_codex, mastery  # noqa
        check("reads_codex + mastery import", True)
    except Exception as e:
        check("reads_codex + mastery import", False, str(e)[:120])

    # 5. corpus indexed yet?
    codex = READS / "_codex" / "manifest.json"
    if codex.exists():
        man = json.loads(codex.read_text(encoding="utf-8"))
        text_pages = sum(e.get("pages_with_text", 0) for e in man.values())
        no_text = [e.get("short", k) for k, e in man.items() if e.get("pages_with_text", 0) == 0]
        check("reads codex built", True, f"{len(man)} sources, {text_pages} text pages")
        if no_text:
            check("scanned PDFs need OCR", False, ", ".join(no_text[:4]), warn=True)
    else:
        pdfs = len(list(READS.rglob("*.pdf")))
        check("reads codex built", False, f"never run - {pdfs} PDFs waiting (first Night School builds it)", warn=True)

    # 6. mastery progress
    mroot = READS / "_mastery"
    advanced = len(list(mroot.glob("*/state.json"))) if mroot.exists() else 0
    check("books on the mastery ladder", advanced > 0, f"{advanced} started", warn=(advanced == 0))

    # 7. handoff queue writable + Claude intake present
    check("handoffs dir writable", os.access(HANDOFFS, os.W_OK) if HANDOFFS.exists() else False,
          str(HANDOFFS))
    check("Claude intake present", (HANDOFFS / "handoff_intake.py").exists())

    # 8. GitHub token
    try:
        import pip_github_scout
        check("GitHub scout token", bool(pip_github_scout.get_token()),
              "present" if pip_github_scout.get_token() else "none (runs unauthenticated)",
              warn=not pip_github_scout.get_token())
    except Exception as e:
        check("GitHub scout token", False, str(e)[:80])

    # 9. did the loops actually fire recently?
    try:
        import pip_config
        mem = pip_config.get_memory_path()
    except Exception:
        mem = HERE / "PipMemory"
    for label, fn in [("Night School", "last_night_school.txt"), ("GitHub scout", "last_github_scout.txt")]:
        f = Path(mem) / fn
        stamp = f.read_text(encoding="utf-8").strip() if f.exists() else None
        today = datetime.now().strftime("%Y-%m-%d")
        check(f"{label} ran", stamp == today, stamp or "never", warn=(stamp is not None and stamp != today))

    # summary
    fails = sum(1 for ok, warn in rows if not ok)
    warns = sum(1 for ok, warn in rows if warn)
    print("\n=== summary ===")
    if fails == 0 and warns == 0:
        print(f"{GREEN}Ready to learn - every link is green.{RST}")
    elif fails == 0:
        print(f"{YEL}Runnable, with {warns} warning(s) to improve quality/coverage.{RST}")
    else:
        print(f"{RED}{fails} blocker(s) + {warns} warning(s) - fix blockers before she can digest.{RST}")


if __name__ == "__main__":
    main()
