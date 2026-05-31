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
                "description": "Dynamic skill bundles loaded from the skills/ directory.",
                "files": [_file_state("pip_skill_registry.py"), _file_state("skills")],
            },
            "workspace_loop": {
                "description": "Approved-folder scanner, condenser, proposal writer, ambient cycle, and permission queue.",
                "files": [_file_state("pip_workspace.py"), _file_state("approved_workspaces.json")],
            },
            "control_panel": {
                "description": "Local LAN dashboard for S25/browser control over supervised actions.",
                "files": [_file_state("pip_control_panel.py")],
                "api": ["/status", "/proposal/latest", "/memory/latest", "/traces", "/system-manifest", "/scheduler/status"],
            },
            "scheduler": {
                "description": "Supervised task queue for long-running or ambient goals.",
                "files": [_file_state("pip_scheduler.py")],
            },
            "model_registry": {
                "description": "Dynamic mapping of task types to local Ollama models based on capabilities.",
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
                "description": "Token Governor, Signal Sieve bridge, and Flow Master pressure pacing.",
                "files": [_file_state("pip_token_guard.py"), _file_state("pip_flow_master.py")],
            },
            "developer_shells": {
                "description": "Pre-established approval-gated shells for Codex, Claude Code, and Antigravity.",
                "files": [_file_state("pip_app_skills.py")],
                "summary": _developer_shell_summary(),
            },
            "phone_bridge": {
                "description": "S25 usage import, optimizer, status, and proposal feedback bridge.",
                "files": [_file_state("pip_phone_bridge.py")],
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
