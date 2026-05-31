#!/usr/bin/env python3
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pip_config

def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

def scheduler_path() -> Path:
    return pip_config.get_memory_path() / "pip_scheduler.json"

def _load_jobs() -> list[dict[str, Any]]:
    path = scheduler_path()
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data.get("jobs", [])
        return data if isinstance(data, list) else []
    except Exception:
        return []

def _save_jobs(jobs: list[dict[str, Any]]):
    path = scheduler_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {"jobs": jobs, "updated_at": _utc_now()}
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")

def add_job(name: str, goal: str, schedule_type: str = "once", scope: str = "global") -> dict[str, Any]:
    jobs = _load_jobs()
    new_job = {
        "id": f"job_{uuid.uuid4().hex[:8]}",
        "name": name,
        "goal": goal,
        "schedule_type": schedule_type,
        "scope": scope,
        "status": "pending",  # pending, paused, completed, failed
        "created_at": _utc_now(),
        "last_run": None,
        "last_result": None,
    }
    jobs.append(new_job)
    _save_jobs(jobs)
    return new_job

def pause_job(job_id: str) -> bool:
    jobs = _load_jobs()
    for job in jobs:
        if job["id"] == job_id:
            job["status"] = "paused"
            _save_jobs(jobs)
            return True
    return False

def resume_job(job_id: str) -> bool:
    jobs = _load_jobs()
    for job in jobs:
        if job["id"] == job_id:
            job["status"] = "pending"
            _save_jobs(jobs)
            return True
    return False

def complete_job(job_id: str, result: str) -> bool:
    jobs = _load_jobs()
    for job in jobs:
        if job["id"] == job_id:
            job["status"] = "completed"
            job["last_run"] = _utc_now()
            job["last_result"] = result
            _save_jobs(jobs)
            return True
    return False

def get_status() -> dict[str, Any]:
    return {
        "jobs": _load_jobs(),
        "updated_at": _utc_now()
    }
