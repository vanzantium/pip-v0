#!/usr/bin/env python3
"""
pip_task_monitor.py - process inventory, research watchdog, and waste report.

Contract (matches the root AGENTS.md safety posture):
  - AUTO-ACTION is allowed ONLY on Pip's own research child (the PID she
    recorded in imports/_research_status.json). Nothing else is ever killed.
  - Everything else is DRAFT-FIRST: the waste report is written to
    imports/_task_monitor_report.json and printed; a human (or a reviewed
    proposal flow) decides what to do about it.
  - Every watchdog action is recorded via pip_traces.

Used by pip_personas.execute_deep_research (dedupe + stale-status cleanup)
and runnable standalone:

    python pip_task_monitor.py watchdog     # check/repair research status
    python pip_task_monitor.py inventory    # python/ollama processes
    python pip_task_monitor.py report       # waste report (draft-first)
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
STATUS_FILE = ROOT / "imports" / "_research_status.json"
REPORT_FILE = ROOT / "imports" / "_task_monitor_report.json"

STALE_NO_PID_MIN = 20      # legacy "running" with no PID older than this -> reset
RUNAWAY_MIN = 45           # own research child alive longer than this -> terminate

try:
    import psutil  # optional; everything degrades without it
    _PSUTIL = True
except ImportError:
    _PSUTIL = False


def _trace(action: str, status: str, details: dict[str, Any]) -> None:
    try:
        import pip_traces
        pip_traces.record_trace(kind="task_monitor", action=action, status=status,
                                summary=action, details=details)
    except Exception:
        pass


# -- pid helpers --------------------------------------------------------------

def pid_alive(pid: int) -> bool:
    if not pid:
        return False
    if _PSUTIL:
        return psutil.pid_exists(pid)
    if os.name == "nt":
        try:
            out = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                capture_output=True, text=True, timeout=10)
            return str(pid) in (out.stdout or "")
        except Exception:
            return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def terminate_pid(pid: int) -> bool:
    """Terminate a process. ONLY ever called on Pip's own research child."""
    try:
        if _PSUTIL:
            psutil.Process(pid).terminate()
            return True
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                           capture_output=True, timeout=10)
            return True
        os.kill(pid, 15)
        return True
    except Exception:
        return False


# -- research watchdog ---------------------------------------------------------

def read_status() -> dict[str, Any]:
    try:
        return json.loads(STATUS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"status": "idle"}


def _reset_idle() -> None:
    try:
        STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATUS_FILE.write_text(json.dumps({"status": "idle"}), encoding="utf-8")
    except Exception:
        pass


def research_watchdog(notify: bool = True) -> str:
    """Returns one of: idle | healthy | reset_dead | reset_stale | terminated_runaway."""
    st = read_status()
    if st.get("status") != "running":
        return "idle"
    age_min = (time.time() - float(st.get("start_time", 0) or 0)) / 60
    pid = int(st.get("pid", 0) or 0)

    if not pid:
        if age_min > STALE_NO_PID_MIN:
            _reset_idle()
            _trace("reset_stale", "ok",
                   {"reason": "running with no pid", "age_min": round(age_min, 1),
                    "topic": st.get("topic", "")})
            return "reset_stale"
        return "healthy"

    if not pid_alive(pid):
        _reset_idle()
        _trace("reset_dead", "ok",
               {"pid": pid, "age_min": round(age_min, 1), "topic": st.get("topic", "")})
        return "reset_dead"

    if age_min > RUNAWAY_MIN:
        ok = terminate_pid(pid)
        _reset_idle()
        _trace("terminated_runaway", "ok",
               {"pid": pid, "age_min": round(age_min, 1),
                "topic": st.get("topic", ""), "terminated": ok})
        if notify:
            try:
                import pip_notify
                pip_notify.notify(
                    f"I stopped a research run on '{st.get('topic', '?')}' that had "
                    f"been going {age_min:.0f} minutes. Status reset - you can ask again.",
                    "Task Monitor")
            except Exception:
                pass
        return "terminated_runaway"

    return "healthy"


def research_is_busy() -> bool:
    """True only if research is genuinely running (live PID). Repairs stale
    state as a side effect - callers can trust the answer."""
    verdict = research_watchdog(notify=False)
    return verdict == "healthy" and read_status().get("status") == "running"


# -- inventory + waste report (draft-first) ------------------------------------

def inventory() -> list[dict[str, Any]]:
    procs: list[dict[str, Any]] = []
    if _PSUTIL:
        for p in psutil.process_iter(["pid", "name", "memory_info", "cmdline", "create_time"]):
            try:
                name = (p.info["name"] or "").lower()
                if not any(k in name for k in ("python", "ollama")):
                    continue
                procs.append({
                    "pid": p.info["pid"],
                    "name": p.info["name"],
                    "mem_mb": round((p.info["memory_info"].rss if p.info["memory_info"] else 0) / 1e6),
                    "cmd": " ".join(p.info["cmdline"] or [])[:160],
                    "age_min": round((time.time() - (p.info["create_time"] or time.time())) / 60),
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return procs
    # fallback: name/pid/mem only
    try:
        if os.name == "nt":
            out = subprocess.run(["tasklist", "/FO", "CSV", "/NH"],
                                 capture_output=True, text=True, timeout=15).stdout
            for line in out.splitlines():
                parts = [c.strip('"') for c in line.split('","')]
                if len(parts) >= 5 and any(k in parts[0].lower() for k in ("python", "ollama")):
                    procs.append({"pid": int(parts[1]), "name": parts[0],
                                  "mem_mb": parts[4], "cmd": "", "age_min": None})
        else:
            out = subprocess.run(["ps", "-eo", "pid,rss,comm,args"],
                                 capture_output=True, text=True, timeout=15).stdout
            for line in out.splitlines()[1:]:
                bits = line.split(None, 3)
                if len(bits) >= 3 and any(k in bits[2].lower() for k in ("python", "ollama")):
                    procs.append({"pid": int(bits[0]), "name": bits[2],
                                  "mem_mb": round(int(bits[1]) / 1000),
                                  "cmd": (bits[3] if len(bits) > 3 else "")[:160],
                                  "age_min": None})
    except Exception:
        pass
    return procs


def waste_report() -> dict[str, Any]:
    procs = inventory()
    findings = []
    ollama_serves = [p for p in procs if "ollama" in str(p["name"]).lower()]
    if len(ollama_serves) > 2:
        findings.append(f"{len(ollama_serves)} ollama processes - possible duplicate servers")
    research = [p for p in procs if "pip_deep_research" in str(p.get("cmd", ""))]
    if len(research) > 1:
        findings.append(f"{len(research)} parallel deep-research processes - contention "
                        f"(pids: {[p['pid'] for p in research]})")
    st = read_status()
    if st.get("status") == "running" and not research and st.get("pid"):
        findings.append("status says running but no research process visible - stale status")
    report = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "watchdog": research_watchdog(notify=False),
        "process_count": len(procs),
        "findings": findings or ["no waste detected"],
        "processes": sorted(procs, key=lambda p: -(p["mem_mb"] if isinstance(p["mem_mb"], int) else 0))[:10],
        "note": "draft-first: this report proposes; it never acts on non-Pip processes",
    }
    try:
        REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
        REPORT_FILE.write_text(json.dumps(report, indent=2), encoding="utf-8")
    except Exception:
        pass
    return report


# -- offloading telemetry report -----------------------------------------------

def offloading_report() -> None:
    try:
        import pip_traces
        events = pip_traces.read_traces(limit=1000, kind="learning_hub_offload")
    except Exception as e:
        print(f"Failed to load traces: {e}")
        return

    if not events:
        print("No offloading traces found.")
        return

    total_bytes = 0
    total_cft = 0.0
    valid_cft_count = 0
    
    for e in events:
        d = e.get("details", {})
        total_bytes += int(d.get("bytes", 0))
        cft = d.get("cft_score")
        if cft is not None:
            total_cft += float(cft)
            valid_cft_count += 1
            
    synthetic_tokens = total_bytes // 4
    avg_cft = (total_cft / valid_cft_count) if valid_cft_count > 0 else 0.0
    
    print("\n--- DEEP OFFLOADING METRICS ---")
    print(f"Total Offload Events : {len(events)}")
    print(f"Total Bytes Saved    : {total_bytes}")
    print(f"Tokens Saved (Est)   : {synthetic_tokens}")
    print(f"Avg Correct Thinking : {avg_cft:.3f} (CFT Composite)")
    print("-------------------------------\n")


def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "watchdog"
    if cmd == "watchdog":
        print(f"watchdog verdict: {research_watchdog()}")
    elif cmd == "inventory":
        for p in inventory():
            print(f"  pid {p['pid']:<8} {p['name']:<18} {p['mem_mb']}MB  {p.get('cmd', '')[:80]}")
    elif cmd == "report":
        r = waste_report()
        print(json.dumps({k: v for k, v in r.items() if k != "processes"}, indent=2))
        print(f"full report: {REPORT_FILE}")
    elif cmd == "offloading":
        offloading_report()
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
