#!/usr/bin/env python3
from __future__ import annotations
import json
import argparse
from pathlib import Path
from typing import Any

import pip_config

def registry_path() -> Path:
    return pip_config.get_memory_path() / "pip_model_registry.json"

def _default_registry() -> dict[str, dict[str, Any]]:
    return {
        "qwen2.5:0.5b": {
            "vram_cost_mb": 500,
            "strengths": ["formatting", "fast_replies", "json_extraction"],
            "max_context": 8192
        },
        "llama3.2:1b": {
            "vram_cost_mb": 1000,
            "strengths": ["simple_reasoning", "chat"],
            "max_context": 8192
        },
        "llama3:8b": {
            "vram_cost_mb": 4500,
            "strengths": ["coding", "complex_reasoning", "summarization"],
            "max_context": 8192
        }
    }

def get_registry() -> dict[str, dict[str, Any]]:
    path = registry_path()
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    
    # Save default if not exists
    default_data = _default_registry()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(default_data, indent=2), encoding="utf-8")
    return default_data

def route_task(task_type: str) -> str:
    """Route a task category (e.g., 'coding', 'formatting') to the optimal local model."""
    registry = get_registry()
    
    # 1. Look for exact strength match
    for model_name, capabilities in registry.items():
        if task_type in capabilities.get("strengths", []):
            return model_name
            
    # 2. Fallback routing
    if task_type in ["coding", "complex_reasoning"]:
        return "llama3:8b" if "llama3:8b" in registry else "llama3.2:1b"
    
    # 3. Default to the lightest model (Pip's standard operation)
    return "qwen2.5:0.5b"

def run_route(args: argparse.Namespace) -> dict[str, Any]:
    task = args.task_type
    model = route_task(task)
    return {
        "skill": "route_task",
        "task_type": task,
        "recommended_model": model,
        "capabilities": get_registry().get(model, {})
    }

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pip Model Routing Registry")
    parser.add_argument("--task-type", required=True, help="Task type (e.g., coding, formatting)")
    args = parser.parse_args()
    print(json.dumps(run_route(args), indent=2))
