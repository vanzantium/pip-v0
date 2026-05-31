#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

import pip_platform
import pip_jobs

def scripts_dir() -> Path:
    d = Path(__file__).resolve().parent / "scripts"
    d.mkdir(parents=True, exist_ok=True)
    return d

def list_scripts() -> list[dict[str, Any]]:
    scripts = []
    d = scripts_dir()
    for p in d.glob("*.py"):
        scripts.append({
            "name": p.name,
            "path": str(p),
        })
    scripts.sort(key=lambda s: s["name"].lower())
    return scripts

def run_script(script_name: str, silent: bool = False) -> dict[str, Any]:
    p = scripts_dir() / script_name
    if not p.exists() or p.suffix != ".py":
        return {"ok": False, "message": f"Script not found: {script_name}"}

    if silent:
        # Run completely detached
        try:
            subprocess.Popen(
                [sys.executable, str(p)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                **pip_platform.hidden_subprocess_kwargs(),
            )
            return {"ok": True, "message": f"Started {script_name} silently."}
        except Exception as e:
            return {"ok": False, "message": f"Failed to start: {e}"}
    else:
        # Run tracked via pip_jobs
        def runner(job_id: str) -> str:
            proc = subprocess.Popen(
                [sys.executable, str(p)],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                **pip_platform.hidden_subprocess_kwargs(),
            )
            while True:
                if pip_jobs.should_stop(job_id):
                    proc.terminate()
                    return "Stopped by user."
                line = proc.stdout.readline()
                if not line and proc.poll() is not None:
                    break
                if line:
                    pip_jobs.append_log(job_id, line.rstrip())
            rc = proc.wait()
            return f"Completed with exit code {rc}"

        job = pip_jobs.start_job(
            kind="efficiency_script",
            title=f"Running {script_name}",
            target=runner,
            details={"script": script_name, "path": str(p)},
        )
        return {"ok": True, "job": job, "message": f"Started {script_name} tracked."}
