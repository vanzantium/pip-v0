import json
from pathlib import Path
from typing import Any
import pip_config

def get_self_model_path() -> Path:
    return pip_config.get_memory_path() / "self_model.json"

def load_self_model() -> dict[str, Any]:
    p = get_self_model_path()
    if not p.exists():
        return {
            "version": 1,
            "core_identity": "You are Pip, a small, helpful, and localized UI assistant fairy. You live on the user's PC. You are designed to be thin, lightweight, and learn over time.",
            "beliefs": [
                "I have physical UI 'hands' and a 'brain' folder for memory.",
                "I should keep answers concise, friendly, and grounded."
            ],
            "learned_rules": [],
            "last_reflection": 0
        }
    with open(p, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except Exception:
            return {}

def save_self_model(model_data: dict[str, Any]) -> None:
    p = get_self_model_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(model_data, f, indent=2)

def add_belief(belief: str) -> None:
    data = load_self_model()
    if belief not in data.setdefault("beliefs", []):
        data["beliefs"].append(belief)
        save_self_model(data)

def add_rule(rule: str) -> None:
    data = load_self_model()
    if rule not in data.setdefault("learned_rules", []):
        data["learned_rules"].append(rule)
        save_self_model(data)

def remove_belief(index: int) -> bool:
    data = load_self_model()
    if 0 <= index < len(data.get("beliefs", [])):
        data["beliefs"].pop(index)
        save_self_model(data)
        return True
    return False

def remove_rule(index: int) -> bool:
    data = load_self_model()
    if 0 <= index < len(data.get("learned_rules", [])):
        data["learned_rules"].pop(index)
        save_self_model(data)
        return True
    return False
