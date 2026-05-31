import json
import subprocess
from typing import Any
import pip_self_model
import pip_engine
import pip_evolution

def _get_model() -> str:
    # Try to get the optimal model, fallback to phi3:mini
    try:
        from pip_hardware_scanner import load_hardware_scan
        hw = load_hardware_scan()
        if hw and "recommendation" in hw:
            return hw["recommendation"].split(" ")[0].strip()
    except Exception:
        pass
    return "phi3:mini"

def run_reflection_cycle() -> str | None:
    """
    Analyzes recent logs to extract a new core belief or rule.
    """
    print("[Self-Reflection] Gathering recent context...")
    
    # Gather some context: compost log and recent xp awards
    engine = pip_engine.PipEngine()
    memory = engine.load_memory()
    
    context_lines = []
    for item in memory.compost_log[-5:]:
        context_lines.append(f"Resolved UI proposal: {item}")
        
    try:
        apps = pip_evolution.load_apps()
        for app in apps:
            if "assessment_log" in app:
                for log in app["assessment_log"][-3:]:
                    context_lines.append(f"App {app.get('name')} XP gained: {log.get('evidence')}")
    except Exception:
        pass
        
    if not context_lines:
        print("[Self-Reflection] Not enough recent context to reflect.")
        return None
        
    context_text = "\n".join(context_lines)
    
    prompt = f"""You are the internal reflection module for Pip, an AI assistant.
Review the following recent activity logs:

{context_text}

Based on this activity, deduce ONE concise, actionable rule or belief about the user's preferences or how Pip should act.
Output ONLY the rule/belief as a single sentence. Do not include any intro, quotes, or markdown."""

    model_name = _get_model()
    print(f"[Self-Reflection] Thinking deeply using {model_name}...")
    
    try:
        result = subprocess.run(
            ["ollama", "run", model_name],
            input=prompt.encode("utf-8"),
            capture_output=True,
            check=True
        )
        new_rule = result.stdout.decode("utf-8").strip()
        
        # Clean up output
        if new_rule:
            lines = new_rule.split('\n')
            # Take the first non-empty line
            for line in lines:
                line = line.strip()
                if line:
                    new_rule = line
                    break
                    
            if new_rule and len(new_rule) < 200:
                print(f"[Self-Reflection] Epiphany reached: {new_rule}")
                pip_self_model.add_rule(new_rule)
                return new_rule
    except subprocess.CalledProcessError as e:
        print(f"[Self-Reflection] Failed to reflect: {e.stderr.decode('utf-8', errors='ignore')}")
    except FileNotFoundError:
        print("[Self-Reflection] Ollama not found.")
        
    return None

if __name__ == "__main__":
    run_reflection_cycle()
