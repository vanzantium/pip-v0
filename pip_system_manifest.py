#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pip_config
import pip_platform


MANIFEST_VERSION = 1
MANIFEST_FILENAME = "pip_system_manifest.json"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def manifest_path() -> Path:
    return pip_config.get_memory_path() / MANIFEST_FILENAME


def _file_state(name: str) -> dict[str, Any]:
    path = pip_platform.ROOT / name
    return {
        "name": name,
        "path": str(path),
        "exists": path.exists(),
    }


def _developer_shell_summary() -> dict[str, Any]:
    try:
        import pip_app_skills

        result = pip_app_skills.inspect_developer_shells()
        shells = result.get("shells", [])
        return {
            "count": len(shells),
            "names": [shell.get("name") for shell in shells],
            "safety_modes": {
                shell.get("name", "unknown"): shell.get("safety_mode", "")
                for shell in shells
            },
        }
    except Exception as exc:
        return {"count": 0, "names": [], "error": str(exc)}


def build_manifest() -> dict[str, Any]:
    platform_status = pip_platform.feature_status()
    memory_path = pip_config.get_memory_path()
    return {
        "version": MANIFEST_VERSION,
        "generated_at": utc_now(),
        "name": "Pip v0 Local Hybrid Agent",
        "purpose": "A supervised local assistant that scans approved workspaces, condenses memory, proposes next actions, and waits for user approval before higher-risk action.",
        "roots": {
            "pip_root": str(pip_platform.ROOT),
            "brain_root": str(pip_platform.BRAIN_ROOT),
            "memory_root": str(memory_path),
        },
        "platform": platform_status,
        "safety_contract": {
            "default_mode": "draft_only",
            "approval_required_for": [
                "original file edits",
                "UI automation",
                "arbitrary Python execution",
                "keyboard or macro recording",
                "autonomous long-running goals",
                "external messaging or app actions",
            ],
            "safe_without_extra_approval": [
                "read approved workspaces",
                "write Pip memory files",
                "write approved draft folders",
                "render local dashboard",
                "record append-only traces",
            ],
        },
        "primitives": {
            "skills": {
                "description": "CLI-addressable abilities with explicit input/output/permission metadata.",
                "files": [_file_state("pip_skills.py")],
            },
            "portable_skills": {
                "description": "Manifest-listed skill bundles from skills/ with lazy trusted-package loading.",
                "files": [_file_state("pip_skill_registry.py"), _file_state("skills")],
            },
            "dox_context_tree": {
                "description": "Builder-facing hierarchical AGENTS.md contracts for project-wide and path-local coding guidance.",
                "files": [
                    _file_state("AGENTS.md"),
                    _file_state("pip_dox.py"),
                    _file_state("dashboard_ui/AGENTS.md"),
                    _file_state("imports/AGENTS.md"),
                    _file_state("scenarios/AGENTS.md"),
                    _file_state("skills/AGENTS.md"),
                ],
            },
            "workspace_loop": {
                "description": "Approved-folder scanner, condenser, proposal writer, ambient cycle, and permission queue.",
                "files": [_file_state("pip_workspace.py"), _file_state("approved_workspaces.json")],
            },
            "control_panel": {
                "description": "Local LAN dashboard for S25/browser control over supervised actions, with per-server POST token protection.",
                "files": [_file_state("pip_control_panel.py")],
                "api": ["/status", "/proposal/latest", "/memory/latest", "/traces", "/task-runs", "/system-manifest", "/scheduler/status"],
            },
            "scheduler": {
                "description": "Supervised task queue for long-running or ambient goals.",
                "files": [_file_state("pip_scheduler.py")],
            },
            "task_runs": {
                "description": "Append-only receipts for scheduled jobs, Nightwatch, and background script launches.",
                "files": [_file_state("pip_task_runs.py")],
                "task_runs_path": str(memory_path / "pip_task_runs.jsonl"),
            },
            "model_registry": {
                "description": "Dynamic mapping of task types to local Ollama models based on capabilities and lightweight fit scoring.",
                "files": [_file_state("pip_model_registry.py")],
            },
            "memory": {
                "description": "Tattoo, skin, fur, proposal, app skill, and bridge state stored under Pip memory.",
                "files": [_file_state("pip_engine.py"), _file_state("pip_config.py")],
            },
            "trace_spine": {
                "description": "Append-only JSONL event record for CLI, dashboard, Flow Master, and future agent handoffs.",
                "files": [_file_state("pip_traces.py")],
                "trace_path": str(memory_path / "pip_traces.jsonl"),
            },
            "governors": {
                "description": "Token Governor, Signal Sieve bridge, Prompt Guard, and Flow Master pressure pacing.",
                "files": [_file_state("pip_token_guard.py"), _file_state("pip_prompt_guard.py"), _file_state("pip_flow_master.py")],
            },
            "tool_memory": {
                "description": "Tool-scoped durable rules for app/tool boundaries and high-priority operating constraints.",
                "files": [_file_state("pip_tool_memory.py")],
                "rules_path": str(memory_path / "tool_memory_rules.json"),
            },
            "developer_shells": {
                "description": "Pre-established approval-gated shells for Codex, Claude Code, and Antigravity.",
                "files": [_file_state("pip_app_skills.py")],
                "summary": _developer_shell_summary(),
            },
            "security": {
                "description": "Public-facing safety notes for local/LAN operation, secrets hygiene, and approval boundaries.",
                "files": [_file_state("SECURITY.md")],
            },
            "phone_bridge": {
                "description": "S25 usage import, optimizer, status, and proposal feedback bridge.",
                "files": [_file_state("pip_phone_bridge.py")],
            },
            "gmail_bridge": {
                "description": "Draft-only manual Gmail summary import plus future read-only connector contract. No Gmail write access.",
                "files": [_file_state("pip_gmail_bridge.py"), _file_state("GMAIL_CONNECTOR_ROADMAP.md")],
                "drafts_path": str(memory_path / "gmail_drafts"),
            },
            "repo_watch": {
                "description": "Draft-only public GitHub repo watcher used by the opt-in Weekly Update system.",
                "files": [_file_state("pip_repo_watch.py"), _file_state("pip_weekly_update.py"), _file_state("repo_watch_config.json")],
                "watch_path": str(memory_path / "repo_watch"),
            },
            "weekly_update": {
                "description": "Separate opt-in industry-watch loop for audited system update suggestions. Independent from Nightwatch.",
                "files": [_file_state("pip_weekly_update.py")],
                "status_path": str(memory_path / "weekly_update_status.json"),
            },
            "pc_bridge": {
                "description": "PC usage import/status and Windows foreground tracker adapter.",
                "files": [_file_state("pip_pc_bridge.py"), _file_state("pip_pc_tracker.py")],
            },
        },
        "openjarvis_takeaways_applied": [
            "Expose a system map instead of hiding capabilities across files.",
            "Keep execution observable through durable traces.",
            "Preserve module boundaries so local components can be replaced or upgraded later.",
            "Favor supervised actions and explicit handoff contracts over opaque autonomy.",
        ],
        "odysseus_takeaways_applied": [
            "Keep local/LAN security posture explicit.",
            "Record durable task-run receipts for background work.",
            "Rank local models with task-fit and hardware-fit metadata before routing heavier tasks.",
            "Borrow operational discipline without broadening Pip beyond supervised draft-first work.",
        ],
        "openhuman_takeaways_applied": [
            "Add a prompt-injection preflight guard before admitting chat/tool work.",
            "Store tool-scoped durable rules under Pip memory instead of scattering boundaries across prompts.",
            "Defer hosted OAuth integrations and broad external tools until policy boundaries are stronger.",
        ],
        "dox_takeaways_applied": [
            "Give coding agents a root-to-local context chain before edits.",
            "Keep path-specific contracts close to durable project boundaries.",
            "Validate child indexes and required sections through Pip doctor.",
            "Use DOX as builder guidance without granting runtime permissions.",
        ],
    }


def save_manifest() -> dict[str, Any]:
    manifest = build_manifest()
    path = manifest_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def inspect_manifest(refresh: bool = False) -> dict[str, Any]:
    path = manifest_path()
    if refresh or not path.exists():
        manifest = save_manifest()
        return {
            "generated_at": utc_now(),
            "manifest_path": str(path),
            "exists": True,
            "refreshed": True,
            "manifest": manifest,
        }
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        manifest = save_manifest()
        return {
            "generated_at": utc_now(),
            "manifest_path": str(path),
            "exists": True,
            "refreshed": True,
            "manifest": manifest,
        }
    return {
        "generated_at": utc_now(),
        "manifest_path": str(path),
        "exists": True,
        "refreshed": False,
        "manifest": manifest,
    }
