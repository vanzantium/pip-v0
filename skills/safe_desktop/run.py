#!/usr/bin/env python3
import argparse
import sys
from typing import Any

def get_active_window(args: argparse.Namespace) -> dict[str, Any]:
    try:
        import pygetwindow as gw
        active = gw.getActiveWindow()
        if active:
            return {"skill": "get_active_window", "ok": True, "title": active.title}
        else:
            return {"skill": "get_active_window", "ok": True, "title": "No active window"}
    except Exception as e:
        return {"skill": "get_active_window", "ok": False, "message": str(e)}

def take_snapshot(args: argparse.Namespace) -> dict[str, Any]:
    # Import BOS to check metabolic state
    try:
        import sys
        import os
        from pathlib import Path
        
        # Add the parent directory to sys.path to access pip_bos
        pip_v0_dir = Path(__file__).parent.parent.parent.resolve()
        if str(pip_v0_dir) not in sys.path:
            sys.path.insert(0, str(pip_v0_dir))
            
        import pip_bos
        bos_phase = pip_bos.get_phase()
    except Exception as e:
        return {"skill": "take_snapshot", "ok": False, "message": f"Failed to check BOS phase: {e}"}

    # Deny snapshot if system is under stress
    if bos_phase in ["DWELL", "SHED"]:
        return {
            "skill": "take_snapshot",
            "ok": False,
            "message": f"Snapshot denied by BOS. System is currently in {bos_phase} phase. Taking a snapshot right now would cause lag."
        }

    try:
        from PIL import ImageGrab
        import datetime
        import pip_platform
        
        snapshot = ImageGrab.grab()
        # Save to memory
        draft_dir = pip_platform.BRAIN_ROOT / "99_inbox_unsorted" / "pip_drafts"
        draft_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = draft_dir / f"desktop_snapshot_{timestamp}.png"
        snapshot.save(filename)
        
        return {
            "skill": "take_snapshot", 
            "ok": True, 
            "message": f"Snapshot successfully taken and saved to {filename.name}.",
            "file": str(filename)
        }
    except Exception as e:
        return {"skill": "take_snapshot", "ok": False, "message": str(e)}

def run(args: argparse.Namespace) -> dict[str, Any]:
    skill_name = getattr(args, "skill", "")
    
    if skill_name == "get_active_window":
        return get_active_window(args)
    elif skill_name == "take_snapshot":
        return take_snapshot(args)
        
    return {"skill": "safe_desktop", "ok": False, "error": f"Unknown skill {skill_name}"}

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--skill", type=str)
    args = parser.parse_args()
    print(run(args))
