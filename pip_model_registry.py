#!/usr/bin/env python3
from __future__ import annotations
import json
import argparse
import os
import re
from pathlib import Path
from typing import Any

import pip_config

def registry_path() -> Path:
    return pip_config.get_memory_path() / "pip_model_registry.json"

def _default_registry() -> dict[str, dict[str, Any]]:
    return {
        "phi3:mini": {
            "vram_cost_mb": 2200,
            "strengths": ["formatting", "fast_replies", "json_extraction"],
            "max_context": 8192
        },
        "llama3.2:latest": {
            "vram_cost_mb": 2000,
            "strengths": ["simple_reasoning", "chat"],
            "max_context": 8192
        },
        "gemma4:e4b": {
            "vram_cost_mb": 9600,
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


TASK_ALIASES = {
    "code": "coding",
    "programming": "coding",
    "reason": "complex_reasoning",
    "reasoning": "complex_reasoning",
    "summarize": "summarization",
    "summary": "summarization",
    "json": "json_extraction",
}


def available_vram_mb() -> int:
    env_value = os.environ.get("PIP_AVAILABLE_VRAM_MB", "").strip()
    if env_value:
        try:
            return max(0, int(float(env_value)))
        except ValueError:
            pass
    try:
        hardware_path = pip_config.get_memory_path() / "hardware.json"
        if hardware_path.exists():
            data = json.loads(hardware_path.read_text(encoding="utf-8"))
            for key in ("vram_mb", "gpu_vram_mb", "available_vram_mb"):
                if key in data:
                    return max(0, int(float(data[key] or 0)))
            gpu = data.get("gpu") or {}
            if isinstance(gpu, dict):
                for key in ("vram_mb", "available_vram_mb"):
                    if key in gpu:
                        return max(0, int(float(gpu[key] or 0)))
            elif isinstance(gpu, str):
                numbers = [int(value) for value in re.findall(r"\b\d{7,}\b", gpu)]
                if numbers:
                    # Older Windows scanner output included AdapterRAM bytes in the GPU string.
                    return max(numbers) // (1024 * 1024)
    except Exception:
        pass
    return 0


def score_models(task_type: str, available_mb: int | None = None) -> list[dict[str, Any]]:
    task = TASK_ALIASES.get((task_type or "").strip().lower(), (task_type or "chat").strip().lower())
    registry = get_registry()
    available = available_vram_mb() if available_mb is None else max(0, int(available_mb))
    scored: list[dict[str, Any]] = []
    for model_name, capabilities in registry.items():
        strengths = capabilities.get("strengths", [])
        vram_cost = int(capabilities.get("vram_cost_mb", 0) or 0)
        strength_score = 45 if task in strengths else 0
        if task in {"coding", "complex_reasoning"} and "complex_reasoning" in strengths:
            strength_score = max(strength_score, 35)
        if task in {"chat", "fast_replies"} and "chat" in strengths:
            strength_score = max(strength_score, 35)
        if available <= 0:
            fit_score = 60
            fit_reason = "No VRAM scan available; using advisory fit only."
        elif vram_cost <= available:
            headroom = available - vram_cost
            fit_score = 35 + min(20, int((headroom / max(available, 1)) * 20))
            fit_reason = f"Fits estimated VRAM budget with {headroom} MB headroom."
        else:
            over = vram_cost - available
            fit_score = max(0, 25 - int((over / max(vram_cost, 1)) * 25))
            fit_reason = f"Estimated VRAM shortfall of {over} MB."
        context_score = min(20, int((int(capabilities.get("max_context", 0) or 0) / 8192) * 20))
        size_penalty = 0
        if task in {"formatting", "fast_replies", "json_extraction", "chat"}:
            size_penalty = min(12, int(vram_cost / 1000))
        score = max(0, min(100, strength_score + fit_score + context_score - size_penalty))
        if available > 0 and vram_cost > available:
            # A model that probably will not fit should remain visible but not win routing.
            score = min(score, 60)
        scored.append(
            {
                "model": model_name,
                "score": score,
                "task_type": task,
                "available_vram_mb": available,
                "vram_cost_mb": vram_cost,
                "strength_match": task in strengths,
                "fit_reason": fit_reason,
                "capabilities": capabilities,
            }
        )
    scored.sort(key=lambda item: (item["score"], -item["vram_cost_mb"]), reverse=True)
    return scored


def inspect_registry() -> dict[str, Any]:
    return {
        "registry_path": str(registry_path()),
        "available_vram_mb": available_vram_mb(),
        "models": get_registry(),
        "fit_examples": {
            task: score_models(task)[:3]
            for task in ["chat", "coding", "formatting", "complex_reasoning"]
        },
        "fit_scoring_note": "Advisory only. Pip favors declared task strengths, estimated VRAM fit, context, and smaller models for lightweight tasks.",
    }


def route_task(task_type: str) -> str:
    """Route a task category (e.g., 'coding', 'formatting') to the optimal local model."""
    ranked = score_models(task_type)
    if ranked:
        return ranked[0]["model"]
    
    return "phi3:mini"

def run_route(args: argparse.Namespace) -> dict[str, Any]:
    task = args.task_type or "chat"
    model = route_task(task)
    candidates = score_models(task)[:5]
    return {
        "skill": "route_task",
        "task_type": task,
        "recommended_model": model,
        "capabilities": get_registry().get(model, {}),
        "candidates": candidates,
    }

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pip Model Routing Registry")
    parser.add_argument("--task-type", required=True, help="Task type (e.g., coding, formatting)")
    args = parser.parse_args()
    print(json.dumps(run_route(args), indent=2))
