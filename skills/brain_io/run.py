#!/usr/bin/env python3
import argparse
import json
import re
from pathlib import Path
from typing import Any

def read_brain_file(args: argparse.Namespace) -> dict[str, Any]:
    import pip_config
    brain_dir = pip_config.get_memory_path()
    target = getattr(args, "filename", "")
    results = list(brain_dir.rglob(target))
    if not results:
        return {"skill": "read_brain_file", "ok": False, "message": "File not found"}
    
    try:
        content = results[0].read_text(encoding="utf-8")
        return {
            "skill": "read_brain_file",
            "ok": True,
            "filename": results[0].name,
            "content": content[:5000] # Truncate to avoid memory blowup
        }
    except Exception as e:
        return {"skill": "read_brain_file", "ok": False, "message": str(e)}

def write_brain_file(args: argparse.Namespace) -> dict[str, Any]:
    import pip_platform
    brain_dir = pip_platform.BRAIN_ROOT
    draft_dir = brain_dir / "99_inbox_unsorted" / "pip_drafts"
    draft_dir.mkdir(parents=True, exist_ok=True)
    
    filename = getattr(args, "filename", "new_brain_file.txt")
    target = (draft_dir / filename).resolve()
    
    if not target.is_relative_to(draft_dir):
        return {"skill": "write_brain_file", "ok": False, "message": "Security Error: Attempted to write outside the pip_drafts sandbox."}
        
    if target.suffix not in [".txt", ".json", ".md", ".py"]:
        target = target.with_suffix(".txt")
        
    try:
        mode = "a" if target.exists() else "w"
        with open(target, mode, encoding="utf-8") as f:
            if mode == "a":
                f.write("\n")
            f.write(getattr(args, "content", ""))
        return {"skill": "write_brain_file", "ok": True, "filename": target.name}
    except Exception as e:
        return {"skill": "write_brain_file", "ok": False, "message": str(e)}

def search_brain(args: argparse.Namespace) -> dict[str, Any]:
    query = (getattr(args, "query", "") or "")
    try:
        import pip_hound
        results = pip_hound.search(query)
        return {
            "skill": "search_brain",
            "ok": True,
            "query": query,
            "matches": len(results),
            "results": results
        }
    except Exception as e:
        return {"skill": "search_brain", "ok": False, "message": str(e)}

def record_new_macro(args: argparse.Namespace) -> dict[str, Any]:
    import pip_safety
    blocked = pip_safety.gate_skill(
        "record_new_macro",
        args,
        "Pip wants to record keyboard events until Escape is pressed.",
    )
    if blocked:
        return blocked

    try:
        import pip_hands
    except ImportError:
        return {"skill": "record_new_macro", "ok": False, "message": "pip_hands module not found."}
    
    events = pip_hands.record_macro(stop_key='esc')
    if not events:
        return {"skill": "record_new_macro", "ok": False, "message": "No events recorded or recording failed."}
        
    import pip_config
    brain_dir = pip_config.get_memory_path()
    name = re.sub(r"[^A-Za-z0-9_.-]+", "_", getattr(args, "name", "macro")).strip("._")
    if not name:
        name = "macro"
    target = brain_dir / f"macro_{name}.json"
    target.write_text(json.dumps(events, indent=2), encoding="utf-8")
    
    return {"skill": "record_new_macro", "ok": True, "filename": target.name, "event_count": len(events)}

def run(args: argparse.Namespace) -> dict[str, Any]:
    skill_name = getattr(args, "skill", "")
    
    if skill_name == "read_brain_file":
        return read_brain_file(args)
    elif skill_name == "write_brain_file":
        return write_brain_file(args)
    elif skill_name == "search_brain":
        return search_brain(args)
    elif skill_name == "record_new_macro":
        return record_new_macro(args)
        
    return {"skill": "brain_io", "ok": False, "error": f"Unknown skill {skill_name}"}
