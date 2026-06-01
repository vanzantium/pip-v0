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
        task_run = None
        try:
            import pip_task_runs

            task_run = pip_task_runs.start_task_run(
                "efficiency_script",
                script_name,
                summary="Starting silent efficiency script.",
                source="pip_background_tasks",
                details={"path": str(p), "silent": True},
            )
            subprocess.Popen(
                [sys.executable, str(p)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                **pip_platform.hidden_subprocess_kwargs(),
            )
            if task_run:
                pip_task_runs.finish_task_run(
                    task_run["id"],
                    "efficiency_script",
                    script_name,
                    "launched",
                    summary="Silent script launched; completion is not tracked.",
                    source="pip_background_tasks",
                    details={"path": str(p), "silent": True},
                )
            return {"ok": True, "message": f"Started {script_name} silently."}
        except Exception as e:
            if task_run:
                try:
                    import pip_task_runs

                    pip_task_runs.finish_task_run(
                        task_run["id"],
                        "efficiency_script",
                        script_name,
                        "failed",
                        summary=str(e),
                        source="pip_background_tasks",
                        details={"path": str(p), "silent": True},
                    )
                except Exception:
                    pass
            return {"ok": False, "message": f"Failed to start: {e}"}
    else:
        # Run tracked via pip_jobs
        def runner(job_id: str) -> str:
            task_run = None
            try:
                import pip_task_runs

                task_run = pip_task_runs.start_task_run(
                    "efficiency_script",
                    script_name,
                    summary="Starting tracked efficiency script.",
                    source="pip_background_tasks",
                    details={"path": str(p), "silent": False, "job_id": job_id},
                )
            except Exception:
                pass
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
                    if task_run:
                        try:
                            import pip_task_runs

                            pip_task_runs.finish_task_run(
                                task_run["id"],
                                "efficiency_script",
                                script_name,
                                "stopped",
                                summary="Stopped by user.",
                                source="pip_background_tasks",
                                details={"path": str(p), "job_id": job_id},
                            )
                        except Exception:
                            pass
                    return "Stopped by user."
                line = proc.stdout.readline()
                if not line and proc.poll() is not None:
                    break
                if line:
                    pip_jobs.append_log(job_id, line.rstrip())
            rc = proc.wait()
            if task_run:
                try:
                    import pip_task_runs

                    pip_task_runs.finish_task_run(
                        task_run["id"],
                        "efficiency_script",
                        script_name,
                        "completed" if rc == 0 else "failed",
                        summary=f"Completed with exit code {rc}",
                        source="pip_background_tasks",
                        details={"path": str(p), "job_id": job_id, "exit_code": rc},
                    )
                except Exception:
                    pass
            return f"Completed with exit code {rc}"

        job = pip_jobs.start_job(
            kind="efficiency_script",
            title=f"Running {script_name}",
            target=runner,
            details={"script": script_name, "path": str(p)},
        )
        return {"ok": True, "job": job, "message": f"Started {script_name} tracked."}
