import time
import os
import random
from pathlib import Path
import pip_config
import pip_platform
from pip_goal_engine import PipGoalEngine

def get_random_brain_file():
    # Looks for random files in the main brain folder to learn from
    brain_dir = pip_platform.BRAIN_ROOT
    if not brain_dir.exists():
        return None
        
    txt_files = list(brain_dir.glob("*.txt"))
    if not txt_files:
        return None
        
    return random.choice(txt_files)

def run_sleep_cycle():
    if os.environ.get("PIP_ENABLE_NIGHTWATCH") != "1":
        print("Nightwatch is disabled. Set PIP_ENABLE_NIGHTWATCH=1 to run the unattended loop.")
        return

    print("Pip Nightwatch Mode Initiated...")
    engine = PipGoalEngine(max_steps=5)
    
    # Import embedding tool
    import pip_embeddings
    import pip_config
    import pip_self_reflection
    memory_store = pip_embeddings.PersonaMemoryStore()
    
    while True:
        # 1. Self-Reflection
        pip_self_reflection.run_reflection_cycle()
        
        # 2. Dream Cycle
        target_file = get_random_brain_file()
        if target_file:
            print(f"Pip is dreaming about {target_file.name}...")
            dream_name = f"dream_{target_file.stem[:10]}.txt"
            goal = f"""You are in a sleep cycle (free play research).
Please read the file named "{target_file.name}" from the brain.
Then, write a short 1-2 sentence core truth or belief of what you learned into your own memory folder as a new file called "{dream_name}".
When you are done, use finish_goal.
"""
            try:
                result = engine.run_goal(goal, yield_logs=True)
                print(f"Dream cycle finished. Result: {result}")
                
                # RAG Integration: Embed the newly created dream
                mem_path = pip_config.get_memory_path() / dream_name
                if mem_path.exists():
                    dream_text = mem_path.read_text(encoding="utf-8").strip()
                    if dream_text:
                        print(f"Embedding dream into Persona Memory: {dream_text[:50]}...")
                        memory_store.add_memory(dream_text)
                
            except Exception as e:
                print(f"Dream cycle failed: {e}")
                
        # 3. Parameter Sweep
        print("Running parameter tuning sweep...")
        try:
            import pip_eval
            sweep_result = pip_eval.sweep_parameters()
            if sweep_result.get("proposed_change"):
                print("Sweep found a better parameter configuration. Check permissions queue.")
        except Exception as e:
            print(f"Sweep failed: {e}")
            
        # Sleep for a long time before next dream (e.g. 15 minutes)
        time.sleep(900)

if __name__ == "__main__":
    run_sleep_cycle()
