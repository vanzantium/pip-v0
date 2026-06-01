#!/usr/bin/env python3
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pip_config


RUN_VERSION = 1
RUN_FILENAME = "pip_task_runs.jsonl"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def run_path() -> Path:
    return pip_config.get_memory_path() / RUN_FILENAME


def _json_safe(value: Any) -> Any:
    try:
        json.dumps(value)
        return value
    except TypeError:
        if isinstance(value, dict):
            return {str(key): _json_safe(item) for key, item in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [_json_safe(item) for item in value]
        return str(value)


def record_task_run(
    kind: str,
    name: str,
    status: str,
    run_id: str | None = None,
    summary: str = "",
    permission_id: str = "",
    source: str = "pip",
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    path = run_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    event = {
        "version": RUN_VERSION,
        "id": run_id or f"taskrun_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}",
        "at": utc_now(),
        "kind": kind or "task",
        "name": name or "task",
        "status": status or "unknown",
        "summary": summary or "",
        "permission_id": permission_id or "",
        "source": source or "pip",
        "details": _json_safe(details or {}),
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, sort_keys=True) + "\n")
    try:
        import pip_traces

        pip_traces.record_trace(
            kind="task_run",
            actor="pip",
            action=name or kind or "task",
            status=status or "unknown",
            summary=summary or f"{kind} {status}",
            details={
                "task_run_id": event["id"],
                "permission_id": event["permission_id"],
                **event["details"],
            },
            source=source or "pip_task_runs",
            tags=["task_run", kind or "task"],
        )
    except Exception:
        pass
    return event


def start_task_run(
    kind: str,
    name: str,
    summary: str = "",
    permission_id: str = "",
    source: str = "pip",
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return record_task_run(
        kind,
        name,
        "started",
        summary=summary,
        permission_id=permission_id,
        source=source,
        details=details,
    )


def finish_task_run(
    run_id: str,
    kind: str,
    name: str,
    status: str,
    summary: str = "",
    permission_id: str = "",
    source: str = "pip",
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return record_task_run(
        kind,
        name,
        status,
        run_id=run_id,
        summary=summary,
        permission_id=permission_id,
        source=source,
        details=details,
    )


def _load_events(path: Path) -> tuple[list[dict[str, Any]], int]:
    if not path.exists():
        return [], 0
    events: list[dict[str, Any]] = []
    skipped = 0
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            parsed = json.loads(line)
            if isinstance(parsed, dict):
                events.append(parsed)
            else:
                skipped += 1
        except json.JSONDecodeError:
            skipped += 1
    return events, skipped


def inspect_task_runs(limit: int = 20, kind: str | None = None, status: str | None = None) -> dict[str, Any]:
    path = run_path()
    events, skipped = _load_events(path)
    filtered = events
    if kind:
        filtered = [event for event in filtered if event.get("kind") == kind]
    if status:
        filtered = [event for event in filtered if event.get("status") == status]
    by_kind: dict[str, int] = {}
    by_status: dict[str, int] = {}
    for event in events:
        by_kind[event.get("kind", "task")] = by_kind.get(event.get("kind", "task"), 0) + 1
        by_status[event.get("status", "unknown")] = by_status.get(event.get("status", "unknown"), 0) + 1
    return {
        "generated_at": utc_now(),
        "task_runs_path": str(path),
        "exists": path.exists(),
        "total_events": len(events),
        "matching_events": len(filtered),
        "skipped_lines": skipped,
        "by_kind": by_kind,
        "by_status": by_status,
        "latest": filtered[-max(1, int(limit)) :],
        "append_only": True,
    }
