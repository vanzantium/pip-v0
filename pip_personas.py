"""
pip_personas.py — The Persona Orchestrator for the Digital Tavern.
Manages loading persona shells and dispatching tasks via UI automation.
"""
import os
import json
import time
from pathlib import Path
import pip_hands
import pip_evolution
import pip_safety

PERSONAS_DIR = Path(__file__).resolve().parent / "personas"

def load_personas() -> dict:
    """Loads all available persona configurations."""
    personas = {}
    if not PERSONAS_DIR.exists():
        PERSONAS_DIR.mkdir()
        return personas
        
    for pfile in PERSONAS_DIR.glob("*.json"):
        try:
            config = json.loads(pfile.read_text(encoding="utf-8"))
            if "name" in config:
                personas[config["name"].lower()] = config
                for alias in config.get("aliases", []):
                    personas[str(alias).lower()] = config
        except Exception as e:
            print(f"[personas] Failed to load {pfile.name}: {e}")
            
    return personas

def focus_window_by_title(title_snippet: str) -> bool:
    """Tries to bring a window containing the title_snippet to the foreground."""
    try:
        import pygetwindow as gw
        windows = gw.getWindowsWithTitle(title_snippet)
        if windows:
            win = windows[0]
            if win.isMinimized:
                win.restore()
            try:
                win.activate()
            except Exception as e:
                # Background processes often can't steal focus natively. 
                # Fallback: physical click the title bar or center of the window.
                try:
                    import pyautogui
                    pyautogui.click(win.left + win.width // 2, win.top + win.height // 2)
                except Exception:
                    pass
            time.sleep(0.5)
            return True
    except ImportError:
        pass
    except Exception as e:
        pass
    
    return False

def _log_harness(agent_name: str, task_type: str, outcome: str, note: str = ""):
    """Helper to safely log harness events without breaking dispatch."""
    try:
        import sys
        harness_dir = str(Path(__file__).resolve().parent.parent.parent / "builds" / "agent_harness")
        if harness_dir not in sys.path:
            sys.path.insert(0, harness_dir)
        import harness
        harness.log_event(agent_name, task_type, outcome, note=note)
    except Exception as e:
        print(f"[personas] Harness logging failed: {e}")

def dispatch_task(persona_name: str, task_text: str) -> dict:
    """Dispatches a text task to a specific persona via UI macros."""
    personas = load_personas()
    name = persona_name.lower().replace("@", "")
    
    if name not in personas:
        return {"ok": False, "message": f"I couldn't find a persona named {persona_name} in the Tavern."}
        
    config = personas[name]
    macros = config.get("macros", {}).get("submit_task", [])
    
    if not macros:
        return {"ok": False, "message": f"Persona {persona_name} doesn't know how to submit tasks!"}

    has_ui = any(step.get("action") in ("focus_window", "type_text", "press_key") for step in macros)
    if has_ui:
        request = pip_safety.request_safety_permission(
            "ui_automation",
            title=f"Approve persona handoff: {persona_name}",
            rationale=f"Submit task to {config.get('app_name', name)} using UI automation.",
            details={"persona": persona_name, "app": config.get("app_name", name), "task": task_text},
        )
        return {
            "ok": False,
            "blocked": True,
            "message": f"I queued the {persona_name} handoff for approval before touching {config.get('app_name', name)}.",
            "permission_request": request,
        }
        
    # Execute the macro sequence
    print(f"[personas] Dispatching task to {persona_name}...")
    for step in macros:
        action = step.get("action")
        if action == "focus_window":
            # Attempt to focus the app
            success = focus_window_by_title(config.get("window_title", ""))
            if not success:
                # If we can't find it, we prompt the user to open it manually.
                return {"ok": False, "message": f"I couldn't find the {config.get('app_name')} window. Please open it so {persona_name} can take over!"}
                
        elif action == "type_text":
            source = step.get("source")
            text_to_type = task_text if source == "task_input" else step.get("text", "")
            if pip_hands.type_text(text_to_type, interval=0.02):
                pip_evolution.award_xp(config.get("app_name", name), 5)
            
        elif action == "press_key":
            key = step.get("key")
            if pip_hands.press_key(key):
                pip_evolution.award_xp(config.get("app_name", name), 2)

        elif action == "trigger_nap":
            try:
                import pip_phone_relay
                state = pip_phone_relay._load_state()
                state["is_napping"] = True
                pip_phone_relay._save_state(state)
                print(f"[personas] Put Pip to sleep for {persona_name}.")
            except Exception as e:
                print(f"[personas] Failed to trigger nap: {e}")

        elif action == "antigravity_api":
            import subprocess
            bin_path = Path(os.environ.get("USERPROFILE", "C:\\")) / ".gemini" / "antigravity" / "bin" / "agentapi.bat"
            if bin_path.exists():
                conversation_id = step.get("conversation_id", "effdbec6-8661-4627-bf87-c09dc63b0ad9")
                try:
                    # Prepend a marker so I know it's from Pip
                    msg = f"**From Pip (via phone):** {task_text}"
                    subprocess.run([str(bin_path), "send-message", conversation_id, msg], check=True, shell=True, creationflags=subprocess.CREATE_NO_WINDOW)
                    pip_evolution.award_xp(config.get("app_name", name), 5)
                except Exception as e:
                    return {"ok": False, "message": f"Failed to send to Antigravity: {e}"}
            else:
                return {"ok": False, "message": "Antigravity API not found!"}

        elif action == "execute_deep_research":
            import subprocess
            import sys
            # Dedupe: one research at a time. research_is_busy() also repairs
            # stale/dead status as a side effect (see pip_task_monitor.py).
            try:
                import pip_task_monitor
                if pip_task_monitor.research_is_busy():
                    running = pip_task_monitor.read_status()
                    return {"ok": False,
                            "message": f"Research already running on '{running.get('topic', '?')}' - "
                                       "ask again when it finishes."}
            except Exception as e:
                print(f"[personas] task monitor check failed (continuing): {e}")
            script_path = Path(__file__).resolve().parent / "pip_deep_research.py"
            if script_path.exists():
                try:
                    subprocess.Popen(
                        [sys.executable, str(script_path), task_text],
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        creationflags=subprocess.CREATE_NO_WINDOW
                    )
                    pip_evolution.award_xp("Deep Research", 10)
                except Exception as e:
                    print(f"[personas] Failed to launch deep research: {e}")
            else:
                return {"ok": False, "message": "pip_deep_research.py not found!"}

        elif action == "api_chat":
            try:
                import pip_ollama
                import subprocess
                import sys
                import threading
                
                def _run_api_chat():
                    try:
                        response = pip_ollama.generate_chat_response(config.get("app_name", name), task_text)
                        notify_path = Path(__file__).resolve().parent / "pip_notify.py"
                        subprocess.Popen(
                            [sys.executable, str(notify_path), response, "--agent", config.get("app_name", name)],
                            creationflags=subprocess.CREATE_NO_WINDOW
                        )
                        _log_harness(name, "synthesis", "success", "Chat response generated.")
                    except Exception as e:
                        _log_harness(name, "synthesis", "fail", f"Chat failed: {e}")
                
                threading.Thread(target=_run_api_chat, daemon=True).start()
                return {"ok": True, "message": f"Sent '{task_text[:20]}...' to {config.get('app_name', name)} in the background! Will text you the reply."}
            except Exception as e:
                return {"ok": False, "message": f"API Chat failed: {e}"}

        elif action in ["execute_opencode", "execute_grok"]:
            import subprocess
            import sys
            import threading
            
            def _run_headless():
                cmd_key = "cmd_build" if "--auto" in task_text or "build" in task_text else "cmd_plan"
                headless_cfg = config.get("headless", {})
                raw_cmd = headless_cfg.get(cmd_key, [])
                if not raw_cmd:
                    return
                cmd_bin = config.get("cmd_bin", "opencode.cmd" if action == "execute_opencode" else "grok.cmd")
                
                cmd = []
                for part in raw_cmd:
                    if part == "{cmd_bin}": cmd.append(cmd_bin)
                    elif part == "{task}": cmd.append(task_text)
                    elif part == "{workspace}": cmd.append(".")
                    else: cmd.append(part)
                
                env = os.environ.copy()
                
                try:
                    result = subprocess.run(cmd, capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW, env=env)
                    out_text = result.stdout.strip()
                    if not out_text and result.stderr:
                        out_text = result.stderr.strip()
                    if not out_text:
                        out_text = "[No output]"
                        
                    notify_path = Path(__file__).resolve().parent / "pip_notify.py"
                    subprocess.Popen(
                        [sys.executable, str(notify_path), f"[{config.get('app_name', name)}]:\n{out_text[:3000]}", "--agent", config.get("app_name", name)],
                        creationflags=subprocess.CREATE_NO_WINDOW
                    )
                    
                    outcome = "success" if result.returncode == 0 else "fail"
                    _log_harness(name, "code_build", outcome, out_text[:50].replace('\n', ' '))
                except Exception as e:
                    notify_path = Path(__file__).resolve().parent / "pip_notify.py"
                    subprocess.Popen([sys.executable, str(notify_path), f"Error running {action}: {e}", "--agent", "Pip"], creationflags=subprocess.CREATE_NO_WINDOW)
                    _log_harness(name, "code_build", "fail", str(e))
                    
            threading.Thread(target=_run_headless, daemon=True).start()
            return {"ok": True, "message": f"Sent task to {config.get('app_name', name)} in the background! Will text you the output."}
            
        time.sleep(0.5) # Slight pause between macro steps
        
    # Log successful UI/sync dispatch
    if not any(step.get("action") in ["api_chat", "execute_opencode", "execute_grok", "execute_deep_research"] for step in macros):
        _log_harness(name, "ops", "success", "Dispatched UI macro sequence.")
        
    return {"ok": True, "message": f"I've handed the task off to {config.get('app_name', name)}! Check the control panel to see if this app leveled up."}
