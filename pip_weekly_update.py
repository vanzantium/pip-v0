#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pip_config
import pip_repo_watch


FILENAME = "weekly_update_status.json"
DEFAULT_POLICY = {
    "mode": "opt_in_industry_watch",
    "purpose": "Track proven ideas from watched public repos and draft audited update suggestions for Pip.",
    "default_enabled": False,
    "allowed_actions": [
        "read public GitHub metadata",
        "draft update suggestions",
        "prefer recurring/proven concepts over one-off hype",
        "require audit before implementation",
    ],
    "blocked_actions": [
        "install dependencies",
        "clone repositories automatically",
        "modify Pip code automatically",
        "open PRs or push changes",
        "expand permissions without explicit user approval",
    ],
    "audit_questions": [
        "Is this concept proven across more than one project or release?",
        "Does it fit Pip's draft-first safety contract?",
        "Can it be implemented as a small reversible skill or memory rule?",
        "What permission boundary could this weaken?",
        "What test or doctor check would prove it works safely?",
    ],
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def status_path() -> Path:
    return pip_config.get_memory_path() / FILENAME


def _read_status() -> dict[str, Any]:
    path = status_path()
    if not path.exists():
        return {
            "generated_at": utc_now(),
            "enabled": False,
            "cadence": "weekly",
            "last_run_at": None,
            "latest_repo_watch": None,
            "policy": DEFAULT_POLICY,
        }
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    data.setdefault("enabled", False)
    data.setdefault("cadence", "weekly")
    data.setdefault("last_run_at", None)
    data.setdefault("latest_repo_watch", None)
    data.setdefault("policy", DEFAULT_POLICY)
    data["generated_at"] = utc_now()
    return data


def _write_status(status: dict[str, Any]) -> dict[str, Any]:
    path = status_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    status["generated_at"] = utc_now()
    path.write_text(json.dumps(status, indent=2), encoding="utf-8")
    return status


def inspect_weekly_update() -> dict[str, Any]:
    status = _read_status()
    status["repo_watch"] = pip_repo_watch.get_repo_watch_status()
    return status


def enable_weekly_update(queue_scheduler: bool = True) -> dict[str, Any]:
    status = _read_status()
    status["enabled"] = True
    status["enabled_at"] = utc_now()
    status["policy"] = DEFAULT_POLICY
    if queue_scheduler:
        import pip_scheduler

        job = pip_scheduler.add_job(
            "Weekly Update Watch",
            "Run Pip's opt-in weekly update watch and draft audited system-improvement suggestions.",
            schedule_type="weekly",
            scope="weekly_update",
        )
        status["scheduler_job"] = job
    return _write_status(status)


def disable_weekly_update() -> dict[str, Any]:
    status = _read_status()
    status["enabled"] = False
    status["disabled_at"] = utc_now()
    job = status.get("scheduler_job") or {}
    job_id = job.get("id")
    if job_id:
        try:
            import pip_scheduler

            status["scheduler_paused"] = pip_scheduler.pause_job(job_id)
        except Exception as exc:
            status["scheduler_pause_error"] = str(exc)
    return _write_status(status)


def run_weekly_update(force: bool = True) -> dict[str, Any]:
    status = _read_status()
    if not status.get("enabled") and not force:
        status["skipped"] = True
        status["message"] = "Weekly Update is disabled. Enable it or run with force for a manual scan."
        return status
    repo_status = pip_repo_watch.scan_repo_watch(force=force)
    status["last_run_at"] = utc_now()
    status["latest_repo_watch"] = repo_status.get("latest_report")
    status["latest_proposal"] = (repo_status.get("proposal") or {}).get("proposal_card")
    status["policy"] = DEFAULT_POLICY
    status["repo_watch"] = repo_status
    return _write_status(status)
