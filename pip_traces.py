#!/usr/bin/env python3
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pip_config


TRACE_VERSION = 1
TRACE_FILENAME = "pip_traces.jsonl"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def trace_path() -> Path:
    return pip_config.get_memory_path() / TRACE_FILENAME


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


def record_trace(
    kind: str,
    actor: str = "pip",
    action: str = "",
    status: str = "ok",
    summary: str = "",
    details: dict[str, Any] | None = None,
    source: str = "pip",
    workspace: str = "",
    tags: list[str] | None = None,
) -> dict[str, Any]:
    """Append one durable trace event without mutating older records."""
    path = trace_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    event = {
        "version": TRACE_VERSION,
        "id": f"trace_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}",
        "at": utc_now(),
        "kind": kind or "event",
        "actor": actor or "pip",
        "action": action or "",
        "status": status or "ok",
        "summary": summary or "",
        "details": _json_safe(details or {}),
        "source": source or "pip",
        "workspace": workspace or "",
        "tags": tags or [],
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, sort_keys=True) + "\n")
    return event


def _load_lines(path: Path) -> tuple[list[dict[str, Any]], int]:
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


def read_traces(limit: int = 50, kind: str | None = None, status: str | None = None) -> list[dict[str, Any]]:
    events, _ = _load_lines(trace_path())
    if kind:
        events = [event for event in events if event.get("kind") == kind]
    if status:
        events = [event for event in events if event.get("status") == status]
    return events[-max(1, int(limit)) :]


def inspect_traces(limit: int = 20, kind: str | None = None, status: str | None = None) -> dict[str, Any]:
    path = trace_path()
    events, skipped = _load_lines(path)
    filtered = events
    if kind:
        filtered = [event for event in filtered if event.get("kind") == kind]
    if status:
        filtered = [event for event in filtered if event.get("status") == status]
    by_kind: dict[str, int] = {}
    by_status: dict[str, int] = {}
    for event in events:
        by_kind[event.get("kind", "event")] = by_kind.get(event.get("kind", "event"), 0) + 1
        by_status[event.get("status", "unknown")] = by_status.get(event.get("status", "unknown"), 0) + 1
    return {
        "generated_at": utc_now(),
        "trace_path": str(path),
        "exists": path.exists(),
        "total_events": len(events),
        "matching_events": len(filtered),
        "skipped_lines": skipped,
        "by_kind": by_kind,
        "by_status": by_status,
        "latest": filtered[-max(1, int(limit)) :],
        "append_only": True,
    }
