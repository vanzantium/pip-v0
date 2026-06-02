#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pip_config


VALID_PRIORITIES = {"critical", "high", "normal", "low"}
VALID_SOURCES = {"user_explicit", "post_run", "programmatic", "review"}
PRIORITY_RANK = {"critical": 0, "high": 1, "normal": 2, "low": 3}
FILENAME = "tool_memory_rules.json"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def memory_path() -> Path:
    return pip_config.get_memory_path() / FILENAME


def _empty_store() -> dict[str, Any]:
    return {"version": 1, "rules": []}


def load_store() -> dict[str, Any]:
    path = memory_path()
    if not path.exists():
        return _empty_store()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return _empty_store()
    if not isinstance(data, dict):
        return _empty_store()
    data.setdefault("version", 1)
    data.setdefault("rules", [])
    if not isinstance(data["rules"], list):
        data["rules"] = []
    return data


def save_store(store: dict[str, Any]) -> None:
    path = memory_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(store, indent=2), encoding="utf-8")


def normalize_tool_name(tool_name: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "_" for ch in (tool_name or "general").strip())
    while "__" in cleaned:
        cleaned = cleaned.replace("__", "_")
    return cleaned.strip("_") or "general"


def _rule_id(tool_name: str, rule: str) -> str:
    digest = hashlib.sha1(f"{normalize_tool_name(tool_name)}\n{rule.strip()}".encode("utf-8")).hexdigest()
    return f"tm_{digest[:12]}"


def put_rule(
    tool_name: str,
    rule: str,
    priority: str = "normal",
    source: str = "user_explicit",
    tags: list[str] | None = None,
) -> dict[str, Any]:
    cleaned_rule = (rule or "").strip()
    if not cleaned_rule:
        raise ValueError("rule must be non-empty")
    cleaned_tool = normalize_tool_name(tool_name)
    cleaned_priority = (priority or "normal").lower()
    if cleaned_priority not in VALID_PRIORITIES:
        raise ValueError(f"priority must be one of: {', '.join(sorted(VALID_PRIORITIES))}")
    cleaned_source = (source or "user_explicit").lower()
    if cleaned_source not in VALID_SOURCES:
        cleaned_source = "user_explicit"
    cleaned_tags = sorted({tag.strip().lower() for tag in (tags or []) if tag and tag.strip()})
    now = utc_now()
    store = load_store()
    rid = _rule_id(cleaned_tool, cleaned_rule)

    for item in store["rules"]:
        if item.get("id") == rid:
            item.update({
                "tool_name": cleaned_tool,
                "rule": cleaned_rule,
                "priority": cleaned_priority,
                "source": cleaned_source,
                "tags": cleaned_tags,
                "updated_at": now,
            })
            save_store(store)
            return {"stored": item, "created": False, "path": str(memory_path())}

    item = {
        "id": rid,
        "tool_name": cleaned_tool,
        "rule": cleaned_rule,
        "priority": cleaned_priority,
        "source": cleaned_source,
        "tags": cleaned_tags,
        "created_at": now,
        "updated_at": now,
    }
    store["rules"].append(item)
    save_store(store)
    return {"stored": item, "created": True, "path": str(memory_path())}


def list_rules(tool_name: str | None = None, limit: int | None = None) -> list[dict[str, Any]]:
    cleaned_tool = normalize_tool_name(tool_name) if tool_name else None
    rules = [
        item for item in load_store().get("rules", [])
        if isinstance(item, dict) and (not cleaned_tool or item.get("tool_name") == cleaned_tool)
    ]
    rules.sort(key=lambda item: (PRIORITY_RANK.get(item.get("priority", "normal"), 9), item.get("tool_name", ""), item.get("rule", "")))
    if limit is not None:
        return rules[: max(0, int(limit))]
    return rules


def inspect_tool_rules(tool_name: str | None = None, limit: int = 20) -> dict[str, Any]:
    rules = list_rules(tool_name=tool_name, limit=limit)
    by_priority: dict[str, int] = {}
    for item in rules:
        priority = item.get("priority", "normal")
        by_priority[priority] = by_priority.get(priority, 0) + 1
    return {
        "generated_at": utc_now(),
        "path": str(memory_path()),
        "tool_name": normalize_tool_name(tool_name) if tool_name else None,
        "count": len(rules),
        "by_priority": by_priority,
        "rules": rules,
    }


def rules_for_prompt(tool_name: str | None = None, limit: int = 12) -> dict[str, Any]:
    rules = [
        item for item in list_rules(tool_name=tool_name)
        if item.get("priority") in {"critical", "high"}
    ][:limit]
    lines = ["Tool Memory Boundary:"]
    if not rules:
        lines.append("- No critical or high-priority tool rules are stored.")
    for item in rules:
        lines.append(f"- [{item.get('priority')}] {item.get('tool_name')}: {item.get('rule')}")
    return {"rules": rules, "prompt_block": "\n".join(lines)}
