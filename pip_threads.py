"""
pip_threads.py — Local Thread Manager for named conversations.
Stores chat histories in 01_agent_context/threads.json
"""
import json
import time
from pathlib import Path
from typing import Dict, Any, List

ROOT = Path(__file__).resolve().parent
THREADS_FILE = ROOT.parent.parent.parent.parent / "01_agent_context" / "threads.json"

def _load_threads() -> Dict[str, Any]:
    if not THREADS_FILE.exists():
        return {}
    try:
        return json.loads(THREADS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}

def _save_threads(data: Dict[str, Any]) -> None:
    THREADS_FILE.parent.mkdir(parents=True, exist_ok=True)
    THREADS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")

def get_thread(name: str) -> Dict[str, Any]:
    """Gets a thread by name, creating it if it doesn't exist."""
    threads = _load_threads()
    name_key = name.lower()
    if name_key not in threads:
        threads[name_key] = {
            "name": name,
            "created_at": time.time(),
            "model": "llama3.2",
            "messages": []
        }
        _save_threads(threads)
    return threads[name_key]

def add_message(name: str, role: str, content: str) -> None:
    """Appends a message to the specified thread."""
    threads = _load_threads()
    name_key = name.lower()
    
    if name_key not in threads:
        get_thread(name) # Initialize it
        threads = _load_threads()
        
    threads[name_key]["messages"].append({
        "role": role,
        "content": content,
        "timestamp": time.time()
    })
    _save_threads(threads)

def set_model(name: str, model: str) -> None:
    """Updates the LLM model assigned to this thread."""
    threads = _load_threads()
    name_key = name.lower()
    if name_key in threads:
        threads[name_key]["model"] = model
        _save_threads(threads)
        
def list_threads() -> List[str]:
    """Returns a list of all thread names."""
    threads = _load_threads()
    return [t.get("name", k) for k, t in threads.items()]
